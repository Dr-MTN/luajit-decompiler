#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.bytecode.instructions as ins
from ljd.bytecode.constants import T_NIL, T_FALSE, T_TRUE

import ljd.ast.nodes as nodes


class _State():
	def __init__(self):
		self.constants = None
		self.debuginfo = None
		self.instructions = []
		self.layers = []

	def _is_opcode_at_addr(self, addr, opcode):
		try:
			return self.instructions[addr].opcode == opcode
		except IndexError:
			return False

	def _get_addr(self, addr):
		return self.instructions[addr]


class _Layer():
	def __init__(self, node, block, block_start, block_end):
		self.node = node
		self.block = block
		self.block_start = block_start
		self.block_end = block_end


def build(prototype):
	return _build_function_definition(prototype)


def _build_function_definition(prototype):
	node = nodes.FunctionDefinition()

	state = _State()

	state.constants = prototype.constants
	state.debuginfo = prototype.debuginfo

	node.arguments.contents = _build_function_arguments(state, prototype)

	if prototype.flags.is_variadic:
		node.arguments.contents.append(nodes.Vararg())

	layer = _Layer(node, node.block.contents, 1, len(prototype.instructions))
	state.layers.append(layer)

	_process_function_body(state, prototype.instructions)

	state.layers.pop()

	assert state.layers == []

	return node


def _build_function_arguments(state, prototype):
	arguments = []

	count = prototype.arguments_count

	slot = 0
	while slot < count:
		variable = _build_variable(state, 0, slot)

		arguments.append(variable)
		slot += 1

	return arguments


OP_NEXT = 0
OP_KEEP = 1

OP_PUSH_STATE = 0
OP_POP_STATE = 1
OP_KEEP_STATE = 2


_MAX_LOOKAHEAD = 2


def _process_function_body(state, instructions):
	funcs = [_process_code_block]

	addr = 1
	state.instructions = instructions

	while addr < len(instructions):
		op, func = funcs[-1](state, addr, instructions[addr])

		assert func is not None

		if func == OP_KEEP_STATE:
			pass
		elif isinstance(func, tuple):
			assert func[0] == OP_PUSH_STATE
			funcs.append(func[1])
		elif func == OP_POP_STATE:
			funcs.pop()
		else:
			funcs[-1] = func

		if isinstance(op, tuple):
			assert op[0] == OP_NEXT
			step = op[1]
			op = op[0]
		else:
			step = 1

		if op == OP_NEXT:
			line = state.debuginfo.lookup_line_number(addr)

			block = state.layers[-1].block

			if block == []:
				block = state.layers[-2].block

			setattr(block[-1], "_line", line)

			assert state.layers[-1].block_end < 0		\
					or addr < state.layers[-1].block_end

			addr += step
		else:
			assert op == OP_KEEP


