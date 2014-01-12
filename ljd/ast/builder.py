#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.bytecode.instructions as ins

from ljd.bytecode.helpers import get_jump_destination
from ljd.bytecode.constants import T_NIL, T_FALSE, T_TRUE

import ljd.ast.nodes as nodes


class _State():
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

	state.blocks[0].warpins_count = 1

	for block in state.blocks:
		addr = block.first_address
		state.block = block

		while addr <= block.last_address:
			instruction = instructions[addr]

			statement = _build_statement(state, addr, instruction)

			if statement is not None:
				line = state.debuginfo.lookup_line_number(addr)

				setattr(statement, "_addr", addr)
				setattr(statement, "_line", line)

				block.contents.append(statement)

			addr += 1

		next_address = block.last_address + 1

		if block.warp is None:
			if block != state.blocks[-1]:
				block.warp = nodes.UnconditionalWarp()
				block.warp.type = nodes.UnconditionalWarp.T_FLOW

				next_block = state._warp_in_block(next_address)
				block.warp.target = next_block
			else:
				block.warp = nodes.EndWarp()

		setattr(block.warp, "_addr", block.last_address)

	state.blocks[-1].warp = nodes.EndWarp()

	# Blocks are linked with warps
	return state.blocks


_JUMP_WARP_INSTRUCTIONS = set((
	ins.UCLO.opcode,
	ins.ISNEXT.opcode,
	ins.JMP.opcode,
	ins.FORI.opcode,
	ins.JFORI.opcode
))


_WARP_INSTRUCTIONS = _JUMP_WARP_INSTRUCTIONS | set((
	ins.FORL.opcode, ins.IFORL.opcode, ins.JFORL.opcode,
	ins.ITERL.opcode, ins.IITERL.opcode, ins.JITERL.opcode
))


def _blockenize(state, instructions):
	addr = 1

	# Duplicates are possible and ok, but we need to sort them out
	last_addresses = set()

	while addr < len(instructions):
		instruction = instructions[addr]
		opcode = instruction.opcode

		if opcode not in _WARP_INSTRUCTIONS:
			addr += 1
			continue

		# We can't process the warp instructions here because of the
		# copy-ifs - they need to emit a statement into the block
		# before creating a warp into another

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


def _build_statement(state, addr, instruction):
	opcode = instruction.opcode
	A_type = instruction.A_type

	# Internal opcodes are stable, so we may freely assume their order
	if opcode == ins.ISTC.opcode or opcode == ins.ISFC.opcode:
		return _build_copy_if_statement(state, addr, instruction)

	elif opcode <= ins.ISF.opcode:
		return _prepare_conditional_warp(state, addr, instruction)

	# Generic assignments - handle the ASSIGNMENT stuff below
	elif A_type == ins.T_DST or A_type == ins.T_UV:
		return _build_var_assignment(state, addr, instruction)

	# ASSIGNMENT starting from MOV and ending at KPRI

	elif opcode == ins.KNIL.opcode:
		return _build_knil(state, addr, instruction)

	# ASSIGNMENT starting from UGET and ending at USETP

	# SKIP UCL0 is handled below

	# ASSIGNMENT starting from FNEW and ending at GGET

	elif opcode == ins.GSET.opcode:
		return _build_global_assignment(state, addr, instruction)

	# ASSIGNMENT starting from TGETV and ending at TGETB

	elif opcode >= ins.TSETV.opcode and opcode <= ins.TSETB.opcode:
		return _build_table_assignment(state, addr, instruction)

	elif opcode == ins.TSETM.opcode:
		return _build_table_mass_assignment(state, addr, instruction)

	elif opcode >= ins.CALLM.opcode and opcode <= ins.CALLT.opcode:
		return _build_call(state, addr, instruction)

	elif opcode == ins.ITERC.opcode or opcode == ins.ITERN.opcode:
		return _prepare_iterator_warp(state, addr, instruction)

	elif opcode == ins.VARG.opcode:
		return _build_vararg(state, addr, instruction)

	elif opcode == ins.ISNEXT.opcode:
		return _build_unconditional_warp(state, addr, instruction)

	elif opcode >= ins.RETM.opcode and opcode <= ins.RET1.opcode:
		return _build_return(state, addr, instruction)

	elif opcode == ins.FORI.opcode:
		return _build_numeric_loop_warp_stub(state, addr, instruction)

	elif opcode >= ins.FORL.opcode and opcode <= ins.JFORL.opcode:
		return _build_numeric_loop_warp(state, addr, instruction)

	elif opcode >= ins.ITERL.opcode and opcode <= ins.JITERL.opcode:
		return _finalize_iterator_warp(state, addr, instruction)

	elif opcode >= ins.LOOP.opcode and opcode <= ins.JLOOP.opcode:
		# Noop
		return None

	else:
		assert opcode == ins.UCLO.opcode or opcode == ins.JMP.opcode
		return _build_jump_warp(state, addr, instruction)


def _prepare_conditional_warp(state, addr, instruction):
	if instruction.opcode >= ins.IST.opcode:
		expression = _build_unary_expression(state, addr, instruction)
	else:
		expression = _build_comparison_expression(state, addr, instruction)

	warp = nodes.ConditionalWarp()
	warp.condition = expression

	assert state.block.warp is None
	state.block.warp = warp


