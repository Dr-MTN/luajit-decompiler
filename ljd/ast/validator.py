#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


class TypeRestriction():
	def __init__(self, default, specific):
		if isinstance(default, dict) and specific == {}:
			specific = default
			default = None

		self.default = default
		self.specific = specific

	def check(self, node):
		try:
			typespec = self.specific[node]
		except KeyError:
			typespec = self.default

		assert typespec, "Unknown node: {0}".format(node)

		assert isinstance(node, typespec), 		\
			"Invalid node type: {0} should be: {1}"	\
			.format(type(node), typespec)


WARPED_STATEMENT_TYPES = (
	nodes.Assignment,
	nodes.FunctionDefinition,
	nodes.FunctionCall,
	nodes.Return
)

UNWARPED_STATEMENT_TYPES = (
	nodes.Assignment,
	nodes.If,
	nodes.IteratorFor,
	nodes.NumericFor,
	nodes.RepeatUntil,
	nodes.FunctionDefinition,
	nodes.Return,
	nodes.Break,
	nodes.FunctionCall,
	nodes.While
)

EXPRESSION_TYPES = (
	nodes.FunctionCall,
	nodes.Primitive,
	nodes.Constant,
	nodes.Identifier,
	nodes.FunctionDefinition,
	nodes.TableConstructor,
	nodes.Vararg,
	nodes.BinaryOperator,
	nodes.UnaryOperator,
	nodes.MULTRES,
	nodes.TableElement,
)

VARIABLE_TYPES = (
	nodes.Identifier,
	nodes.TableElement,
	nodes.MULTRES  # It's not valid here, but it is a hack anyway...
)

WARP_TYPES = (
	nodes.UnconditionalWarp,
	nodes.ConditionalWarp,
	nodes.IteratorWarp,
	nodes.NumericLoopWarp,
	nodes.EndWarp
)


