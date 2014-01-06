#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


CMD_START_STATEMENT = 0
CMD_END_STATEMENT = 1
CMD_END_LINE = 3
CMD_START_BLOCK = 4
CMD_END_BLOCK = 5
CMD_WRITE = 6


OPERATOR_TYPES = (nodes.BinaryOperator, nodes.UnaryOperator)


class Visitor(traverse.Visitor):
	def __init__(self, warped):
		traverse.Visitor.__init__(self)

		self.visited_nodes_stack = [set()]

		self.print_queue = []
		self.warped = True

	# ##

	def _start_statement(self):
		self.print_queue.append((CMD_START_STATEMENT,))

	def _end_statement(self):
		self.print_queue.append((CMD_END_STATEMENT,))

	def _end_line(self):
		self.print_queue.append((CMD_END_LINE,))

	def _start_block(self):
		self.print_queue.append((CMD_START_BLOCK,))

	def _end_block(self):
		self.print_queue.append((CMD_END_BLOCK,))

	def _write(self, fmt, *args, **kargs):
		self.print_queue.append((CMD_WRITE, fmt, args, kargs))

	# ##

	def visit_function_definition(self, node):
		if node.name is not None:
			self._start_statement()

			self._write("function {0} (", node.name)
		else:
			self._write("function (")

		self._visit(node.arguments)

		self._write(")")

		self._end_line()

		self._start_block()

		self._visit(node.statements)

		self._end_block()

		self._write("end")

		if node.name is not None:
			self._end_statement()

	# ##

	def visit_table_constructor(self, node):
		self._write("{")

		self._end_line()

		self._start_block()

		self._visit(node.records)

		self._end_block()

		self._write("}")

		self._end_line()

	def visit_table_record(self, node):
		# TODO: Check if the key expression is a string constant or
		# a concat type
		self._write("[")

		self._visit(node.key)

		self._write("] = ")

		self._visit(node.value)

	# ##

	def visit_assignment(self, node):
		self._start_statement()

		if node.type == node.T_LOCAL_DEFINITION:
			self._write("local ")

		self._visit(node.destinations)

		self._write(" = ")

		self._visit(node.expressions)

		self._end_statement()

	# ##

	def visit_binary_operator(self, node):
		is_left_op = isinstance(node.left, OPERATOR_TYPES)
		is_right_op = isinstance(node.right, OPERATOR_TYPES)

		# If the subexpressions are less in order then this expression,
		# they should go with parentheses
		left_parentheses = is_left_op and node.left.type < node.type
		right_parentheses = is_right_op and node.right.type < node.type

		if left_parentheses:
			self._write("(")

		self._visit(node.left)

		if left_parentheses:
			self._write(")")

		if node.type == nodes.BinaryOperator.T_LOGICAL_OR:
			self._write(" or ")
		elif node.type == nodes.BinaryOperator.T_LOGICAL_AND:
			self._write(" and ")

		elif node.type == nodes.BinaryOperator.T_LESS_THEN:
			self._write(" < ")
		elif node.type == nodes.BinaryOperator.T_GREATER_THEN:
			self._write(" > ")
		elif node.type == nodes.BinaryOperator.T_LESS_OR_EQUAL:
			self._write(" <= ")
		elif node.type == nodes.BinaryOperator.T_GREATER_OR_EQUAL:
			self._write(" >= ")

		elif node.type == nodes.BinaryOperator.T_NOT_EQUAL:
			self._write(" ~= ")
		elif node.type == nodes.BinaryOperator.T_EQUAL:
			self._write(" == ")

		elif node.type == nodes.BinaryOperator.T_CONCAT:
			self._write(" .. ")

		elif node.type == nodes.BinaryOperator.T_ADD:
			self._write(" + ")
		elif node.type == nodes.BinaryOperator.T_SUBTRACT:
			self._write(" - ")

		elif node.type == nodes.BinaryOperator.T_DIVISION:
			self._write("/")
		elif node.type == nodes.BinaryOperator.T_MULTIPLY:
			self._write("*")
		elif node.type == nodes.BinaryOperator.T_MOD:
			self._write("%")

		elif node.type == nodes.BinaryOperator.T_POW:
			self._write("^")
		else:
			self._write(" - ")

		if right_parentheses:
			self._write("(")

		self._visit(node.right)

		if right_parentheses:
			self._write(")")

	def visit_unary_operator(self, node):
		if node.type == nodes.UnaryOperator.T_LENGTH_OPERATOR:
			self._write("#")
		elif node.type == nodes.UnaryOperator.T_MINUS:
			self._write("-")
		elif node.type == nodes.UnaryOperator.T_NOT:
			self._write("not ")

		self._write("(")

		self._visit(node.operand)

		self._write(")")

	# ##

	def _visit_comma_separated_list(self, node):
		if node.contents == []:
			return

		for subnode in node.contents[:-1]:
			self._visit(subnode)
			self._write(", ")

		self._visit(node.contents[-1])

	visit_identifiers_list = _visit_comma_separated_list

	def visit_records_list(self, node):
		if node.contents == []:
			return

		for subnode in node.contents[:-1]:
			self._visit(subnode)

			self._write(", ")
			self._end_line()

		self._visit(node.contents[-1])
		self._end_line()

	visit_variables_list = _visit_comma_separated_list
	visit_expressions_list = _visit_comma_separated_list

	# ##

	def visit_identifier(self, node):
		if node.type == nodes.Identifier.T_SLOT:
			self._write("slot{0}", node.slot)
		else:
			self._write(node.name)

	def visit_multres(self, node):
		self._write("MULTRES")

	def visit_table_element(self, node):
		key = node.key
		base = node.table
		if isinstance(key, nodes.Constant) and key.type == key.T_STRING:
			if isinstance(base, nodes.Identifier)	\
					and base.type == base.T_BUILTIN:
				assert base.name == "_env"
				self._skip(base)
			else:
				self._visit(base)
				self._write(".")

			self._write(key.value)
			self._skip(key)
		else:
			self._visit(base)

			self._write("[")

			self._visit(key)

			self._write("]")

	def visit_vararg(self, node):
		self._write("...")

	def visit_function_call(self, node):
		self._start_statement()

		self._visit(node.function)

		self._write("(")

		self._visit(node.arguments)

		self._write(")")

		# HACK! Function call could be statement as
		# well as expression part
		self._end_statement()

	# ##

	def visit_if(self, node):
		self._start_statement()

		self._write("if ")

		self._visit(node.expression)

		self._write(" then")

		self._end_line()

		self._start_block()

		self._visit(node.then_block)

		self._end_block()

		self._visit_list(node.elseifs)

		self._write("else")

		self._end_line()

		self._start_block()

		self._visit(node.else_block)

		self._end_block()

		self._write("end")

		self._end_statement()

	def visit_elseif(self, node):
		self._write("elseif ")

		self._visit(node.expression)

		self._write(" then")

		self._end_line()

		self._start_block()

		self._visit(node.then_block)

		self._end_block()

	# ##

	def visit_block(self, node):
		self._write("--- BLOCK {0} {1}-{2}, warpins: {3} ---",
					node.__hash__(),
					node.first_address, node.last_address,
					node.warpins_count)

		self._end_line()

		self._start_block()

		self._visit_list(node.contents)

		self._end_block()

		self._write("--- END OF BLOCK {0} ---", node.__hash__())

		self._end_line()

		self._end_line()
		self._visit(node.warp)
		self._end_line()

		self._end_line()

	def visit_unconditional_warp(self, node):
		if node.type == nodes.UnconditionalWarp.T_FLOW:
			self._write("FLOW")
		elif node.type == nodes.UnconditionalWarp.T_JUMP:
			self._write("UNCONDITIONAL JUMP")

		self._write("; TARGET {0}", node.target.__hash__())

		self._end_line()

	def visit_conditional_warp(self, node):
		self._write("if ")

		self._visit(node.condition)

		self._write(" then")
		self._end_line()

		self._start_block()

		self._write("JUMP ")

		if node.type == nodes.ConditionalWarp.T_NEGATIVE_JUMP:
			self._write("BEHIND")
		else:
			self._write("AHEAD")

		self._write(" TO BLOCK {0}", node.true_target.__hash__())

		self._end_block()

		self._end_line()
		self._write("else")
		self._end_line()

		self._start_block()

		self._write("JUMP TO BLOCK {0}", node.false_target.__hash__())

		self._end_block()

		self._end_line()

		self._write("end")
		self._end_line()

	def visit_iterator_warp(self, node):
		self._write("for ")

		self._visit(node.variables)

		self._write(" in ")

		self._visit(node.controls)

		self._write(" LOOP BLOCK {0}", node.body.__hash__())
		self._end_line()

		self._write("GO OUT TO BLOCK {0}", node.way_out.__hash__())

	def visit_numeric_loop_warp(self, node):
		self._write("for ")

		self._visit(node.index)

		self._write("=")

		self._visit(node.controls)

		self._write(" LOOP BLOCK {0}", node.body.__hash__())
		self._end_line()

		self._write("GO OUT TO BLOCK {0}", node.way_out.__hash__())

	# ##

	def visit_return(self, node):
		self._start_statement()

		self._write("return ")

		self._visit(node.returns)

		self._end_statement()

	def visit_break(self, node):
		self._start_statement()

		self._write("break")

		self._end_statement()

	# ##

	def visit_while(self, node):
		self._start_statement()

		self._write("while ")
		self._visit(node.expression)
		self._write(" do")

		self._end_line()

		self._start_block()
		self._visit(node.block)
		self._end_block()

		self._write("end")
		self._end_statement()

	def visit_repeat_until(self, node):
		self._start_statement()

		self._write("repeat")
		self._end_line()

		self._start_block()
		self._visit(node.block)
		self._end_block()

		self._write("until ")
		self._visit(node.expression)

		self._end_statement()

	def visit_numeric_for(self, node):
		self._start_statement()

		self._write("for ")
		self._visit(node.variable)
		self._write(" = ")

		self._visit(node.expressions)

		self._write(" do")

		self._end_line()

		self._start_block()
		self._visit(node.block)
		self._end_block()

		self._write("end")
		self._end_statement()

	def visit_iterator_for(self, node):
		self._start_statement()

		self._write("for ")
		self._visit(node.identifiers)
		self._write(" in ")
		self._visit(node.expressions)
		self._write(" do")

		self._end_line()

		self._start_block()
		self._visit(node.block)
		self._end_block()

		self._write("end")
		self._end_statement()

	# ##

	def visit_constant(self, node):
		if node.type != nodes.Constant.T_STRING:
			self._write(node.value)
			return

		if "\n" in node.value:
			self._write("[[")

			self._end_line()

			self._write(node.value)
			self._write("]]")

			self._end_line()
		else:
			self._write('"' + node.value + '"')

	def visit_primitive(self, node):
		if node.type == nodes.Primitive.T_FALSE:
			self._write("false")
		elif node.type == nodes.Primitive.T_TRUE:
			self._write("true")
		else:
			self._write("nil")

	def _skip(self, node):
		self.visited_nodes_stack[-1].add(node)

	def _visit(self, node):
		assert node is not None

		if node in self.visited_nodes_stack[-1]:
			return

		# TODO: add check
		# "It looks like you forgot about some node changes..."

		self.visited_nodes_stack[-1].add(node)

		self.visited_nodes_stack.append(set())

		traverse.Visitor._visit(self, node)

		self.visited_nodes_stack.pop()


def write(fd, ast, warped=True):
	assert isinstance(ast, nodes.FunctionDefinition)

	visitor = Visitor(warped)

	traverse.traverse(visitor, ast.statements)

	_process_queue(fd, visitor.print_queue)


def _process_queue(fd, queue):
	indent = 0

	line_broken = True

	for cmd in queue:
		assert isinstance(cmd, tuple)

		if cmd[0] == CMD_START_STATEMENT:
			# assert line_broken
			pass
		elif cmd[0] == CMD_END_STATEMENT or cmd[0] == CMD_END_LINE:
			fd.write("\n")
			line_broken = True
		elif cmd[0] == CMD_START_BLOCK:
			indent += 1
		elif cmd[0] == CMD_END_BLOCK:
			indent -= 1

			assert indent >= 0
		else:
			assert cmd[0] == CMD_WRITE

			if line_broken:
				fd.write(indent * '\t')
				line_broken = False

			_id, fmt, args, kargs = cmd

			if len(args) + len(kargs) > 0:
				text = fmt.format(*args, **kargs)
			elif isinstance(fmt, str):
				text = fmt
			else:
				text = str(fmt)

			fd.write(text)