def _process_code_block(state, addr, instruction):
	opcode = instruction.opcode
	A_type = instruction.A_type

	# internal opcodes are stable, so we may freely assume their order

	if opcode <= ins.ISF.opcode	\
			and state._is_opcode_at_addr(addr + 2, ins.LOOP.opcode):
		return _process_while(state, addr, instruction)

	# Comparison operators (if something)
	elif opcode <= ins.ISNEP.opcode:
		expression = _build_comparison_expression(state, addr, instruction)
		return _process_if_statement(state, addr, expression)

	# Unary test and copy operators ([A = D;] if D)
	elif opcode == ins.IST.opcode			\
			or opcode == ins.ISF.opcode:
		expression = _build_unary_expression(state, addr, instruction)
		return _process_if_statement(state, addr, expression)

	#
	# The copy-if operators plus obfuscated if true/if false:
	# it's replaced with a single JMP without a condition
	# Hopefully it's always preceeded by KPRI
	#
	elif opcode == ins.ISTC.opcode			\
			or opcode == ins.ISFC.opcode	\
			or (opcode == ins.KPRI.opcode	\
				and state._is_opcode_at_addr(addr + 1,
								ins.JMP.opcode)):
		return _process_copy_if_statement(state, addr, instruction)

	# Generic assignments - handle ASSIGNMENT stuff
	elif A_type == ins.T_DST or A_type == ins.T_UV:
		return _process_var_assignment(state, addr, instruction)

	# ASSIGNMENT starting from MOV and ending at KPRI

	elif opcode == ins.KNIL.opcode:
		return _process_knil(state, addr, instruction)

	# ASSIGNMENT starting from KSTR and ending at USETP

	# SKIP UCL0 is handled below

	# ASSIGNMENT starting from FNEW and ending at GGET

	elif opcode == ins.GSET.opcode:
		return _process_global_assignment(state, addr, instruction)

	# ASSIGNMENT starting from TGETV and ending at TGETB

	elif opcode >= ins.TSETV.opcode and opcode <= ins.TSETB.opcode:
		return _process_table_assignment(state, addr, instruction)

	elif opcode == ins.TSETM.opcode:
		return _process_table_mass_assignment(state, addr, instruction)

	elif opcode >= ins.CALLM.opcode and opcode <= ins.CALLT.opcode:
		return _process_call(state, addr, instruction)

	# SKIP ITERC and ITERN - handle at iterator_for

	elif opcode == ins.VARG.opcode:
		return _process_vararg(state, addr, instruction)

	elif opcode == ins.ISNEXT.opcode:
		return _process_iterator_for(state, addr, instruction)

	elif opcode >= ins.RETM.opcode and opcode <= ins.RET1.opcode:
		return _process_return(state, addr, instruction)

	elif opcode == ins.FORI.opcode or opcode == ins.FORL.opcode:
		return _process_numeric_for(state, addr, instruction)

	elif opcode >= ins.LOOP.opcode and opcode <= ins.JLOOP.opcode:
		return _process_repeat_until(state, addr, instruction)

	else:
		assert opcode == ins.UCLO.opcode or opcode == ins.JMP.opcode
		return _process_jump(state, addr, instruction)


def _process_if_statement(state, addr, expression):
	node = nodes.If()

	node.expression = expression

	layer = _Layer(node, node.then_block.contents, addr, -1)

	state.layers[-1].block.append(node)
	state.layers.append(layer)

	return OP_NEXT, (OP_PUSH_STATE, _process_if_body_start)


def _process_if_body_start(state, addr, instruction):
	assert instruction.opcode == ins.JMP.opcode

	state.layers[-1].block_end = _get_jump_destination(addr, instruction)

	return OP_NEXT, _process_if_body


def _process_if_body(state, addr, instruction):
	# jump outside of the if - block end and start of else block
	if instruction.opcode == ins.JMP.opcode			\
			and addr == state.layers[-1].block_end - 1:
		layer = state.layers.pop()

		block_end = _get_jump_destination(addr, instruction)

		layer = _Layer(layer.node, layer.node.else_block.contents,
								addr, block_end)

		state.layers.append(layer)
		return OP_NEXT, _process_if_body

	if addr < state.layers[-1].block_end:
		return _process_code_block(state, addr, instruction)

	state.layers.pop()
	return OP_KEEP, OP_POP_STATE


def _process_copy_if_statement(state, addr, instruction):
	assignment = nodes.Assignment()
	destination = _build_destination(state, addr, instruction.A)

	if instruction.opcode == ins.KPRI.opcode:
		expression = _build_primitive(state, instruction.CD)
	else:
		expression = _build_variable(state, addr, instruction.CD)

	assignment.destinations.contents.append(destination)
	assignment.expressions.contents.append(expression)

	varinfo = destination._varinfo

	if varinfo is not None and varinfo.start_addr == addr:
		assignment.type = nodes.Assignment.T_LOCAL_DEFINITION
	else:
		assignment.type = nodes.Assignment.T_NORMAL

	state.layers[-1].block.append(assignment)

	if instruction.opcode == ins.KPRI.opcode:
		expression = _build_primitive_to_bool_expression(state, addr,
								instruction)
	else:
		expression = _build_unary_expression(state, addr, instruction)

	return _process_if_statement(state, addr, expression)


