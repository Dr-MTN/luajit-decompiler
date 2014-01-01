#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

#
# Slot elimination.
#
# There are two different cases here:
# 1. Forward replacement - that's the case when a slot gets assigned to
# 	something, i.e. slot = something.
# 	Either way we need to determine slot's value and replace all the
# 	occurances below
# 2. Backward replacement - that's the opposite case when a slot gets assigned
# 	to a function return value, one of many. I.e.
# 	slot, slot, slot, ... = function(call)
# 	In that case we can't guess a value so the forward replacement is not
# 	possible. But the slot itself should be assigned to a something more
# 	permanent just a few instructions below. So we need to find out which
# 	variable/table element the slot is assigned to and then replace all the
# 	slot occurances above with that variable or table element.
#
# The good news are that the cases are never mixed. I.e. if a slot is used
# in the mass assignment (from a function return) then it will be never used
# for anything beyound assigning to a permanent variable/table element.
# If the permanent variable/table element are to be used in the code just below
# - it's value will be assigned to a NEW slot which will be used in any
# operations below (which is covered by the forward case).
#
# But anyway - we can't do this in a single pass, we have to use defered
# approach. So we are going to traverse tree two times - the first time is for
# marking operations and the second time is for executing them.
#

import copy

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


ASSIGNED_VALUE_MARK = "_value_assigned"
COPY_FROM_MARK = "_copy_from"
INVALIDATED_MARK = "_invalidated"


class _SlotDescription():
	T_ASSIGNMENT = 0
	T_MASS_ASSIGNMENT = 1

	def __init__(self):
		self.slots = ()
		self.assignment = None
		self.type = 0


class _SelectiveVisitor(traverse.Visitor):
	def __init__(self):
		traverse.Visitor.__init__(self)

		self._block_visits_to = None

	def _visit(self, node):
		if node == self._block_visits_to:
			return

		traverse.Visitor._visit(self, node)


class JudgeVisitor(_SelectiveVisitor):
	def __init__(self):
		_SelectiveVisitor.__init__(self)
		self._known_slots_stack = [[None] * 255]
		self._path = [None]
		self._multres_stack = [None]

	def _register_slot(self, slot, slots, node, assignment):
		description = _SlotDescription()
		description.node = node
		description.assignment = assignment
		description.slots = slots
		self._known_slots_stack[-1][slot] = description

	def _unregister_slot(self, slot):
		self._known_slots_stack[-1][slot] = None

	def _get_slot_description(self, slot):
		return self._known_slots_stack[-1][slot]

	def _copy_node(self, dst, src):
		setattr(dst, COPY_FROM_MARK, src)
		assert dst != src

	def _invalidate_node(self, node):
		setattr(node, INVALIDATED_MARK, True)

	def _set_multres(self, value):
		self._multres_stack[-1] = value

	def _get_multres(self):
		multres = self._multres_stack[-1]
		assert multres is not None
		return multres

	def _unset_multres(self):
		self._multres_stack[-1] = None

	# ##

	def visit_function_definition(self, node):
		self._known_slots_stack.append([None] * 255)
		self._multres_stack.append(None)

	def leave_function_definition(self, node):
		self._known_slots_stack.pop()
		self._multres_stack.pop()

	def visit_statements_list(self, node):
		lastslots = copy.deepcopy(self._known_slots_stack[-1])
		self._known_slots_stack.append(lastslots)

	def leave_statements_list(self, node):
		self._known_slots_stack.pop()

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

		if destination.type == nodes.Identifier.T_LOCAL:
			# It doesn't matter if it's massive or not
			return self._leave_local_assignment(node)

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

		assert isinstance(last_expression, nodes.MULTRES)	\
			and isinstance(last_destination, nodes.MULTRES)

		table_slot = node.destinations.contents[0].table.slot
		description = self._get_slot_description(table_slot)

		assert description is not None

		constructor = description.assignment.expressions.contents[0]

		constructor.records.contents.append(self._get_multres())

		self._invalidate_node(node)

	def _leave_table_assignment(self, node):
		tablevar = node.destinations.contents[0]
		slot = node.expressions.contents[0]

		# Skip local variables
		if slot.type != nodes.Identifier.T_SLOT:
			return

		description = self._get_slot_description(slot.slot)

		assert description is not None

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

			self._copy_node(description.node, tablevar)
			self._invalidate_node(node)

	def _leave_local_assignment(self, node):
		first = node.destinations.contents[0]
		description = self._get_slot_description(first.slot)

		already_defined = False

		if description is not None:
			# Slots are shared
			already_defined = first == description.node

		for var in node.destinations.contents:
			if already_defined:
				desc = self._get_slot_description(var.slot)
				assert desc.node == var
			else:
				self._register_slot(var.slot, (var.slot,), var, node)

		if not already_defined:
			node.type = nodes.Assignment.T_LOCAL_DEFINITION

	def _leave_massive_slot_assignment(self, node):
		slots = tuple([x.slot for x in node.destinations.contents])

		for destination in node.destinations.contents:
			slot = destination.slot
			self._register_slot(slot, slots, destination, node)

	def _leave_slot_assignment(self, node):
		destination = node.destinations.contents[0]
		slot = destination.slot
		self._register_slot(slot, (slot,), destination, node)

	# ##

	def visit_expressions_list(self, node):
		slots = []

		# Ignore small scale things - we are after
		# slot, slot, slot = call thing here
		if len(node.contents) < 2:
			return

		for subnode in node.contents:
			if not isinstance(subnode, nodes.Identifier):
				return

			if subnode.type != nodes.Identifier.T_SLOT:
				return

			slots.append(subnode.slot)

		slots = tuple(slots)
		description = self._get_slot_description(slots[0])

		if description.slots != slots:
			return

		for slot in slots:
			description = self._get_slot_description(slot)
			assert description.slots == slots

		self._copy_node(node, description.assignment.expressions)
		self._invalidate_node(description.assignment)

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
		assert self._path[-1] != value
		self._copy_node(node, value)

	def visit_multres(self, node):
		self._copy_node(node, self._get_multres())

	# ##

	def _visit_node(self, handler, node):
		_SelectiveVisitor._visit_node(self, handler, node)
		self._path.append(node)

	def _leave_node(self, handler, node):
		self._path.pop()
		_SelectiveVisitor._leave_node(self, handler, node)


