#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.bytecode.instructions as ins
import ljd.config.version_config
from ljd.bytecode.constants import T_FALSE, T_NIL, T_TRUE
from ljd.bytecode.helpers import get_jump_destination


class _State:
    def __init__(self):
        self.constants = None
        self.debuginfo = None
        self.block = None
        self.blocks = []
        self.block_starts = {}

    def _warp_in_block(self, addr):
        block = self.block_starts[addr]
        block.warpins_count += 1
        return block


def build(prototype):
    return _build_function_definition(prototype)


def _build_function_definition(prototype):
    node = nodes.FunctionDefinition()

    state = _State()

    state.constants = prototype.constants
    state.debuginfo = prototype.debuginfo

    node._upvalues = prototype.constants.upvalue_references
    node._debuginfo = prototype.debuginfo
    node._instructions_count = len(prototype.instructions)

    node.arguments.contents = _build_function_arguments(state, prototype)

    if prototype.flags.is_variadic:
        node.arguments.contents.append(nodes.Vararg())

    instructions = prototype.instructions
    node.statements.contents = _build_function_blocks(state, instructions)

    return node


def _build_function_arguments(state, prototype):
    arguments = []

    count = prototype.arguments_count

    slot = 0
    while slot < count:
        variable = _build_slot(state, 0, slot)

        arguments.append(variable)
        slot += 1

    return arguments


def _build_function_blocks(state, instructions):
    _blockenize(state, instructions)
    _establish_warps(state, instructions)

    state.blocks[0].warpins_count = 1
    prev_block = None

    for block in state.blocks:
        addr = block.first_address
        state.block = block

        while addr <= block._last_body_addr:
            instruction = instructions[addr]

            statement = _build_statement(state, addr, instruction)

            if statement is not None:
                line = state.debuginfo.lookup_line_number(addr)

                setattr(statement, "_addr", addr)
                setattr(statement, "_line", line)

                block.contents.append(statement)

            addr += 1

        # walterr this and other fix maybe belong in mutator.SimpleLoopWarpSwapper?
        if (len(block.contents) == 0 and
                isinstance(block.warp, nodes.UnconditionalWarp) and
                block.warp.type == nodes.UnconditionalWarp.T_JUMP and
                prev_block is not None and
                isinstance(prev_block.warp, nodes.ConditionalWarp)):
            _create_no_op(state, block.first_address, block)

        prev_block = block

    return state.blocks


_JUMP_WARP_INSTRUCTIONS = {ins.UCLO.opcode, ins.ISNEXT.opcode, ins.JMP.opcode, ins.FORI.opcode, ins.JFORI.opcode}

_WARP_INSTRUCTIONS = _JUMP_WARP_INSTRUCTIONS | {ins.FORL.opcode, ins.IFORL.opcode, ins.JFORL.opcode, ins.ITERL.opcode,
                                                ins.IITERL.opcode, ins.JITERL.opcode, ins.LOOP.opcode}


def _blockenize(state, instructions):
    # Fix inverted comparison expressions (e.g. 0 < variable):
    _fix_inverted_comparison_expressions(state, instructions)

    # Fix "repeat until true" encapsulated by another loop
    _fix_broken_repeat_until_loops(state, instructions)

    # Fix "var_1 = var_1 [comparison] var_2 and (operation) var_1 or var_1" edge case
    _fix_broken_unary_expressions(state, instructions)

    addr = 1

    # Duplicates are possible and ok, but we need to sort them out
    last_addresses = set()

    while addr < len(instructions):
        instruction = instructions[addr]
        opcode = instruction.opcode

        if opcode not in _WARP_INSTRUCTIONS:
            addr += 1
            continue

        if opcode in _JUMP_WARP_INSTRUCTIONS:
            destination = get_jump_destination(addr, instruction)

            if opcode != ins.UCLO.opcode or destination != addr + 1:
                last_addresses.add(destination - 1)
                last_addresses.add(addr)
        else:
            last_addresses.add(addr)

        addr += 1

    last_addresses = sorted(list(last_addresses))
    last_addresses.append(len(instructions) - 1)

    # This could happen if something jumps to the first instruction
    # We don't need "zero block" with function header, so simply ignore
    # this
    if last_addresses[0] == 0:
        last_addresses.pop(0)

    previous_last_address = 0

    index = 0
    for last_address in last_addresses:
        block = nodes.Block()
        block.index = index
        block.first_address = previous_last_address + 1
        block.last_address = last_address

        state.blocks.append(block)
        state.block_starts[block.first_address] = block

        previous_last_address = last_address

        index += 1


