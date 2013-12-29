#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.util.indentedstream

import ljd.ast.nodes as nodes


def write(fd, ast):
	stream = ljd.util.indentedstream.IndentedStream(fd)

	assert isinstance(ast, nodes.FunctionDefinition)
	_write_code_block(stream, ast.block)


def _write_code_block(stream, node):
	assert isinstance(node, nodes.CodeBlock)

	for statement in node.statements:
		_write_statement(stream, statement)


def _write_statement(stream, node):
	if isinstance(node, nodes.Assignment):
		_write_assignment(stream, node)
	elif isinstance(node, nodes.If):
		_write_if(stream, node)
	elif isinstance(node, nodes.IteratorFor):
		_write_iterator_for(stream, node)
	elif isinstance(node, nodes.NumericFor):
		_write_numeric_for(stream, node)
	elif isinstance(node, nodes.RepeatUntil):
		_write_repeat_until(stream, node)
	elif isinstance(node, nodes.FunctionDefinition):
		_write_function_definition(stream, node)
	elif isinstance(node, nodes.Return):
		_write_return(stream, node)
	elif isinstance(node, nodes.Break):
		_write_return(stream, node)
	elif isinstance(node, nodes.FunctionCall):
		stream.start_line()
		_write_function_call(stream, node)
		stream.end_line()
	else:
		assert isinstance(node, nodes.While)

		_write_while(stream, node)


def _write_assignment(stream, node):
	assert isinstance(node, nodes.Assignment)

	stream.start_line()

	if node.type == node.T_LOCAL_DEFINITION:
		stream.write("local ")

	_write_variables_list(stream, node.destinations)

	stream.write(" = ")

	_write_expressions_list(stream, node.expressions)

	if stream.line_open:
		stream.end_line()


def _write_function_definition(stream, node):
	assert isinstance(node, nodes.FunctionDefinition)

	if node.name is not None:
		stream.start_line("function {0} (", node.name)
	else:
		stream.write("function (")

	_write_arguments_list(stream, node.arguments)

	stream.write(")")

	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.block)
	stream.close_block()

	stream.write_line("end")


def _write_variables_list(stream, node):
	assert isinstance(node, nodes.List)

	for variable in node.contents[:-1]:
		_write_variable_or_slot(stream, variable)
		stream.write(", ")

	_write_variable_or_slot(stream, node.contents[-1])


def _write_arguments_list(stream, node):
	assert isinstance(node, nodes.List)

	if node.contents == []:
		return

	for variable in node.contents[:-1]:
		_write_function_argument(stream, variable)
		stream.write(", ")

	_write_function_argument(stream, node.contents[-1])


def _write_expressions_list(stream, node):
	assert isinstance(node, nodes.List)

	if node.contents == []:
		return

	for variable in node.contents[:-1]:
		_write_expression(stream, variable)
		stream.write(", ")

	_write_expression(stream, node.contents[-1])


def _write_variable_or_slot(stream, node):
	if isinstance(node, nodes.Variable):
		_write_variable(stream, node)
	elif isinstance(node, nodes.TableElement):
		_write_table_element(stream, node)
	elif isinstance(node, nodes.MULTRES):
		_write_multres(stream, node)
	else:
		assert isinstance(node, nodes.Slot)
		_write_slot(stream, node)


def _write_function_argument(stream, node):
	if isinstance(node, nodes.Variable):
		_write_variable(stream, node)
	elif isinstance(node, nodes.Slot):
		_write_slot(stream, node)
	else:
		assert isinstance(node, nodes.Vararg)

		_write_vararg(stream, node)


def _write_expression(stream, node):
	if isinstance(node, nodes.FunctionCall):
		_write_function_call(stream, node)

	elif isinstance(node, nodes.Primitive):
		_write_primitive(stream, node)
	elif isinstance(node, nodes.Constant):
		_write_constant(stream, node)

	elif isinstance(node, nodes.FunctionDefinition):
		_write_function_definition(stream, node)

	elif isinstance(node, nodes.TableConstructor):
		_write_table_constructor(stream, node)

	elif isinstance(node, nodes.Vararg):
		_write_vararg(stream, node)

	elif isinstance(node, nodes.BinaryOperator):
		_write_binary_operator(stream, node)
	elif isinstance(node, nodes.UnaryOperator):
		_write_unary_operator(stream, node)

	elif isinstance(node, nodes.MULTRES):
		_write_multres(stream, node)

	else:
		_write_variable_alike(stream, node)