def _process_var_assignment(state, addr, instruction):
	opcode = instruction.opcode

	assignment = nodes.Assignment()

	if instruction.A_type == ins.T_DST:
		destination = _build_destination(state, addr, instruction.A)
	else:
		assert instruction.A_type == ins.T_UV

		destination = _build_upvalue(state, addr, instruction.A)

	assignment.destinations.contents.append(destination)

	varinfo = destination._varinfo

	if varinfo is not None and varinfo.start_addr == addr + 1:
		assignment.type = nodes.Assignment.T_LOCAL_DEFINITION
	else:
		assignment.type = nodes.Assignment.T_NORMAL

	state.layers[-1].block.append(assignment)

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
		expression = _build_variable(state, addr, instruction.CD)

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

	return OP_NEXT, OP_KEEP_STATE


def _process_knil(state, addr, instruction):
	node = _build_range_assignment(state, addr, instruction.A, instruction.CD)

	node.expressions.contents = [_build_primitive(state, None)]

	state.layers[-1].block.append(node)

	return OP_NEXT, OP_KEEP_STATE


def _process_global_assignment(state, addr, instruction):
	assignment = nodes.Assignment()

	variable = _build_global_variable(state, addr, instruction.CD)
	expression = _build_variable(state, addr, instruction.A)

	assignment.destinations.contents.append(variable)
	assignment.expressions.contents.append(expression)
	assignment.type = nodes.Assignment.T_NORMAL

	state.layers[-1].block.append(assignment)

	return OP_NEXT, OP_KEEP_STATE


def _process_table_assignment(state, addr, instruction):
	assignment = nodes.Assignment()

	destination = _build_table_element(state, addr, instruction)
	expression = _build_variable(state, addr, instruction.A)

	assignment.destinations.contents.append(destination)
	assignment.expressions.contents.append(expression)

	assignment.type = nodes.Assignment.T_NORMAL

	state.layers[-1].block.append(assignment)

	return OP_NEXT, OP_KEEP_STATE


def _process_table_mass_assignment(state, addr, instruction):
	assignment = nodes.Assignment()

	base = instruction.A

	start = int(state.constants.numeric_constants[instruction.CD])

	destination = nodes.TableElement()
	destination.key = _build_literal(state, start)
	destination.table = _build_variable(state, addr, base - 1)

	assignment.destinations.contents = [
		destination,
		nodes.MULTRES()
	]

	assignment.expressions.contents = [
		_build_variable(state, addr, base),
		nodes.MULTRES()
	]

	assignment.type = nodes.Assignment.T_NORMAL

	state.layers[-1].block.append(assignment)

	return OP_NEXT, OP_KEEP_STATE


def _process_iterator_for(state, addr, instruction):
	node = nodes.IteratorFor()

	# JMP points to the ITERC, but there is the ITERL instruction next to
	# it
	block_end = _get_jump_destination(addr, instruction) + 2
	layer = _Layer(node, node.block.contents, addr, block_end)

	state.layers[-1].block.append(node)
	state.layers.append(layer)

	return OP_NEXT, (OP_PUSH_STATE, _process_iterator_for_body)


def _process_iterator_for_body(state, addr, instruction):
	opcode = instruction.opcode

	if opcode == ins.ITERC.opcode or opcode == ins.ITERN.opcode:
		node = state.layers[-1].node

		base = instruction.A

		# These are the temporary slots with weird local names
		# Ignore the names - we will squash them later at
		# the optimization phase
		node.expressions.contents = [
			_build_slot(state, addr, base - 3),  # generator
			_build_slot(state, addr, base - 2),  # state
			_build_slot(state, addr, base - 1)  # control
		]

		last_slot = base + instruction.B - 2

		slot = base
		while slot <= last_slot:
			# variables scope is up to this instruction
			variable = _build_variable(state, addr - 1, slot)
			node.identifiers.contents.append(variable)
			slot += 1

		return OP_NEXT, OP_KEEP_STATE

	elif opcode == ins.ITERL.opcode			\
			or opcode == ins.IITERL.opcode	\
			or opcode == ins.JITERL.opcode:
		state.layers.pop()
		return OP_NEXT, OP_POP_STATE

	return _process_code_block(state, addr, instruction)