def _establish_warps(state, instructions):
    state.blocks[0].warpins_count = 1

    enumerated_blocks = enumerate(state.blocks[:-1])
    for i, block in enumerated_blocks:
        if state.blocks.__contains__(block) is None:
            continue

        state.block = block

        end_addr = block.last_address + 1
        start_addr = max(block.last_address - 1, block.first_address)

        # Catch certain double unconditional jumps caused by logical primitives in expressions:
        if start_addr == (end_addr - 1) \
                and end_addr + 1 < len(instructions) \
                and instructions[start_addr].opcode == ins.JMP.opcode \
                and instructions[end_addr].opcode == ins.JMP.opcode \
                and instructions[start_addr].A == instructions[end_addr].A \
                and instructions[start_addr].CD == 0:

            end_instruction_destination = end_addr + instructions[end_addr].CD + 1
            target_instruction_A = instructions[start_addr].A
            exit_instruction_found = False

            # When two consecutive jumps are found with the same A operand, lookahead for the end jump.
            following_destination = -1
            for j in range(end_addr + 1, len(instructions) - 1):
                following_instruction = instructions[j]
                if following_instruction.opcode == ins.JMP.opcode:
                    if following_instruction.A == target_instruction_A:
                        following_destination = get_jump_destination(j, following_instruction)
                        exit_instruction_found = True
                        break

            # If we find the exit jump and we're not skipping it (if true then break else),
            #  form the original two jumps into a fake conditional warp.
            if exit_instruction_found \
                    and end_instruction_destination <= following_destination:
                fixed_instruction = ins.ISF()
                fixed_instruction.CD = ins.SLOT_FALSE

                instructions[start_addr] = fixed_instruction
                state.blocks.pop(state.blocks.index(block) + 1)

                block.last_address += 1
                start_addr = max(block.last_address - 1, block.first_address)
                end_addr = block.last_address + 1

        warp = instructions[start_addr:end_addr]

        block.warp, shift = _build_warp(state, block.last_address, warp)

        setattr(block, "_last_body_addr", block.last_address - shift)
        setattr(block.warp, "_addr", block.last_address - shift + 1)

    last_block = state.blocks[-1]
    last_block.warp = nodes.EndWarp()

    setattr(last_block, "_last_body_addr", last_block.last_address)
    setattr(last_block.warp, "_addr", last_block.last_address)


def _build_warp(state, last_addr, instructions):
    last = instructions[-1]

    if last.opcode in (ins.JMP.opcode, ins.UCLO.opcode, ins.ISNEXT.opcode):
        return _build_jump_warp(state, last_addr, instructions)

    elif ins.ITERL.opcode <= last.opcode <= ins.JITERL.opcode:
        assert len(instructions) == 2
        return _build_iterator_warp(state, last_addr, instructions)

    elif ins.FORL.opcode <= last.opcode <= ins.JFORL.opcode:
        return _build_numeric_loop_warp(state, last_addr, last)

    else:
        return _build_flow_warp(state, last_addr, last)


def _build_jump_warp(state, last_addr, instructions):
    last = instructions[-1]
    opcode = 256 if len(instructions) == 1 else instructions[-2].opcode

    if opcode <= ins.ISF.opcode:
        assert last.opcode != ins.ISNEXT.opcode
        return _build_conditional_warp(state, last_addr, instructions)
    else:
        return _build_unconditional_warp(state, last_addr, last)


def _build_conditional_warp(state, last_addr, instructions):
    condition = instructions[-2]
    condition_addr = last_addr - 1

    warp = nodes.ConditionalWarp()

    if condition.opcode in (ins.ISTC.opcode, ins.ISFC.opcode):
        expression = _build_unary_expression(state,
                                             condition_addr,
                                             condition)

        setattr(warp, "_slot", condition.A)
    elif condition.opcode >= ins.IST.opcode:
        expression = _build_unary_expression(state,
                                             condition_addr,
                                             condition)

        setattr(warp, "_slot", condition.CD)
    else:
        expression = _build_comparison_expression(state,
                                                  condition_addr,
                                                  condition)

    warp.condition = expression

    jump = instructions[-1]
    jump_addr = last_addr

    destination = get_jump_destination(jump_addr, jump)

    # A condition is inverted during the preparation phase above
    warp.false_target = state._warp_in_block(destination)
    warp.true_target = state._warp_in_block(jump_addr + 1)

    shift = 2
    if destination == (jump_addr + 1) \
            and condition.opcode not in (ins.ISTC.opcode, ins.ISFC.opcode):
        # This is an empty 'then' or 'else'. The simplest way to handle it is
        # to insert a Block containing just a no-op statement.
        block = nodes.Block()
        block.first_address = jump_addr + 1
        block.last_address = block.first_address
        block.index = warp.true_target.index
        block.warpins_count = 1
        setattr(block, "_last_body_addr", block.last_address - shift)

        block.warp = nodes.UnconditionalWarp()
        block.warp.type = nodes.UnconditionalWarp.T_FLOW
        block.warp.target = warp.true_target
        setattr(block.warp, "_addr", block.last_address - shift + 1)

        state.blocks.insert(state.blocks.index(warp.true_target), block)
        warp.true_target = block

        _create_no_op(state, jump_addr, block)

    return warp, shift