def _write_function_call(stream, node):
	assert isinstance(node, nodes.FunctionCall)

	_write_variable_alike(stream, node.function)

	stream.write("(")

	_write_expressions_list(stream, node.arguments)

	stream.write(")")


def _write_primitive(stream, node):
	assert isinstance(node, nodes.Primitive)

	if node.type == nodes.Primitive.T_FALSE:
		stream.write("false")
	elif node.type == nodes.Primitive.T_TRUE:
		stream.write("true")
	else:
		assert node.type == nodes.Primitive.T_NIL

		stream.write("nil")


def _write_constant(stream, node):
	assert isinstance(node, nodes.Constant)

	if node.type == nodes.Constant.T_FLOAT:
		stream.write(node.value)
	elif node.type == nodes.Constant.T_INTEGER:
		stream.write(node.value)
	else:
		assert node.type == nodes.Constant.T_STRING

		if "\n" in node.value:
			stream.start_line()
			stream.write("[[")
			stream.write(node.value)
			stream.write("]]")
			stream.end_line()
		else:
			stream.write('"' + node.value + '"')


def _write_table_constructor(stream, node):
	assert isinstance(node, nodes.TableConstructor)

	stream.write("{")
	stream.end_line()

	stream.open_block()

	_write_table_records_list(stream, node.records)

	stream.close_block()

	stream.write_line("}")


def _write_table_records_list(stream, node):
	assert isinstance(node, nodes.List)

	if node.contents == []:
		return

	for record in node.contents[:-1]:
		stream.start_line()

		_write_table_record(stream, record)

		stream.write(",")
		stream.end_line()

	stream.start_line()
	_write_table_record(stream, node.contents[-1])
	stream.end_line()


def _write_table_record(stream, node):
	assert isinstance(node, nodes.TableRecord)

	stream.write("[")

	_write_expression(stream, node.key)

	stream.write("] = ")

	_write_expression(stream, node.value)


def _write_variable_alike(stream, node):
	if isinstance(node, nodes.Variable) or isinstance(node, nodes.Slot):
		_write_variable_or_slot(stream, node)
	else:
		assert isinstance(node, nodes.TableElement)
		_write_table_element(stream, node)


def _write_table_element(stream, node):
	assert isinstance(node, nodes.TableElement)

	_write_expression(stream, node.table)

	stream.write("[")

	_write_expression(stream, node.key)

	stream.write("]")


def _write_vararg(stream, node):
	assert isinstance(node, nodes.Vararg)

	stream.write("...")


def _write_binary_operator(stream, node):
	assert isinstance(node, nodes.BinaryOperator)

	stream.write("(")

	_write_expression(stream, node.left)

	stream.write(")")

	if node.operator == nodes.BinaryOperator.T_LOGICAL_OR:
		stream.write(" or ")
	elif node.operator == nodes.BinaryOperator.T_LOGICAL_AND:
		stream.write(" and ")

	elif node.operator == nodes.BinaryOperator.T_LESS_THEN:
		stream.write(" < ")
	elif node.operator == nodes.BinaryOperator.T_GREATER_THEN:
		stream.write(" > ")
	elif node.operator == nodes.BinaryOperator.T_LESS_OR_EQUAL:
		stream.write(" <= ")
	elif node.operator == nodes.BinaryOperator.T_GREATER_OR_EQUAL:
		stream.write(" >= ")

	elif node.operator == nodes.BinaryOperator.T_NOT_EQUAL:
		stream.write(" ~= ")
	elif node.operator == nodes.BinaryOperator.T_EQUAL:
		stream.write(" == ")

	elif node.operator == nodes.BinaryOperator.T_CONCAT:
		stream.write(" .. ")

	elif node.operator == nodes.BinaryOperator.T_ADD:
		stream.write(" + ")
	elif node.operator == nodes.BinaryOperator.T_SUBTRACT:
		stream.write(" - ")

	elif node.operator == nodes.BinaryOperator.T_DIVISION:
		stream.write("/")
	elif node.operator == nodes.BinaryOperator.T_MULTIPLY:
		stream.write("*")
	elif node.operator == nodes.BinaryOperator.T_MOD:
		stream.write("%")

	elif node.operator == nodes.BinaryOperator.T_POW:
		stream.write("^")
	else:
		assert node.operator == nodes.BinaryOperator.T_SUBTRACT
		stream.write(" - ")

	stream.write("(")

	_write_expression(stream, node.right)

	stream.write(")")


