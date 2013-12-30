#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#


class FunctionDefinition():
	def __init__(self):
		self.arguments = IdentifiersList()
		self.name = None
		self.block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_function_definition, self)

		visitor._visit(self.arguments)
		visitor._visit(self.block)


class TableConstructor():
	def __init__(self):
		self.records = RecordsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_table_constructor, self)

		visitor._visit(self.records)


class TableRecord():
	def __init__(self):
		self.key = None
		self.value = None

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_table_record, self)

		visitor._visit(self.key)
		visitor._visit(self.value)


class Assignment():
	T_LOCAL_DEFINITION = 0
	T_NORMAL = 1

	def __init__(self):
		self.destinations = VariablesList()
		self.expressions = ExpressionsList()
		self.type = -1

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_assignment, self)

		visitor._visit(self.destinations)
		visitor._visit(self.expressions)


class BinaryOperator():
	T_LOGICAL_OR = 0  # left or right
	T_LOGICAL_AND = 10  # left and right

	T_LESS_THEN = 20  # left < right
	T_GREATER_THEN = 21  # left > right
	T_LESS_OR_EQUAL = 22  # left <= right
	T_GREATER_OR_EQUAL = 23  # left >= right

	T_NOT_EQUAL = 24  # left ~= right
	T_EQUAL = 25  # left == right

	T_CONCAT = 30  # left .. right

	T_ADD = 40  # left + right
	T_SUBTRACT = 41  # left - right

	T_MULTIPLY = 50  # left * right
	T_DIVISION = 51  # left / right
	T_MOD = 52  # left % right

	T_POW = 70  # left ^ right

	def __init__(self):
		self.type = -1
		self.left = None
		self.right = None

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_binary_operator, self)

		visitor._visit(self.left)
		visitor._visit(self.right)


class UnaryOperator():
	T_NOT = 60  # not operand
	T_LENGTH_OPERATOR = 61  # #operand
	T_MINUS = 62  # -operand

	def __init__(self):
		self.type = -1
		self.operand = None

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_unary_operator, self)

		visitor._visit(self.operand)


class StatementsList():
	def __init__(self):
		self.contents = []

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_statements_list, self)

		visitor._visit_list(self.contents)


class IdentifiersList():
	def __init__(self):
		self.contents = []

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_identifiers_list, self)

		visitor._visit_list(self.contents)


class RecordsList():
	def __init__(self):
		self.contents = []

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_records_list, self)

		visitor._visit_list(self.contents)


class VariablesList():
	def __init__(self):
		self.contents = []

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_variables_list, self)

		visitor._visit_list(self.contents)


class ExpressionsList():
	def __init__(self):
		self.contents = []

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_expressions_list, self)

		visitor._visit_list(self.contents)


# Called Name in the Lua 5.1 reference
class Identifier():
	T_SLOT = 0
	T_LOCAL = 1
	T_UPVALUE = 2
	T_BUILTIN = 3

	def __init__(self):
		self.name = None
		self.type = -1
		self.slot = -1
		self._varinfo = None  # from debuginfo

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_identifier, self)


# helper vararg/varreturn

class MULTRES():
	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_multres, self)


class TableElement():
	def __init__(self):
		self.table = None
		self.key = None

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_table_element, self)

		visitor._visit(self.key)
		visitor._visit(self.table)


class Vararg():
	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_vararg, self)


class FunctionCall():
	def __init__(self):
		self.function = None
		self.arguments = ExpressionsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_function_call, self)

		visitor._visit(self.function)
		visitor._visit(self.arguments)


class If():
	def __init__(self):
		self.expression = None
		self.then_block = StatementsList()
		self.elseifs = []
		self.else_block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_if, self)

		visitor._visit(self.expression)
		visitor._visit(self.then_block)

		visitor._visit_list(self.elseifs)

		visitor._visit(self.else_block)


class ElseIf():
	def __init__(self):
		self.expression = None
		self.then_block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_elseif, self)

		visitor._visit(self.expression)
		visitor._visit(self.then_block)


class Return():
	def __init__(self):
		self.returns = ExpressionsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_return, self)

		visitor._visit(self.returns)


class Break():
	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_break, self)


class While():
	def __init__(self):
		self.expression = None
		self.block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_while, self)

		visitor._visit(self.expression)
		visitor._visit(self.block)


class RepeatUntil():
	def __init__(self):
		self.expression = None
		self.block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_repeat_until, self)

		visitor._visit(self.expression)
		visitor._visit(self.block)


class NumericFor():
	def __init__(self):
		self.variable = None
		self.expressions = ExpressionsList()
		self.block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_numeric_for, self)

		visitor._visit(self.variable)
		visitor._visit(self.expressions)
		visitor._visit(self.block)


class IteratorFor():
	def __init__(self):
		self.expressions = ExpressionsList()
		self.identifiers = IdentifiersList()
		self.block = StatementsList()

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_iterator_for, self)

		visitor._visit(self.expressions)
		visitor._visit(self.identifiers)
		visitor._visit(self.block)


class Constant():
	T_INTEGER = 0
	T_FLOAT = 1
	T_STRING = 2
	T_CDATA = 3

	def __init__(self):
		self.type = -1
		self.value = None

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_constant, self)


class Primitive():
	T_NIL = 0
	T_TRUE = 1
	T_FALSE = 2

	def __init__(self):
		self.type = -1

	def _accept(self, visitor):
		visitor._visit_node(visitor.visit_primitive, self)