def _create_no_op(state, addr, block):
    statement = nodes.NoOp()
    setattr(statement, "_addr", addr)
    setattr(statement, "_line", state.debuginfo.lookup_line_number(addr))
    block.contents.append(statement)


def _build_unconditional_warp(state, addr, instruction):
    warp = nodes.UnconditionalWarp()
    warp.type = nodes.UnconditionalWarp.T_JUMP

    opcode = instruction.opcode

    warp.is_uclo = opcode == ins.UCLO.opcode

    shift = 1
    if warp.is_uclo and instruction.CD == 0:
        # Not a jump
        return _build_flow_warp(state, addr, instruction)
    else:
        destination = get_jump_destination(addr, instruction)
        warp.target = state._warp_in_block(destination)

    return warp, shift


def _build_iterator_warp(state, last_addr, instructions):
    iterator = instructions[-2]
    iterator_addr = last_addr - 1

    assert iterator.opcode in (ins.ITERC.opcode, ins.ITERN.opcode)

    warp = nodes.IteratorWarp()

    base = iterator.A

    warp.controls.contents = [
        _build_slot(state, iterator_addr, base - 3),  # generator
        _build_slot(state, iterator_addr, base - 2),  # state
        _build_slot(state, iterator_addr, base - 1)  # control
    ]

    last_slot = base + iterator.B - 2

    slot = base

    while slot <= last_slot:
        variable = _build_slot(state, iterator_addr - 1, slot)
        warp.variables.contents.append(variable)
        slot += 1

    jump = instructions[-1]
    jump_addr = last_addr

    destination = get_jump_destination(jump_addr, jump)
    warp.way_out = state._warp_in_block(jump_addr + 1)
    warp.body = state._warp_in_block(destination)

    return warp, 2


def _build_numeric_loop_warp(state, addr, instruction):
    warp = nodes.NumericLoopWarp()

    base = instruction.A

    warp.index = _build_slot(state, addr, base + 3)
    warp.controls.contents = [
        _build_slot(state, addr, base + 0),  # start
        _build_slot(state, addr, base + 1),  # limit
        _build_slot(state, addr, base + 2)  # step
    ]

    destination = get_jump_destination(addr, instruction)
    warp.body = state._warp_in_block(destination)
    warp.way_out = state._warp_in_block(addr + 1)

    return warp, 1


def _build_flow_warp(state, addr, instruction):
    warp = nodes.UnconditionalWarp()
    warp.type = nodes.UnconditionalWarp.T_FLOW
    warp.target = state._warp_in_block(addr + 1)

    opcode = instruction.opcode
    shift = 1 if opcode in (ins.FORI.opcode, ins.UCLO.opcode) else 0

    return warp, shift


def _build_statement(state, addr, instruction):
    opcode = instruction.opcode
    A_type = instruction.A_type

    # Generic assignments - handle the ASSIGNMENT stuff below
    if A_type == ins.T_DST or A_type == ins.T_UV:
        return _build_var_assignment(state, addr, instruction)

    # ASSIGNMENT starting from MOV and ending at KPRI

    elif opcode == ins.KNIL.opcode:
        return _build_knil(state, addr, instruction)

    # ASSIGNMENT starting from UGET and ending at USETP

    # SKIP UCL0 is handled below

    # ASSIGNMENT starting from FNEW and ending at GGET

    elif opcode == ins.GSET.opcode:
        return _build_global_assignment(state, addr, instruction)

    # ASSIGNMENT starting from TGETV and ending at TGETR

    elif opcode >= ins.TSETV.opcode and (opcode <= ins.TSETB.opcode
                                         or (ljd.config.version_config.use_version > 2.0
                                             and opcode == ins.TSETR.opcode)):
        return _build_table_assignment(state, addr, instruction)

    elif opcode == ins.TSETM.opcode:
        return _build_table_mass_assignment(state, addr, instruction)

    elif ins.CALLM.opcode <= opcode <= ins.CALLT.opcode:
        return _build_call(state, addr, instruction)

    elif opcode == ins.VARG.opcode:
        return _build_vararg(state, addr, instruction)

    elif ins.RETM.opcode <= opcode <= ins.RET1.opcode:
        return _build_return(state, addr, instruction)

    else:
        assert opcode == ins.UCLO.opcode or (
                ins.LOOP.opcode <= opcode <= ins.JLOOP.opcode)
        # NoOp
        return None