def _process_call(state, addr, instruction):
	call = nodes.FunctionCall()

	if instruction.opcode <= ins.CALL.opcode:
		if instruction.B == 0:
			node = nodes.Assignment()
			node.destinations.contents.append(nodes.MULTRES())
			node.expressions.contents.append(call)
			node.type = nodes.Assignment.T_NORMAL
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

	call.function = _build_variable(state, addr, instruction.A)

	call.arguments.contents = _build_call_arguments(state, addr, instruction)

	state.layers[-1].block.append(node)

	return OP_NEXT, OP_KEEP_STATE


def _process_vararg(state, addr, instruction):
	base = instruction.A
	last_slot = base + instruction.B - 2

	if last_slot < base:
		node = nodes.Assignment()
		node.type = nodes.Assignment.T_NORMAL
		node.destinations.contents.append(nodes.MULTRES())
		node.expressions.contents.append(nodes.Vararg())
	else:
		node = _build_range_assignment(state, addr, base, last_slot)
		node.expressions.contents.append(nodes.Vararg())

	state.layers[-1].block.append(node)

	return OP_NEXT, OP_KEEP_STATE


def _process_return(state, addr, instruction):
	node = nodes.Return()

	base = instruction.A
	last_slot = base + instruction.CD - 1

	if instruction.opcode != ins.RETM.opcode:
		last_slot -= 1

	slot = base

	# Negative count for the RETM is OK
	while slot <= last_slot:
		variable = _build_variable(state, addr, slot)
		node.returns.contents.append(variable)
		slot += 1

	if instruction.opcode == ins.RETM.opcode:
		node.returns.contents.append(nodes.MULTRES())

	state.layers[-1].block.append(node)

	return OP_NEXT, OP_KEEP_STATE


def _process_numeric_for(state, addr, instruction):
	node = nodes.NumericFor()

	base = instruction.A

	node.variable = _build_variable(state, addr, base + 3)
	node.expressions.contents = [
		_build_variable(state, addr, base + 2),
		_build_variable(state, addr, base + 1),
		_build_variable(state, addr, base + 0)
	]

	state.layers[-1].block.append(node)

	block_end = _get_jump_destination(addr, instruction)
	layer = _Layer(node, node.block.contents, addr, block_end)

	state.layers.append(layer)

	return OP_NEXT, (OP_PUSH_STATE, _process_numeric_for_body)


def _process_numeric_for_body(state, addr, instruction):
	opcode = instruction.opcode

	if opcode == ins.FORL.opcode 			\
			or opcode == ins.JFORL.opcode	\
			or opcode == ins.IFORL.opcode:
		state.layers.pop()
		return OP_NEXT, OP_POP_STATE

	return _process_code_block(state, addr, instruction)


def _process_repeat_until(state, addr, instruction):
	node = nodes.RepeatUntil()

	state.layers[-1].block.append(node)

	#
	# In case of the LJOOP the D operand is a JIT trace, not a jump
	# destination - so we can't use it to detect the block end
	#
	# We will have to use the lookahead to detect any comparison instruction
	# with the following jump back to the block end
	#
	layer = _Layer(node, node.block.contents, addr, -1)
	state.layers.append(layer)

	return OP_NEXT, (OP_PUSH_STATE, _process_repeat_until_body)


def _process_repeat_until_body(state, addr, instruction):
	next_instruction = state._get_addr(addr + 1)
	node = state.layers[-1].node

	if next_instruction.opcode != ins.JMP.opcode:
		return _process_code_block(state, addr, instruction)

	# This is the next instruction, so addr should be incremented as well
	destination = _get_jump_destination(addr + 1, next_instruction)

	if destination != state.layers[-1].block_start:
		return _process_code_block(state, addr, instruction)

	node.block_end = addr + 1
	opcode = instruction.opcode

	assert opcode <= ins.ISF.opcode

	#
	# Not supported. Shouldn't actually happen, but who knows...
	#
	# It's easy to support the assignment if as well, but the code is
	# already complex enough and there is no solid evidence that such
	# a thing may ever happen
	#
	assert opcode != ins.ISTC.opcode and opcode != ins.ISFC.opcode

	if opcode >= ins.IST.opcode:
		expression = _build_unary_expression(state, addr, instruction)
	else:
		expression = _build_comparison_expression(state, addr, instruction)

	node.expression = expression

	state.layers.pop()

	# See the commentary within the _process_while_body function
	return (OP_NEXT, 2), OP_POP_STATE


