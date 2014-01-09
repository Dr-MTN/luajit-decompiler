#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


class MutatorVisitor(traverse.Visitor):
	# ##

	def leave_assignment(self, node):
		for dst in node.destinations.contents:
			if not isinstance(dst, nodes.Identifier):
				return

		node.type = nodes.Assignment.T_LOCAL_DEFINITION

	def leave_if(self, node):
		if len(node.else_block.contents) != 1:
			return

		subif = node.else_block.contents[0]

		if not isinstance(subif, nodes.If):
			return

		elseif = nodes.ElseIf()
		elseif.expression = subif.expression
		elseif.then_block = subif.then_block
		
		node.elseifs.append(elseif)
		node.elseifs += subif.elseifs
		node.else_block = subif.else_block


def mutate(ast):
	traverse.traverse(MutatorVisitor(), ast)

	return ast