def _build_var_assignment(state, addr, instruction):
    opcode = instruction.opcode

    assignment = nodes.Assignment()

    # Unary assignment operators (A = op D)
    if opcode == ins.MOV.opcode \
            or opcode == ins.NOT.opcode \
            or opcode == ins.UNM.opcode \
            or (ljd.config.version_config.use_version > 2.0 and opcode == ins.ISTYPE.opcode) \
            or (ljd.config.version_config.use_version > 2.0 and opcode == ins.ISNUM.opcode) \
            or opcode == ins.LEN.opcode:
        expression = _build_unary_expression(state, addr, instruction)

    # Binary assignment operators (A = B op C)
    elif opcode <= ins.POW.opcode:
        expression = _build_binary_expression(state, addr, instruction)

    # Concat assignment type (A = B .. B + 1 .. ... .. C - 1 .. C)
    elif opcode == ins.CAT.opcode:
        expression = _build_concat_expression(state, addr, instruction)

    # Constant assignment operators except KNIL, which is weird anyway
    elif opcode <= ins.KPRI.opcode:
        expression = _build_const_expression(state, addr, instruction)

    elif opcode == ins.UGET.opcode:
        expression = _build_upvalue(state, addr, instruction.CD)

    elif opcode == ins.USETV.opcode:
        expression = _build_slot(state, addr, instruction.CD)

    elif opcode <= ins.USETP.opcode:
        expression = _build_const_expression(state, addr, instruction)

    elif opcode == ins.FNEW.opcode:
        expression = _build_function(state, instruction.CD)

    elif opcode == ins.TNEW.opcode:
        expression = nodes.TableConstructor()

    elif opcode == ins.TDUP.opcode:
        expression = _build_table_copy(state, instruction.CD)

    elif opcode == ins.GGET.opcode:
        expression = _build_global_variable(state, addr, instruction.CD)

    else:
        if ljd.config.version_config.use_version > 2.0:
            assert opcode <= ins.TGETR.opcode
            expression = _build_table_element(state, addr, instruction)
        else:
            assert opcode <= ins.TGETB.opcode
            expression = _build_table_element(state, addr, instruction)

    assignment.expressions.contents.append(expression)

    if instruction.A_type == ins.T_DST:
        destination = _build_slot(state, addr, instruction.A)
    else:
        assert instruction.A_type == ins.T_UV

        destination = _build_upvalue(state, addr, instruction.A)

    assignment.destinations.contents.append(destination)

    return assignment


def _build_knil(state, addr, instruction):
    node = _build_range_assignment(state, addr, instruction.A, instruction.CD)

    node.expressions.contents = [_build_primitive(state, None)]

    return node


def _build_global_assignment(state, addr, instruction):
    assignment = nodes.Assignment()

    variable = _build_global_variable(state, addr, instruction.CD)
    expression = _build_slot(state, addr, instruction.A)

    assignment.destinations.contents.append(variable)
    assignment.expressions.contents.append(expression)

    return assignment


def _build_table_assignment(state, addr, instruction):
    assignment = nodes.Assignment()

    destination = _build_table_element(state, addr, instruction)
    expression = _build_slot(state, addr, instruction.A)

    assignment.destinations.contents.append(destination)
    assignment.expressions.contents.append(expression)

    return assignment


def _build_table_mass_assignment(state, addr, instruction):
    assignment = nodes.Assignment()

    base = instruction.A

    destination = nodes.TableElement()
    destination.key = nodes.MULTRES()
    destination.table = _build_slot(state, addr, base - 1)

    assignment.destinations.contents = [destination]
    assignment.expressions.contents = [nodes.MULTRES()]

    return assignment


def _build_call(state, addr, instruction):
    call = nodes.FunctionCall()
    call.function = _build_slot(state, addr, instruction.A)
    call.arguments.contents = _build_call_arguments(state, addr, instruction)

    if instruction.opcode <= ins.CALL.opcode:
        if instruction.B == 0:
            node = nodes.Assignment()
            node.destinations.contents.append(nodes.MULTRES())
            node.expressions.contents.append(call)
        elif instruction.B == 1:
            node = call
        else:
            from_slot = instruction.A
            to_slot = instruction.A + instruction.B - 2
            node = _build_range_assignment(state, addr, from_slot,
                                           to_slot)
            node.expressions.contents.append(call)
    else:
        assert instruction.opcode <= ins.CALLT.opcode
        node = nodes.Return()
        node.returns.contents.append(call)

    return node


def _build_vararg(state, addr, instruction):
    base = instruction.A
    last_slot = base + instruction.B - 2

    if last_slot < base:
        node = nodes.Assignment()
        node.destinations.contents.append(nodes.MULTRES())
        node.expressions.contents.append(nodes.Vararg())
    else:
        node = _build_range_assignment(state, addr, base, last_slot)
        node.expressions.contents.append(nodes.Vararg())

    return node


def _build_return(state, addr, instruction):
    node = nodes.Return()

    base = instruction.A
    last_slot = base + instruction.CD - 1

    if instruction.opcode != ins.RETM.opcode:
        last_slot -= 1

    slot = base

    # Negative count for the RETM is OK
    while slot <= last_slot:
        variable = _build_slot(state, addr, slot)
        node.returns.contents.append(variable)
        slot += 1

    if instruction.opcode == ins.RETM.opcode:
        node.returns.contents.append(nodes.MULTRES())

    return node