def _write_unary_operator(stream, node):
	assert isinstance(node, nodes.UnaryOperator)

	if node.operator == nodes.UnaryOperator.T_LENGTH_OPERATOR:
		stream.write("#")
	elif node.operator == nodes.UnaryOperator.T_MINUS:
		stream.write("-")
	elif node.operator == nodes.UnaryOperator.T_NOT:
		stream.write("not ")

	stream.write("(")

	_write_expression(stream, node.operand)

	stream.write(")")


def _write_break(stream, node):
	assert isinstance(node, nodes.Break)

	stream.write_line("break")


def _write_if(stream, node):
	assert isinstance(node, nodes.If)

	stream.start_line()
	stream.write("if ")
	_write_expression(stream, node.expression)
	stream.write(" then")
	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.then_block)
	stream.close_block()

	for elseif in node.elseifs:
		_write_elseif(stream, elseif)

	stream.write_line("else")

	stream.open_block()
	_write_code_block(stream, node.else_block)
	stream.close_block()

	stream.write_line("end")


def _write_elseif(stream, node):
	assert isinstance(node, nodes.ElseIf)

	stream.start_line()

	stream.write("elseif ")
	_write_expression(stream, node.expression)
	stream.write(" then")

	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.then_block)
	stream.close_block()


def _write_iterator_for(stream, node):
	assert isinstance(node, nodes.IteratorFor)

	stream.start_line()

	stream.write("for ")
	_write_expressions_list(stream, node.expressions)
	stream.write(" in ")
	_write_expressions_list(stream, node.variables)
	stream.write(" do")

	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.block)
	stream.close_block()

	stream.write_line("end")


def _write_numeric_for(stream, node):
	assert isinstance(node, nodes.NumericFor)

	stream.start_line()

	stream.write("for ")

	_write_variable_or_slot(stream, node.variable)

	stream.write(" = ")

	_write_expressions_list(stream, node.expressions)

	stream.write(" do")

	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.block)
	stream.close_block()

	stream.write_line("end")


def _write_multres(stream, node):
	assert isinstance(node, nodes.MULTRES)

	stream.write("MULTRES")


def _write_repeat_until(stream, node):
	assert isinstance(node, nodes.RepeatUntil)

	stream.write_line("repeat")

	stream.open_block()
	_write_code_block(stream, node.block)
	stream.close_block()

	stream.start_line()

	stream.write("until ")
	_write_expression(stream, node.expression)

	stream.end_line()


def _write_while(stream, node):
	assert isinstance(node, nodes.While)

	stream.start_line()
	stream.write("while ")
	_write_expression(stream, node.expression)
	stream.write(" do")
	stream.end_line()

	stream.open_block()
	_write_code_block(stream, node.block)
	stream.close_block()

	stream.write_line("done")


def _write_return(stream, node):
	assert isinstance(node, nodes.Return)

	stream.start_line()

	stream.write("return ")

	_write_expressions_list(stream, node.returns)

	stream.end_line()


def _write_slot(stream, node):
	assert isinstance(node, nodes.Slot)

	stream.write("slot{0}", node.number)


def _write_variable(stream, node):
	assert isinstance(node, nodes.Variable)

	stream.write(node.name)
