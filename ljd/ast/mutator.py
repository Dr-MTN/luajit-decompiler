#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


class SimpleLoopWarpSwapper(traverse.Visitor):
	def visit_statements_list(self, node):
		blocks = node.contents

		for block in node.contents:
			warp = block.warp

			if isinstance(warp, nodes.IteratorWarp):
				self._swap_iterator_warps(blocks, block)
			elif isinstance(warp, nodes.NumericLoopWarp):
				self._swap_numeric_loop_warps(blocks, block)

	def _swap_iterator_warps(self, blocks, block):
		warp = block.warp
		index = warp.body.index

		assert index > 0

		start = blocks[index - 1]

		assert isinstance(start.warp, nodes.UnconditionalWarp)
		assert start.warp.type == nodes.UnconditionalWarp.T_JUMP
		assert start.warp.target == block

		new_end_warp = start.warp
		new_start_warp = block.warp

		block.warp = new_end_warp
		start.warp = new_start_warp

		new_end_warp.target = start

	def _swap_numeric_loop_warps(self, blocks, block):
		warp = block.warp
		index = warp.body.index

		assert index > 0

		start = blocks[index - 1]

		assert isinstance(start.warp, nodes.UnconditionalWarp)
		assert start.warp.type == nodes.UnconditionalWarp.T_FLOW
		assert start.warp.target == warp.body

		new_end_warp = start.warp
		new_start_warp = block.warp

		block.warp = new_end_warp
		start.warp = new_start_warp

		new_end_warp.type = nodes.UnconditionalWarp.T_JUMP
		new_end_warp.target = start


class MutatorVisitor(traverse.Visitor):
	# ##

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

	def visit_statements_list(self, node):
		patched = []

		for statement in node.contents:
			if not isinstance(statement, nodes.BlackHole):
				patched.append(statement)

		node.contents = patched


def pre_pass(ast):
	traverse.traverse(SimpleLoopWarpSwapper(), ast)

	return ast


def primary_pass(ast):
	traverse.traverse(MutatorVisitor(), ast)

	return ast