def _build_call_arguments(state, addr, instruction):
    base = instruction.A
    last_argument_slot = base + instruction.CD

    is_variadic = (instruction.opcode == ins.CALLM.opcode
                   or instruction.opcode == ins.CALLMT.opcode)

    if not is_variadic:
        last_argument_slot -= 1

    arguments = []

    slot = base + 1

    while slot <= last_argument_slot:
        argument = _build_slot(state, addr, slot)
        arguments.append(argument)
        slot += 1

    if is_variadic:
        arguments.append(nodes.MULTRES())

    return arguments


def _build_range_assignment(state, addr, from_slot, to_slot):
    assignment = nodes.Assignment()

    slot = from_slot

    assert from_slot <= to_slot

    while slot <= to_slot:
        destination = _build_slot(state, addr, slot)

        assignment.destinations.contents.append(destination)

        slot += 1

    return assignment


_BINARY_OPERATOR_MAP = [None] * 255

_BINARY_OPERATOR_MAP[ins.ADDVN.opcode] = nodes.BinaryOperator.T_ADD
_BINARY_OPERATOR_MAP[ins.SUBVN.opcode] = nodes.BinaryOperator.T_SUBTRACT
_BINARY_OPERATOR_MAP[ins.MULVN.opcode] = nodes.BinaryOperator.T_MULTIPLY
_BINARY_OPERATOR_MAP[ins.DIVVN.opcode] = nodes.BinaryOperator.T_DIVISION
_BINARY_OPERATOR_MAP[ins.MODVN.opcode] = nodes.BinaryOperator.T_MOD


def _build_binary_expression(state, addr, instruction):
    operator = nodes.BinaryOperator()
    opcode = instruction.opcode

    if opcode == ins.POW.opcode:
        operator.type = nodes.BinaryOperator.T_POW
    else:
        map_index = opcode - ins.ADDVN.opcode
        map_index %= 5
        map_index += ins.ADDVN.opcode

        operator.type = _BINARY_OPERATOR_MAP[map_index]

    assert (ins.ADDVN.opcode <= opcode <= ins.POW.opcode)
    assert instruction.B_type == ins.T_VAR

    # VN
    if opcode < ins.ADDNV.opcode:
        operator.left = _build_slot(state, addr, instruction.B)
        operator.right = _build_numeric_constant(state, instruction.CD)

    # NV
    elif opcode < ins.ADDVV.opcode:
        operator.right = _build_slot(state, addr, instruction.B)
        operator.left = _build_numeric_constant(state, instruction.CD)

    # VV
    else:
        assert instruction.CD_type == ins.T_VAR
        operator.left = _build_slot(state, addr, instruction.B)
        operator.right = _build_slot(state, addr, instruction.CD)

    return operator


def _build_concat_expression(state, addr, instruction):
    operator = nodes.BinaryOperator()
    operator.type = nodes.BinaryOperator.T_CONCAT

    slot = instruction.B

    operator.left = _build_slot(state, addr, slot)
    operator.right = _build_slot(state, addr, slot + 1)

    slot += 2

    while slot <= instruction.CD:
        upper_operator = nodes.BinaryOperator()
        upper_operator.left = operator
        upper_operator.right = _build_slot(state, addr, slot)
        upper_operator.type = nodes.BinaryOperator.T_CONCAT

        operator = upper_operator

        slot += 1

    return operator


def _build_const_expression(state, addr, instruction):
    CD_type = instruction.CD_type

    if CD_type == ins.T_STR:
        return _build_string_constant(state, instruction.CD)
    elif CD_type == ins.T_CDT:
        return _build_cdata_constant(state, instruction.CD)
    elif CD_type == ins.T_SLIT:
        value = instruction.CD

        if value & 0x8000:
            value = -0x10000 + value

        return _build_literal(state, value)
    elif CD_type == ins.T_LIT:
        return _build_literal(state, instruction.CD)
    elif CD_type == ins.T_NUM:
        return _build_numeric_constant(state, instruction.CD)
    else:
        assert CD_type == ins.T_PRI
        return _build_primitive(state, instruction.CD)


def _build_table_element(state, addr, instruction):
    node = nodes.TableElement()
    node.table = _build_slot(state, addr, instruction.B)

    if instruction.CD_type == ins.T_VAR:
        node.key = _build_slot(state, addr, instruction.CD)
    else:
        node.key = _build_const_expression(state, addr, instruction)

    return node


def _build_function(state, slot):
    prototype = state.constants.complex_constants[slot]

    return _build_function_definition(prototype)


def _build_table_copy(state, slot):
    node = nodes.TableConstructor()

    table = state.constants.complex_constants[slot]

    i = 0

    for value in table.array:
        record = nodes.ArrayRecord()
        record.value = _build_table_record_item(value)

        node.array.contents.append(record)

        i += 1

    for key, value in table.dictionary:
        record = nodes.TableRecord()
        record.key = _build_table_record_item(key)
        record.value = _build_table_record_item(value)

        node.records.contents.append(record)

    return node


