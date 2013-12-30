#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#


#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


ASSIGNED_VALUE_MARK = "_value_assigned"
COPY_FROM_MARK = "_copy_from"
INVALIDATED_MARK = "_invalidated"


class SlotMarker(traverse.Visitor):
	def __init__(self):
		traverse.Visitor.__init__(self)

		self._block_visits_to = None
		self._known_slots_stack = [[(None, None)] * 255]

	def _register_slot(self, slot, node, value):
		self._known_slots_stack[-1][slot] = (node, value)

	def _copy_slot_to(self, slot, to_node):
		pair = self._known_slots_stack[-1][slot]

		if pair[0] is None:
			return

		setattr(pair[0], INVALIDATED_MARK, True)
		setattr(to_node, COPY_FROM_MARK, pair[1])

	# ##

	def visit_function_definition(self, node):
		self._known_slots_stack.append([(None, None)] * 255)

	def leave_function_definition(self, node):
		self._known_slots_stack.pop()

	# ##

	def visit_assignment(self, node):
		self._block_visits_to = node.destinations

		destinations = node.destinations

		cant_process = len(destinations.contents) > 1

		if not cant_process:
			assert len(node.expressions.contents) == 1
			value = node.expressions.contents[0]
		else:
			value = None

		for subnode in destinations.contents:
			if not isinstance(subnode, nodes.Identifier)	\
					or subnode.type != subnode.T_SLOT:
				continue

			slot = subnode.slot

			if cant_process:
				self._register_slot(slot, None, None)
			else:
				self._register_slot(slot, subnode, value)

	def leave_assignment(self, node):
		self._block_visits_to = None

	# ##

	def visit_identifier(self, node):
		if node.type != nodes.Identifier.T_SLOT:
			return

		self._copy_slot_to(node.slot, self)

	def _visit(self, node):
		if node == self._block_visits_to:
			return

		traverse.Visitor._visit(self, node)


class SlotMover(traverse.Visitor):
	# ##

	def leave_assignment(self, node):
		destinations = node.destinations

		invalid = True

		for subnode in destinations.contents:
			if not hasattr(subnode, INVALIDATED_MARK):
				invalid = False
				break

		if invalid:
			setattr(self, INVALIDATED_MARK, True)

	# ##

	def leave_statements_list(self, node):
		node.contents = [x for x in node.contents if		\
					not hasattr(x, INVALIDATED_MARK)]

	def _process_copy_form(self, node):
		contents = []

		for subnode in node.contents:
			copy_from = getattr(subnode, COPY_FROM_MARK, None)

			if copy_from is None:
				contents.append(subnode)
			else:
				contents.append(copy_from)

		node.contents = contents

	leave_identifiers_list = _process_copy_form
	leave_variables_list = _process_copy_form
	leave_expressions_list = _process_copy_form


def optimize(ast):
	marker = SlotMarker()
	traverse.traverse(marker, ast)

	mover = SlotMover()
	traverse.traverse(mover, ast)

	return ast
