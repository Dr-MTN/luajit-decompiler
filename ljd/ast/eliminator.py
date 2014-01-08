#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

#
# Slot elimination.
#
# Process is simple enough - we just pick a slot assignment and replace all the
# occurances below. Slots are not propaged through warps (because a context
# of a block could be any) - only exception is a logical expression and that's
# the way to detect it. But the logical expression compilation is not handled
# here - it's handled in the unwapring process instead.
#
# As a special case we also eliminate all the MULTRES occurances, which
# essentially is just a specialy named slot.
#

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


class _SlotDescription():
	def __init__(self):
		self.slots = ()
		self.assignment = None
		self.node = None


class _CopyCommand():
	def __init__(self, dst, src):
		self.dst_parent = None
		self.dst_attribute = None
		self.dst_index = -1
		self.dst = dst
		self.src = src


class _FunctionState():
	def __init__(self):
		self.reset()

	def reset(self):
		self._multres = None
		self._known_slots = [None] * 255
		self._pending_commands = {}
		self._copy_queue = []
		self._invalide_statements = set()


class EliminatorVisitor(traverse.Visitor):
	def __init__(self):
		traverse.Visitor.__init__(self)
		self._block_visits_to = None

		self._states = [_FunctionState()]

	def _register_slot(self, slot, slots, node, assignment):
		description = _SlotDescription()
		description.node = node
		description.assignment = assignment
		description.slots = slots

		self._states[-1]._known_slots[slot] = description

	def _unregister_slot(self, slot):
		self._states[-1]._known_slots[slot] = None

	def _get_slot_description(self, slot):
		return self._states[-1]._known_slots[slot]

	def _copy_node(self, dst, src):
		assert dst != src
		assert dst not in self._states[-1]._pending_commands

		cmd = _CopyCommand(dst, src)

		self._states[-1]._pending_commands[dst] = cmd
		self._states[-1]._copy_queue.append(cmd)

	def _commit_cmd(self, dst, dst_parent, dst_attribute, dst_index=-1):
		cmd = self._states[-1]._pending_commands[dst]

		cmd.dst_parent = dst_parent
		cmd.dst_attribute = dst_attribute
		cmd.dst_index = dst_index

		del self._states[-1]._pending_commands[dst]

	def _invalidate_node(self, node):
		self._states[-1]._invalide_statements.add(node)

	def _set_multres(self, value):
		self._states[-1]._multres = value

	def _get_multres(self):
		assert self._states[-1]._multres is not None
		return self._states[-1]._multres

	def _unset_multres(self):
		self._states[-1]._multres = None

	# ##

	def visit_statements_list(self, node):
		self._states.append(_FunctionState())

	def leave_statements_list(self, node):
		self._states.pop()

	def visit_block(self, node):
		self._states[-1].reset()

	def leave_block(self, node):
		assert len(self._states[-1]._pending_commands) == 0

		for cmd in self._states[-1]._copy_queue:
			assert cmd.dst_parent and cmd.dst_attribute

			subnode = getattr(cmd.dst_parent, cmd.dst_attribute)

			if isinstance(subnode, list) and cmd.dst_index >= 0:
				assert subnode[cmd.dst_index] == cmd.dst
				subnode[cmd.dst_index] = cmd.src
			else:
				assert subnode == cmd.dst
				setattr(cmd.dst_parent, cmd.dst_attribute,
							cmd.src)

		mask = self._states[-1]._invalide_statements
		node.contents = [x for x in node.contents if x not in mask]

	# ##

	# There are seven interesting types or the assignment possible:
	# 1. slot = something
	# 2. table[x] = slot
	# 3. slot, slot, slot, ... = call()
	# 4. local = something
	# 5. local, local, local, ... = call()
	# 6. MULTRES = call()
	# 7. table[A], ... table[] = B, ... , MULTRES (mass table assignment)

	def visit_assignment(self, node):
		destination = node.destinations.contents[0]

		if isinstance(destination, (nodes.Identifier, nodes.MULTRES)):
			self._block_visits_to = node.destinations

		last_expression = node.expressions.contents[-1]

		if isinstance(last_expression, nodes.MULTRES):
			self._block_visits_to = node.expressions

	def leave_assignment(self, node):
		self._block_visits_to = None

		massive = len(node.destinations.contents) > 1

		destination = node.destinations.contents[0]

		if isinstance(destination, nodes.TableElement):
			if massive:
				return self._leave_mass_table_assignment(node)
			else:
				return self._leave_table_assignment(node)

		if isinstance(destination, nodes.MULTRES):
			assert not massive
			return self._leave_multres_assignment(node)

		assert isinstance(destination, nodes.Identifier)

		for subnode in node.destinations.contents:
			self._unregister_slot(subnode.slot)

		# Don't bother with locals here
		if destination.type == nodes.Identifier.T_LOCAL:
			return

		if massive:
			self._leave_massive_slot_assignment(node)
		else:
			self._leave_slot_assignment(node)

	def _leave_multres_assignment(self, node):
		assert len(node.expressions.contents) == 1
		value = node.expressions.contents[0]

		self._set_multres(value)
		self._invalidate_node(node)

	def _leave_mass_table_assignment(self, node):
		last_expression = node.expressions.contents[-1]
		last_destination = node.destinations.contents[-1]

		if not isinstance(last_expression, nodes.MULTRES)	\
				or not isinstance(last_destination, nodes.MULTRES):
			return

		table_slot = node.destinations.contents[0].table.slot
		description = self._get_slot_description(table_slot)

		assert description is not None

		constructor = description.assignment.expressions.contents[0]

		constructor.records.contents.append(self._get_multres())

		self._invalidate_node(node)

	def _leave_table_assignment(self, node):
		tablevar = node.destinations.contents[0]
		slot = node.expressions.contents[0]

		if not isinstance(slot, nodes.Identifier):
			return

		# Skip local variables
		if slot.type != nodes.Identifier.T_SLOT:
			return

		description = self._get_slot_description(slot.slot)

		# That's possible in a case of a logical expression -
		# A global variable is assigned in the first instructin o
		# the next block after the expression
		if description is None:
			return

		value = description.assignment.expressions.contents[0]

		if isinstance(tablevar.table, nodes.Identifier) and	\
				tablevar.table.type == nodes.Identifier.T_SLOT:
			tabledesc = self._get_slot_description(tablevar.table.slot)

			if tabledesc is None:
				return

			constructor = tabledesc.assignment.expressions.contents[0]

			if not isinstance(constructor, nodes.TableConstructor):
				return

			record = nodes.TableRecord()
			record.key = tablevar.key
			record.value = value

			constructor.records.contents.append(record)
			self._invalidate_node(node)
		else:
			# Nothing to worry about
			if len(description.slots) == 1:
				return

			dst = description.node
			dst_parent = description.assignment.destinations

			self._copy_node(dst, tablevar)

			for i, subnode in enumerate(dst_parent.contents):
				if subnode == dst:
					break

			self._commit_cmd(dst, dst_parent, "contents", i)
			self._invalidate_node(node)

	def _leave_massive_slot_assignment(self, node):
		slots = tuple([x.slot for x in node.destinations.contents])

		for destination in node.destinations.contents:
			slot = destination.slot
			self._register_slot(slot, slots, destination, node)

	def _leave_slot_assignment(self, node):
		dst = node.destinations.contents[0]
		slot = dst.slot
		src = node.expressions.contents[0]

		if isinstance(src, nodes.Identifier)	\
				and src.type == nodes.Identifier.T_SLOT:
			description = self._get_slot_description(src.slot)

			assert description is not None

			assignment = description.assignment
			self._register_slot(slot, (slot,), src, assignment)
		else:
			self._register_slot(slot, (slot,), dst, node)

	# ##

	def visit_identifier(self, node):
		if node.type != nodes.Identifier.T_SLOT:
			return

		description = self._get_slot_description(node.slot)

		if description is None:
			return

		assert description is not None

		if len(description.slots) != 1:
			return

		value = description.assignment.expressions.contents[0]
		self._invalidate_node(description.assignment)
		self._copy_node(node, value)

	def visit_multres(self, node):
		self._copy_node(node, self._get_multres())

	# ##

	def _process_attribute_copy_from(self, node, attr):
		slot = getattr(node, attr)
		cmd = self._states[-1]._pending_commands.get(slot)

		if cmd is not None:
			self._commit_cmd(slot, node, attr)

	def leave_binary_operator(self, node):
		self._process_attribute_copy_from(node, "left")
		self._process_attribute_copy_from(node, "right")

		assert len(self._states[-1]._pending_commands) == 0

	def leave_unary_operator(self, node):
		self._process_attribute_copy_from(node, "operand")

		assert len(self._states[-1]._pending_commands) == 0

	# ##

	def leave_table_element(self, node):
		self._process_attribute_copy_from(node, "table")
		self._process_attribute_copy_from(node, "key")

		assert len(self._states[-1]._pending_commands) == 0

	def leave_function_call(self, node):
		self._process_attribute_copy_from(node, "function")

		assert len(self._states[-1]._pending_commands) == 0

	# ##

	def leave_conditional_warp(self, node):
		self._process_attribute_copy_from(node, "condition")

	def leave_iterator_for(self, node):
		slots = []

		for slot in node.expressions.contents:
			assert isinstance(slot, nodes.Identifier)	\
				and slot.type == nodes.Identifier.T_SLOT

			slots.append(slot.slot)

		slots = tuple(slots)

		description = self._get_slot_description(slots[0])

		if description is None:
			return

		# Dissected iterator case
		if description.slots != slots:
			return

		src = description.assignment.expressions

		self._invalidate_node(description.assignment)
		self._copy_node(node.expressions, src)
		self._commit_cmd(node.expressions, node, "expressions")

	def leave_numeric_for(self, node):
		self._process_attribute_copy_from(node, "variable")

	# ##

	def _process_list_copy_form(self, node):
		for i, subnode in enumerate(node.contents):
			cmd = self._states[-1]._pending_commands.get(subnode)

			if cmd is not None:
				self._commit_cmd(subnode, node, "contents", i)

		assert len(self._states[-1]._pending_commands) == 0

	leave_identifiers_list = _process_list_copy_form
	leave_variables_list = _process_list_copy_form
	leave_expressions_list = _process_list_copy_form

	# ##

	def _visit_list(self, nodes_list):
		if nodes_list == self._block_visits_to:
			return

		traverse.Visitor._visit_list(self, nodes_list)

	def _visit(self, node):
		if node == self._block_visits_to:
			return

		traverse.Visitor._visit(self, node)


def eliminate_slots(ast):
	traverse.traverse(EliminatorVisitor(), ast)

	return ast