def _build_table_record_item(value):
    item = None
    if value is None:
        item = nodes.Primitive()
        item.type = nodes.Primitive.T_NIL
    elif value is True:
        item = nodes.Primitive()
        item.type = nodes.Primitive.T_TRUE
    elif value is False:
        item = nodes.Primitive()
        item.type = nodes.Primitive.T_FALSE
    elif isinstance(value, int):
        item = nodes.Constant()
        item.value = value
        item.type = nodes.Constant.T_INTEGER
    elif isinstance(value, float):
        item = nodes.Constant()
        item.value = value
        item.type = nodes.Constant.T_FLOAT
    elif isinstance(value, str):
        item = nodes.Constant()
        item.value = value
        item.type = nodes.Constant.T_STRING

    return item


_COMPARISON_MAP = [None] * 255

# Mind the inversion - comparison operators are affecting JMP to the next block
# So in the normal code a comparison will be inverted
_COMPARISON_MAP[ins.ISLT.opcode] = nodes.BinaryOperator.T_GREATER_OR_EQUAL
_COMPARISON_MAP[ins.ISGE.opcode] = nodes.BinaryOperator.T_LESS_THEN
_COMPARISON_MAP[ins.ISLE.opcode] = nodes.BinaryOperator.T_GREATER_THEN
_COMPARISON_MAP[ins.ISGT.opcode] = nodes.BinaryOperator.T_LESS_OR_EQUAL

_COMPARISON_MAP[ins.ISEQV.opcode] = nodes.BinaryOperator.T_NOT_EQUAL
_COMPARISON_MAP[ins.ISNEV.opcode] = nodes.BinaryOperator.T_EQUAL

_COMPARISON_MAP[ins.ISEQS.opcode] = nodes.BinaryOperator.T_NOT_EQUAL
_COMPARISON_MAP[ins.ISNES.opcode] = nodes.BinaryOperator.T_EQUAL

_COMPARISON_MAP[ins.ISEQN.opcode] = nodes.BinaryOperator.T_NOT_EQUAL
_COMPARISON_MAP[ins.ISNEN.opcode] = nodes.BinaryOperator.T_EQUAL

_COMPARISON_MAP[ins.ISEQP.opcode] = nodes.BinaryOperator.T_NOT_EQUAL
_COMPARISON_MAP[ins.ISNEP.opcode] = nodes.BinaryOperator.T_EQUAL


def _build_comparison_expression(state, addr, instruction):
    operator = nodes.BinaryOperator()

    operator.left = _build_slot(state, addr, instruction.A)

    opcode = instruction.opcode

    if opcode == ins.ISEQS.opcode or opcode == ins.ISNES.opcode:
        operator.right = _build_string_constant(state, instruction.CD)
    elif opcode == ins.ISEQN.opcode or opcode == ins.ISNEN.opcode:
        operator.right = _build_numeric_constant(state, instruction.CD)
    elif opcode == ins.ISEQP.opcode or opcode == ins.ISNEP.opcode:
        operator.right = _build_primitive(state, instruction.CD)
    else:
        operator.right = _build_slot(state, addr, instruction.CD)

    operator.type = _COMPARISON_MAP[instruction.opcode]
    assert operator.type is not None

    return operator


def _build_unary_expression(state, addr, instruction):
    opcode = instruction.opcode

    variable = _build_slot(state, addr, instruction.CD)

    # Mind the inversion
    if opcode == ins.ISFC.opcode \
            or opcode == ins.ISF.opcode \
            or opcode == ins.MOV.opcode:
        return variable

    operator = nodes.UnaryOperator()
    operator.operand = variable

    if opcode == ins.ISTC.opcode \
            or opcode == ins.IST.opcode \
            or opcode == ins.NOT.opcode:
        operator.type = nodes.UnaryOperator.T_NOT
    elif opcode == ins.UNM.opcode:
        operator.type = nodes.UnaryOperator.T_MINUS
    elif ljd.config.version_config.use_version > 2.0 and opcode == ins.ISTYPE.opcode:
        operator.type = nodes.UnaryOperator.T_TOSTRING
    elif ljd.config.version_config.use_version > 2.0 and opcode == ins.ISNUM.opcode:
        operator.type = nodes.UnaryOperator.T_TONUMBER
    else:
        assert opcode == ins.LEN.opcode
        operator.type = nodes.UnaryOperator.T_LENGTH_OPERATOR

    return operator


def _build_slot(state, addr, slot):
    return _build_identifier(state, addr, slot, nodes.Identifier.T_LOCAL)


def _build_upvalue(state, addr, slot):
    return _build_identifier(state, addr, slot, nodes.Identifier.T_UPVALUE)


def _build_identifier(state, addr, slot, want_type):
    node = nodes.Identifier()
    setattr(node, "_addr", addr)

    node.slot = slot
    node.type = nodes.Identifier.T_SLOT

    if want_type == nodes.Identifier.T_UPVALUE:
        name = state.debuginfo.lookup_upvalue_name(slot)

        if name is not None:
            node.name = name
            node.type = want_type

    return node