class ExecutorVisitor(_SelectiveVisitor):
	# ##

# 	def visit_assignment(self, node):
# 		self._block_visits_to = node.destinations
#
# 	def leave_assignment(self, node):
# 		self._block_visits_to = None

	# ##

	def _process_attribute_copy_from(self, node, attr):
		slot = getattr(node, attr)

		replacement = getattr(slot, COPY_FROM_MARK, None)

		if replacement is not None:
			setattr(node, attr, replacement)

	def leave_binary_operator(self, node):
		self._process_attribute_copy_from(node, "left")
		self._process_attribute_copy_from(node, "right")

	def leave_unary_operator(self, node):
		self._process_attribute_copy_from(node, "operand")

	# ##

	def leave_expressions_list(self, node):
		copy_from = getattr(node, COPY_FROM_MARK, None)

		if copy_from is None:
			self._process_list_copy_form(node)
		else:
			node.contents = copy_from.contents

	def leave_statements_list(self, node):
		node.contents = [x for x in node.contents if		\
					not getattr(x, INVALIDATED_MARK, False)]

	def _process_list_copy_form(self, node):
		contents = []

		for subnode in node.contents:
			copy_from = getattr(subnode, COPY_FROM_MARK, None)

			if copy_from is None:
				contents.append(subnode)
			else:
				contents.append(copy_from)

		node.contents = contents

	leave_identifiers_list = _process_list_copy_form
	leave_variables_list = _process_list_copy_form

	# ##

	def leave_table_element(self, node):
		self._process_attribute_copy_from(node, "table")
		self._process_attribute_copy_from(node, "key")

	def leave_function_call(self, node):
		self._process_attribute_copy_from(node, "function")

	# ##

	def leave_if(self, node):
		self._process_attribute_copy_from(node, "expression")

	def leave_elseif(self, node):
		self._process_attribute_copy_from(node, "expression")

	# ##

	def leave_while(self, node):
		self._process_attribute_copy_from(node, "expression")

	def leave_repeat_until(self, node):
		self._process_attribute_copy_from(node, "expression")


def mutate(ast):
	traverse.traverse(JudgeVisitor(), ast)
	traverse.traverse(ExecutorVisitor(), ast)

	return ast