def _finalize_conditional_warp(state, addr, instruction):
	warp = state.block.warp
	assert isinstance(warp, nodes.ConditionalWarp)

	destination = get_jump_destination(addr, instruction)

	# A condition is inverted during the preparation phase above
	warp.false_target = state._warp_in_block(destination)
	warp.true_target = state._warp_in_block(addr + 1)

	# something or true or simply true
	if warp.false_target == warp.true_target:
		target = warp.false_target

		black_hole = nodes.BlackHole()
		black_hole.contents.append(warp.condition)

		state.block.contents.append(black_hole)

		warp = nodes.UnconditionalWarp()
		warp.type = nodes.UnconditionalWarp.T_FLOW
		warp.target = target

		state.block.warp = warp


def _build_copy_if_statement(state, addr, instruction):
	assignment = nodes.Assignment()
	destination = _build_slot(state, addr, instruction.A)

	expression = _build_slot(state, addr, instruction.CD)

	assignment.destinations.contents.append(destination)
	assignment.expressions.contents.append(expression)

	warp = nodes.ConditionalWarp()
	warp.condition = _build_unary_expression(state, addr, instruction)

	assert state.block.warp is None
	state.block.warp = warp

	return assignment


def _build_var_assignment(state, addr, instruction):
	opcode = instruction.opcode

	assignment = nodes.Assignment()

	# Unary assignment operators (A = op D)
	if opcode == ins.MOV.opcode			\
			or opcode == ins.NOT.opcode	\
			or opcode == ins.UNM.opcode	\
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
	destination.key = _build_literal(state, nodes.MULTRES())
	destination.table = _build_slot(state, addr, base - 1)

	assignment.destinations.contents = [destination]
	assignment.expressions.contents = [nodes.MULTRES()]

	return assignment


def _prepare_iterator_warp(state, addr, instruction):
	warp = nodes.IteratorWarp()

	base = instruction.A

	warp.controls.contents = [
		_build_slot(state, addr, base - 3),  # generator
		_build_slot(state, addr, base - 2),  # state
		_build_slot(state, addr, base - 1)  # control
	]

	last_slot = base + instruction.B - 2

	slot = base

	while slot <= last_slot:
		variable = _build_slot(state, addr - 1, slot)
		warp.variables.contents.append(variable)
		slot += 1

	assert state.block.warp is None
	state.block.warp = warp


def _finalize_iterator_warp(state, addr, instruction):
	warp = state.block.warp
	assert isinstance(warp, nodes.IteratorWarp)

	destination = get_jump_destination(addr, instruction)
	warp.way_out = state._warp_in_block(addr + 1)
	warp.body = state._warp_in_block(destination)


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


def _build_numeric_loop_warp_stub(state, addr, instruction):
	warp = nodes.UnconditionalWarp()
	warp.type = nodes.UnconditionalWarp.T_FLOW
	warp.target = state._warp_in_block(addr + 1)

	assert state.block.warp is None
	state.block.warp = warp


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

	assert state.block.warp is None
	state.block.warp = warp


def _build_jump_warp(state, addr, instruction):
	if state.block.warp is not None:
		return _finalize_conditional_warp(state, addr, instruction)
	else:
		return _build_unconditional_warp(state, addr, instruction)


def _build_unconditional_warp(state, addr, instruction):
	warp = nodes.UnconditionalWarp()

	opcode = instruction.opcode

	if opcode == ins.UCLO.opcode and instruction.CD == 0:
		# Not a jump
		return
	else:
		warp.type = nodes.UnconditionalWarp.T_JUMP
		destination = get_jump_destination(addr, instruction)
		warp.target = state._warp_in_block(destination)

	assert state.block.warp is None
	state.block.warp = warp


def _build_call_arguments(state, addr, instruction):
	base = instruction.A
	last_argument_slot = base + instruction.CD

	is_variadic = (instruction.opcode == ins.CALLM.opcode	\
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

	map_index = opcode - ins.ADDVN.opcode
	map_index %= 5
	map_index += ins.ADDVN.opcode

	operator.type = _BINARY_OPERATOR_MAP[map_index]

	if operator.type is None:
		assert opcode == ins.POW.opcode

		operator.type = nodes.BinaryOperator.T_POW

	if instruction.B_type == ins.T_VAR and instruction.CD_type == ins.T_VAR:
		operator.left = _build_slot(state, addr, instruction.B)
		operator.right = _build_slot(state, addr, instruction.CD)
	elif instruction.B_type == ins.T_VAR:
		operator.left = _build_slot(state, addr, instruction.B)
		operator.right = _build_numeric_constant(state, instruction.CD)
	else:
		assert instruction.CD_type == ins.T_VAR

		operator.right = _build_slot(state, addr, instruction.B)
		operator.left = _build_numeric_constant(state, instruction.CD)

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
		if i == 0 and value is None:
			i += 1
			continue

		record = nodes.TableRecord()
		record.key = _build_table_record_item(i)
		record.value = _build_table_record_item(value)

		node.records.contents.append(record)

		i += 1

	for key, value in table.dictionary:
		record = nodes.TableRecord()
		record.key = _build_table_record_item(key)
		record.value = _build_table_record_item(value)

		node.records.contents.append(record)

	return node


def _build_table_record_item(value):
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
	elif opcode == ins.ISEQN.opcode	or opcode == ins.ISNEN.opcode:
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
	if opcode == ins.ISFC.opcode			\
			or opcode == ins.ISF.opcode	\
			or opcode == ins.MOV.opcode:
		return variable

	operator = nodes.UnaryOperator()
	operator.operand = variable

	if opcode == ins.ISTC.opcode			\
			or opcode == ins.IST.opcode	\
			or opcode == ins.NOT.opcode:
		operator.type = nodes.UnaryOperator.T_NOT
	elif opcode == ins.UNM.opcode:
		operator.type = nodes.UnaryOperator.T_MINUS
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