def _build_global_variable(state, addr, slot):
    node = nodes.TableElement()
    node.table = nodes.Identifier()
    node.table.type = nodes.Identifier.T_BUILTIN
    node.table.name = "_env"

    node.key = _build_string_constant(state, slot)

    return node


def _build_string_constant(state, index):
    node = nodes.Constant()
    node.type = nodes.Constant.T_STRING
    node.value = state.constants.complex_constants[index]

    return node


def _build_cdata_constant(state, index):
    node = nodes.Constant()
    node.type = nodes.Constant.T_CDATA
    node.value = state.constants.complex_constants[index]

    return node


def _build_numeric_constant(state, index):
    number = state.constants.numeric_constants[index]

    node = nodes.Constant()
    node.value = number

    if isinstance(number, int):
        node.type = nodes.Constant.T_INTEGER
    else:
        node.type = nodes.Constant.T_FLOAT

    return node


def _build_primitive(state, value):
    node = nodes.Primitive()

    if value is True or value == T_TRUE:
        node.type = nodes.Primitive.T_TRUE
    elif value is False or value == T_FALSE:
        node.type = nodes.Primitive.T_FALSE
    else:
        assert value is None or value == T_NIL

        node.type = nodes.Primitive.T_NIL

    return node


def _build_literal(state, value):
    node = nodes.Constant()
    node.value = value
    node.type = nodes.Constant.T_INTEGER

    return node


def _fix_inverted_comparison_expressions(state, instructions):
    for i, instruction in enumerate(instructions):

        if ins.ISLT.opcode <= instruction.opcode <= ins.ISGT.opcode:
            left_slot = instruction.A
            right_slot = instruction.CD

            is_inverted = False
            if i > 0:
                preceding_instruction = instructions[i - 1]

                # Matching A slot for left slot
                if hasattr(preceding_instruction, "A") and preceding_instruction.A == left_slot:
                    opcode = preceding_instruction.opcode

                    # Previous instruction is likely a number assignment to left slot
                    if ins.UNM.opcode <= opcode <= ins.POW.opcode \
                            or ins.KSHORT.opcode <= opcode <= ins.KNUM.opcode:
                        is_inverted = True

            # Invert order of slots
            if is_inverted:
                instruction.A = right_slot
                instruction.CD = left_slot

                if instruction.opcode == ins.ISGT.opcode:
                    instruction.opcode = ins.ISLT.opcode
                elif instruction.opcode == ins.ISGE.opcode:
                    instruction.opcode = ins.ISLE.opcode

                elif instruction.opcode == ins.ISLT.opcode:
                    instruction.opcode = ins.ISGT.opcode
                elif instruction.opcode == ins.ISLE.opcode:
                    instruction.opcode = ins.ISGE.opcode


def _fix_broken_repeat_until_loops(state, instructions):
    enumerated_instructions = enumerate(instructions)
    for i, instruction in enumerated_instructions:

        if instruction.opcode == ins.LOOP.opcode:

            # Check for the conditional jump that restarts the loop
            loop_exit_addr = get_jump_destination(i, instruction)
            loop_condition_addr = loop_exit_addr - 1
            loop_condition_instruction = instructions[loop_condition_addr]
            if not loop_condition_instruction.opcode == ins.JMP.opcode:
                if get_jump_destination(loop_condition_addr, loop_condition_instruction) <= i:
                    continue

                # It's not there, so this is probably a repeat-until true loop.

                # We need a fake conditional warp that is treated as 'true' by the writer
                fixed_cond_instruction = ins.ISF()
                fixed_cond_instruction.CD = ins.SLOT_TRUE

                # Resulting jump to the loop starting point
                fixed_jump_instruction = ins.JMP()
                fixed_jump_instruction.CD = i - loop_condition_addr - 1

                # Add fake conditional instructions
                insertion_index = loop_condition_addr + 1
                _insert_instruction(state, instructions, insertion_index, fixed_jump_instruction)
                _insert_instruction(state, instructions, insertion_index, fixed_cond_instruction)

                shift = 2

                # Fix non-break destinations within the loop
                # Breaks in the empty-condition loop point towards the same exit destination
                # as non-breaks, so we'll have to search for a pattern of jumps.

                leading_jump = False
                start_index = i + 1
                for j in range(start_index, insertion_index):
                    checked_instruction = instructions[j]

                    # Look for following JMP instructions
                    if checked_instruction.opcode == ins.JMP.opcode:

                        # Leading jump indicates this is a break?
                        if not leading_jump:
                            checked_instruction_destination \
                                = get_jump_destination(j, checked_instruction)

                            # If the destination would've been moved
                            if checked_instruction.CD >= shift \
                                    and checked_instruction_destination == insertion_index + shift:

                                # Check for an inverted jump pair
                                next_index = j + 1
                                following_instruction = instructions[next_index]
                                if following_instruction.opcode == ins.JMP.opcode:
                                    following_destination \
                                        = get_jump_destination(next_index, following_instruction)

                                    # e.g. goto 277 followed directly by goto 176
                                    if following_destination < checked_instruction_destination:
                                        leading_jump = True
                                        continue

                                    # e.g. goto 277 followed directly by goto 277
                                    elif following_destination == checked_instruction_destination:
                                        leading_jump = False
                                        continue

                                # Check for else-break-end following this jump
                                following_else_break_found = False
                                prev_jump = False
                                for k in range(next_index, insertion_index):
                                    following_instruction = instructions[k]
                                    if following_instruction.opcode == ins.JMP.opcode:
                                        if not prev_jump:
                                            prev_jump = True

                                        else:
                                            following_destination \
                                                = get_jump_destination(k, following_instruction)

                                            # Don't adjust the checked jump, it's probably a break
                                            if following_instruction.CD >= shift \
                                                    and following_destination \
                                                    == checked_instruction_destination:
                                                following_else_break_found = True
                                                break

                                            prev_jump = False

                                    else:
                                        if prev_jump:
                                            last_destination \
                                                = get_jump_destination(k - 1, instructions[k - 1])
                                            # We can adjust, it's probably not a break
                                            if last_destination < checked_instruction_destination:
                                                break
                                        prev_jump = False

                                if not following_else_break_found:
                                    checked_instruction.CD -= shift
                        leading_jump = True

                    else:
                        leading_jump = False