def _process_while(state, addr, instruction):
	node = nodes.While()

	opcode = instruction.opcode

	# Not supported. Same as above
	assert opcode != ins.ISTC.opcode and opcode != ins.ISFC.opcode

	if opcode >= ins.IST.opcode:
		expression = _build_unary_expression(state, addr, instruction)
	else:
		expression = _build_comparison_expression(state, addr, instruction)

	node.expression = expression

	state.layers[-1].block.append(node)

	# Lookahead JMP instruction
	block_end = _get_jump_destination(addr + 1, state._get_addr(addr + 1))

	layer = _Layer(node, node.block.contents, addr, block_end)

	state.layers.append(layer)

	#
	# We could use an another statement to skip the first two instruction,
	# but...
	#
	# That's not real FSM anyway, so who cares if we will make a tiny
	# shortcut here? =)
	#
	return (OP_NEXT, 3), (OP_PUSH_STATE, _process_while_body)


def _process_while_body(state, addr, instruction):
	block_end = state.layers[-1].block_end

	# Jump to the while condition start
	if instruction.opcode == ins.JMP.opcode and addr == block_end - 1:
		state.layers.pop()
		return OP_NEXT, OP_POP_STATE

	return _process_code_block(state, addr, instruction)


def _process_jump(state, addr, instruction):
	destination = _get_jump_destination(addr, instruction)

	if instruction.opcode == ins.UCLO.opcode and instruction.CD == 0:
		return OP_NEXT, OP_KEEP_STATE

	target_opcode = state._get_addr(destination).opcode

	if target_opcode == ins.ITERN.opcode or target_opcode == ins.ITERC.opcode:
		return _process_iterator_for(state, addr, instruction)

	pre_target = state._get_addr(destination - 1)

	assert pre_target.opcode in (
			ins.IFORL.opcode,
			ins.JFORL.opcode,
			ins.FORL.opcode,
			ins.ITERL.opcode,
			ins.JITERL.opcode,
			ins.IITERL.opcode
	) or (pre_target.opcode == ins.JMP.opcode and pre_target.CD < 0), 	\
		"GOTO statements are not supported (yet)"

	state.layers[-1].block.append(nodes.Break())

	return OP_NEXT, OP_KEEP_STATE


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
		argument = _build_variable(state, addr, slot)
		arguments.append(argument)
		slot += 1

	if is_variadic:
		arguments.append(nodes.MULTRES())

	return arguments


def _build_range_assignment(state, addr, from_slot, to_slot):
	assignment = nodes.Assignment()

	slot = from_slot

	is_local = True

	assert from_slot <= to_slot

	while slot <= to_slot:
		destination = _build_destination(state, addr, slot)

		varinfo = destination._varinfo

		if is_local and (varinfo is None or			\
					varinfo.start_addr != addr + 1):
			is_local = False

		assignment.destinations.contents.append(destination)

		slot += 1

	if is_local:
		assignment.type = nodes.Assignment.T_LOCAL_DEFINITION
	else:
		assignment.type = nodes.Assignment.T_NORMAL

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
		operator.left = _build_variable(state, addr, instruction.B)
		operator.right = _build_variable(state, addr, instruction.CD)
	elif instruction.B_type == ins.T_VAR:
		operator.left = _build_variable(state, addr, instruction.B)
		operator.right = _build_numeric_constant(state, instruction.CD)
	else:
		assert instruction.CD_type == ins.T_VAR

		operator.right = _build_variable(state, addr, instruction.B)
		operator.left = _build_numeric_constant(state, instruction.CD)

	return operator


