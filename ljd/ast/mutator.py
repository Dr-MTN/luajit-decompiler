#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse

from ljd.ast.helpers import insert_table_record


class SimpleLoopWarpSwapper(traverse.Visitor):
	def visit_statements_list(self, node):
		blocks = node.contents

		for i, block in enumerate(node.contents):
			warp = block.warp

			if isinstance(warp, nodes.IteratorWarp):
				self._swap_iterator_warps(blocks, block)
				continue

			if isinstance(warp, nodes.NumericLoopWarp):
				self._swap_numeric_loop_warps(blocks, block)
				continue

			if not isinstance(warp, nodes.UnconditionalWarp):
				continue

			if not warp.is_uclo:
				continue

			target = warp.target

			if len(target.contents) != 1:
				continue

			statement = target.contents[0]

			if not isinstance(statement, nodes.Return):
				continue

			block.contents.append(statement)
			statement._addr = block.last_address
			target.contents = []

			assert block != node.contents[-1]

			warp.type = nodes.UnconditionalWarp.T_FLOW
			warp.target = node.contents[i + 1]

	def _swap_iterator_warps(self, blocks, end):
		warp = end.warp
		index = warp.body.index

		assert index > 0

		start = blocks[index - 1]

		assert isinstance(start.warp, nodes.UnconditionalWarp)
		assert start.warp.type == nodes.UnconditionalWarp.T_JUMP
		assert start.warp.target == end

		end_addr = end.warp._addr
		start_addr = start.warp._addr

		new_end_warp = start.warp
		new_end_warp._addr = end_addr

		new_start_warp = end.warp
		new_start_warp._addr = start_addr

		end.warp = new_end_warp
		start.warp = new_start_warp

		new_end_warp.target = start

	def _swap_numeric_loop_warps(self, blocks, end):
		warp = end.warp
		index = warp.body.index

		assert index > 0

		start = blocks[index - 1]

		assert isinstance(start.warp, nodes.UnconditionalWarp)
		assert start.warp.type == nodes.UnconditionalWarp.T_FLOW
		assert start.warp.target == warp.body

		end_addr = end.warp._addr
		start_addr = start.warp._addr

		new_end_warp = start.warp
		new_end_warp._addr = end_addr

		new_start_warp = end.warp
		new_start_warp._addr = start_addr

		end.warp = new_end_warp
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

		i = -1

		while i < len(node.contents) - 1:
			i += 1
			statement = node.contents[i]

			if isinstance(statement, nodes.BlackHole):
				continue

			patched.append(statement)

			if not isinstance(statement, nodes.Assignment):
				continue

			src = statement.expressions.contents[0]

			if not isinstance(src, nodes.TableConstructor):
				continue

			assert len(statement.destinations.contents) == 1

			dst = statement.destinations.contents[0]

			i += self._fill_constructor(dst, src, node.contents[i + 1:])

		node.contents = patched

	def _fill_constructor(self, table, constructor, statements):
		consumed = 0

		for statement in statements:
			if not isinstance(statement, nodes.Assignment):
				break

			if len(statement.destinations.contents) > 1:
				break

			dst = statement.destinations.contents[0]

			if not isinstance(dst, nodes.TableElement):
				break

			if not self._is_equal(dst.table, table):
				break

			assert len(statement.expressions.contents) == 1

			src = statement.expressions.contents[0]

			insert_table_record(constructor, dst.key, src)
			consumed += 1

		return consumed

	def _is_equal(self, a, b):
		if type(a) != type(b):
			return False

		if isinstance(a, nodes.Identifier):
			return a.type == b.type and a.slot == b.slot
		elif isinstance(a, nodes.TableElement):
			return self._is_equal(a.table, b.table)		\
				and self._is_equal(a.key, b.key)
		else:
			assert isinstance(a, nodes.Constant)
			return a.type == b.type and a.value == b.value


def pre_pass(ast):
	traverse.traverse(SimpleLoopWarpSwapper(), ast)

	return ast


def primary_pass(ast):
	traverse.traverse(MutatorVisitor(), ast)

	return ast