def _fix_broken_unary_expressions(state, instructions):
    enumerated_instructions = enumerate(instructions)
    for i, instruction in enumerated_instructions:
        if i > 2 and instruction.opcode == ins.ISTC.opcode \
                and ins.ADDVN.opcode <= instructions[i - 1].opcode <= ins.CAT.opcode:

            # Search for a jump that precedes the ISTC op
            leading_jump_found = False
            for j in range(1, i):
                if instructions[i - j].opcode == ins.JMP.opcode:
                    leading_jump_found = True
                    break
                elif instructions[i - j].opcode not in range(ins.ADDVN.opcode, ins.CAT.opcode):
                    break

            # Make sure the preceding jump matches the destination of the ISTC op
            instruction_destination = get_jump_destination(i + 1, instructions[i + 1])
            if instruction_destination == i + 2 and leading_jump_found:
                # Additional jump edge case of an edge case when expression is in an else body
                if not instruction_destination == get_jump_destination(i - j, instructions[i - j]):

                    if instructions[i + 2].opcode == ins.JMP.opcode:
                        instruction_destination = get_jump_destination(i + 2, instructions[i + 2])

                        if instruction_destination == get_jump_destination(i - j, instructions[i - j]):
                            instructions[i - 1].A = instruction.A

                            # Remove the broken condition
                            _remove_instruction(state, instructions, i + 1)
                            _remove_instruction(state, instructions, i)

                else:
                    instructions[i - 1].A = instruction.A

                    # Remove the broken condition
                    _remove_instruction(state, instructions, i + 1)
                    _remove_instruction(state, instructions, i)


def _insert_instruction(state, instructions, index, new_instruction):
    preceding_index = index - 1
    line_mapping = state.debuginfo.addr_to_line_map[preceding_index]

    instructions.insert(index, new_instruction)
    state.debuginfo.addr_to_line_map.insert(index, line_mapping)

    # Offset
    shift = 1

    # Update warp destinations with regards to the inserted instruction
    _shift_warp_destinations(state, instructions, shift, index)

    # Update variable info ranges
    _shift_debug_variable_info(state, shift, index)


def _remove_instruction(state, instructions, index):
    removed_instruction = instructions.pop(index)
    state.debuginfo.addr_to_line_map.pop(index)

    # Offset
    shift = -1

    # Update warp destinations with regards to the removed instruction
    _shift_warp_destinations(state, instructions, shift, index)

    # Update variable info ranges
    _shift_debug_variable_info(state, shift, index)

    return removed_instruction


def _shift_warp_destinations(state, instructions, shift, modified_index):
    for current_index, moved_instruction in enumerate(instructions):
        opcode = moved_instruction.opcode

        if opcode in _WARP_INSTRUCTIONS:
            if current_index < modified_index and moved_instruction.CD >= 0:
                destination = get_jump_destination(current_index, moved_instruction)
                if destination > modified_index or (destination == modified_index and shift > 0):
                    moved_instruction.CD += shift

            elif current_index >= modified_index and moved_instruction.CD < 0:
                destination = current_index + moved_instruction.CD - shift + 1
                if destination < modified_index or (destination == modified_index and shift > 0):
                    moved_instruction.CD -= shift


def _shift_debug_variable_info(state, shift, modified_index):
    for variable_info in state.debuginfo.variable_info:

        if variable_info.end_addr > modified_index \
                or (shift > 0 and variable_info.end_addr == modified_index):
            variable_info.end_addr += shift

        if variable_info.start_addr > modified_index \
                or (shift > 0 and variable_info.start_addr == modified_index):
            variable_info.start_addr += shift