def _build_concat_expression(state, addr, instruction):
	operator = nodes.BinaryOperator()
	operator.type = nodes.BinaryOperator.T_CONCAT

	slot = instruction.B

	operator.left = _build_variable(state, addr, slot)
	operator.right = _build_variable(state, addr, slot + 1)

	slot += 2

	while slot <= instruction.CD:
		upper_operator = nodes.BinaryOperator()
		upper_operator.left = operator
		upper_operator.right = _build_variable(state, addr, slot)
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
	elif CD_type == ins.T_LIT or CD_type == ins.T_SLIT:
		return _build_literal(state, instruction.CD)
	elif CD_type == ins.T_NUM:
		return _build_numeric_constant(state, instruction.CD)
	else:
		assert CD_type == ins.T_PRI
		return _build_primitive(state, instruction.CD)


def _build_table_element(state, addr, instruction):
	node = nodes.TableElement()
	node.table = _build_variable(state, addr, instruction.B)

	if instruction.CD_type == ins.T_VAR:
		node.key = _build_variable(state, addr, instruction.CD)
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
			continue

		record = nodes.TableRecord()
		record.key = _build_table_record_item(i)
		record.value = _build_table_record_item(value)

		node.records.contents.append(record)

		i += 1

	for key, value in table.dictionary.items():
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


def _get_jump_destination(addr, instruction):
	return addr + instruction.CD + 1


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

	operator.left = _build_variable(state, addr, instruction.A)

	opcode = instruction.opcode

	if opcode == ins.ISEQS.opcode or opcode == ins.ISNES.opcode:
		operator.right = _build_string_constant(state, instruction.CD)
	elif opcode == ins.ISEQN.opcode	or opcode == ins.ISNEN.opcode:
		operator.right = _build_numeric_constant(state, instruction.CD)
	elif opcode == ins.ISEQP.opcode or opcode == ins.ISNEP.opcode:
		operator.right = _build_primitive(state, addr, instruction.CD)
	else:
		operator.right = _build_variable(state, addr, instruction.CD)

	operator.type = _COMPARISON_MAP[instruction.opcode]
	assert operator.type is not None

	return operator


def _build_primitive_to_bool_expression(state, addr, instruction):
	value = instruction.CD

	variable = _build_variable(state, addr, instruction.A)

	if value == T_TRUE:
		return variable

	node = nodes.UnaryOperator()
	node.type = nodes.UnaryOperator.T_NOT
	node.operand = variable

	return node


def _build_unary_expression(state, addr, instruction):
	opcode = instruction.opcode

	variable = _build_variable(state, addr, instruction.CD)

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
	elif opcode == ins.LEN.opcode:
		operator.type = nodes.UnaryOperator.T_LENGTH_OPERATOR

	return operator


def _build_destination(state, addr, slot):
	return _build_variable(state, addr + 1, slot)


def _build_variable(state, addr, slot):
	return _build_identifier(state, addr, slot, nodes.Identifier.T_LOCAL)


def _build_upvalue(state, addr, slot):
	return _build_identifier(state, addr, slot, nodes.Identifier.T_UPVALUE)


def _build_slot(state, addr, slot):
	return _build_identifier(state, addr, slot, nodes.Identifier.T_SLOT)


def _build_identifier(state, addr, slot, want_type):
	node = nodes.Identifier()
	node.slot = slot
	node.type = nodes.Identifier.T_SLOT

	if want_type == nodes.Identifier.T_LOCAL:
		info = state.debuginfo.lookup_local_name(addr, slot)
		node._varinfo = info

		if info is not None and info.type != info.T_INTERNAL:
			node.type = want_type
			node.name = info.name
	elif want_type == nodes.Identifier.T_UPVALUE:
		name = state.debuginfo.lookup_upvalue_name(slot)

		if name is not None:
			node.name = info.name
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

	if value == True or value == T_TRUE:
		node.type = nodes.Primitive.T_TRUE
	elif value == False or value == T_FALSE:
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