class Visitor(traverse.Visitor):
	def __init__(self, warped=True):
		# Restrictions for the upmost level
		self.restrictions = [None]
		self.warped = warped

	def _set_restrictions(self, default, specific={}):
		self.restrictions[-1] = TypeRestriction(default, specific)

	# ##

	def visit_function_definition(self, node):
		self._set_restrictions(nodes.Block, {
			node.arguments: nodes.IdentifiersList,
			node.statements: nodes.StatementsList
		})

		if self.warped:
			assert len(node.statements.contents) == 0
		else:
			assert len(node.blocks) == 0

	# ##

	def visit_table_constructor(self, node):
		self._set_restrictions(nodes.RecordsList)

	def visit_table_record(self, node):
		self._set_restrictions(EXPRESSION_TYPES)

	# ##

	def visit_assignment(self, node):
		self._set_restrictions({
			node.destinations: nodes.VariablesList,
			node.expressions: nodes.ExpressionsList
		})

		if not isinstance(node.destinations.contents[0], nodes.Identifier):
			return

		if node.destinations.contents[0].type != nodes.Identifier.T_LOCAL:
			return

		for destination in node.destinations.contents:
			# It's either all or none
			assert destination.type == nodes.Identifier.T_LOCAL

		# Don't test type flag here
	# ##

	def visit_binary_operator(self, node):
		self._set_restrictions(EXPRESSION_TYPES)

		assert	node.type == nodes.BinaryOperator.T_LOGICAL_OR		\
			or node.type == nodes.BinaryOperator.T_LOGICAL_AND	\
										\
			or node.type == nodes.BinaryOperator.T_LESS_THEN	\
			or node.type == nodes.BinaryOperator.T_GREATER_THEN	\
			or node.type == nodes.BinaryOperator.T_LESS_OR_EQUAL	\
			or node.type == nodes.BinaryOperator.T_GREATER_OR_EQUAL	\
										\
			or node.type == nodes.BinaryOperator.T_NOT_EQUAL	\
			or node.type == nodes.BinaryOperator.T_EQUAL		\
										\
			or node.type == nodes.BinaryOperator.T_CONCAT		\
										\
			or node.type == nodes.BinaryOperator.T_ADD		\
			or node.type == nodes.BinaryOperator.T_SUBTRACT		\
										\
			or node.type == nodes.BinaryOperator.T_MULTIPLY		\
			or node.type == nodes.BinaryOperator.T_DIVISION		\
			or node.type == nodes.BinaryOperator.T_MOD		\
										\
			or node.type == nodes.BinaryOperator.T_POW

	def visit_unary_operator(self, node):
		self._set_restrictions(EXPRESSION_TYPES)

		assert node.type == nodes.UnaryOperator.T_NOT			\
			or node.type == nodes.UnaryOperator.T_LENGTH_OPERATOR	\
			or node.type == nodes.UnaryOperator.T_MINUS

	# ##

	def visit_statements_list(self, node):
		if self.warped:
			types = WARPED_STATEMENT_TYPES
		else:
			types = UNWARPED_STATEMENT_TYPES

		self._set_restrictions(types)

	def visit_identifiers_list(self, node):
		# HACK
		self._set_restrictions((nodes.Identifier, nodes.Vararg))

	def visit_records_list(self, node):
		self._set_restrictions((nodes.TableRecord,
					nodes.FunctionCall,
					nodes.Vararg))

		for i, x in enumerate(node.contents):
			if not isinstance(x, nodes.TableRecord):
				assert i == (len(node.contents) - 1)

	def visit_variables_list(self, node):
		self._set_restrictions(VARIABLE_TYPES)

	def visit_expressions_list(self, node):
		self._set_restrictions(EXPRESSION_TYPES)

	# ##

	def visit_identifier(self, node):
		assert node.type == nodes.Identifier.T_SLOT		\
			or node.type == nodes.Identifier.T_BUILTIN	\
			or node.type == nodes.Identifier.T_UPVALUE	\
			or (node.name is not None			\
				and node._varinfo is not None)

		assert node.type == nodes.Identifier.T_SLOT		\
			or node.type == nodes.Identifier.T_LOCAL	\
			or node.type == nodes.Identifier.T_UPVALUE	\
			or node.type == nodes.Identifier.T_BUILTIN

		assert node.type == nodes.Identifier.T_BUILTIN or node.slot >= 0

	def visit_table_element(self, node):
		self._set_restrictions(EXPRESSION_TYPES)

	def visit_function_call(self, node):
		self._set_restrictions({
			node.function: VARIABLE_TYPES,
			node.arguments: nodes.ExpressionsList
		})

	# ##

	def visit_if(self, node):
		self._set_restrictions(nodes.ElseIf, {
			node.expression: EXPRESSION_TYPES,
			node.then_block: nodes.StatementsList,
			node.else_block: nodes.StatementsList
		})

	def visit_elseif(self, node):
		self._set_restrictions({
			node.expression: EXPRESSION_TYPES,
			node.then_block: nodes.StatementsList
		})

	# ##

	def visit_block(self, node):
		self._set_restrictions({
			node.warp: WARP_TYPES,
			node.statements: nodes.StatementsList
		})

		assert node.first_address >= 0			\
			and node.first_address <= node.last_address

		# if false produce a statements without warps in
		# assert node.warpins_count > 0

	def visit_unconditional_warp(self, node):
		assert node.target is not None

		assert node.type == nodes.UnconditionalWarp.T_JUMP	\
			or node.type == nodes.UnconditionalWarp.T_FLOW	\
			or node.type == nodes.UnconditionalWarp.T_LOOP

	def visit_conditional_warp(self, node):
		self._set_restrictions({
			node.condition: EXPRESSION_TYPES
		})

		assert node.true_target is not None
		assert node.false_target is not None

		assert node.type == nodes.ConditionalWarp.T_POSITIVE_JUMP	\
			or node.type == nodes.ConditionalWarp.T_NEGATIVE_JUMP

	def visit_iterator_warp(self, node):
		assert node.body is not None
		assert node.way_out is not None

		self._set_restrictions(nodes.Block, {
			node.variables: nodes.VariablesList,
			node.controls: nodes.ExpressionsList
		})

	def visit_numeric_loop_warp(self, node):
		assert node.body is not None
		assert node.way_out is not None

		self._set_restrictions(nodes.Block, {
			node.index: nodes.Identifier,
			node.controls: nodes.ExpressionsList
		})

	# ##

	def visit_return(self, node):
		self._set_restrictions(nodes.ExpressionsList)

	# ##

	def visit_while(self, node):
		self._set_restrictions({
			node.expression: EXPRESSION_TYPES,
			node.block: nodes.StatementsList
		})

	def visit_repeat_until(self, node):
		self._set_restrictions({
			node.expression: EXPRESSION_TYPES,
			node.block: nodes.StatementsList
		})

	def visit_numeric_for(self, node):
		self._set_restrictions({
			node.expressions: nodes.ExpressionsList,
			node.block: nodes.StatementsList,
			node.variable: VARIABLE_TYPES
		})

	def visit_iterator_for(self, node):
		self._set_restrictions({
			node.expressions: nodes.ExpressionsList,
			node.identifiers: nodes.IdentifiersList,
			node.block: nodes.StatementsList
		})

	# ##

	def visit_constant(self, node):
		assert	node.type == nodes.Constant.T_CDATA		\
			or node.type == nodes.Constant.T_FLOAT		\
			or node.type == nodes.Constant.T_INTEGER	\
			or node.type == nodes.Constant.T_STRING

	def visit_primitive(self, node):
		assert	node.type == nodes.Primitive.T_NIL		\
			or node.type == nodes.Primitive.T_TRUE		\
			or node.type == nodes.Primitive.T_FALSE

	# ##

	def _visit(self, node):
		restrictions = self.restrictions[-1]

		if restrictions is not None:
			restrictions.check(node)

		# Add layer for the child node
		self.restrictions.append(None)

		traverse.Visitor._visit(self, node)

		# And pop it back
		self.restrictions.pop()


def validate(ast, warped=True):
	visitor = Visitor(warped)
	traverse.traverse(visitor, ast)
