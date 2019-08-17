#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import os
import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse
from ljd.ast.helpers import insert_table_record

catch_asserts = False
debug_verify = "LJD_DEBUG" in os.environ


# Temporary slot cleanup eliminating assignments - general documentation
#
# Imagine the following:
#
# slot0 = "mything"
# slot1 = slot0
# return slot1
#
# There's a couple of ways this could be simplified. If slot0 is eliminated first, it will look like this:
#
# slot1 = "mything"
# (slot1 = slot0 -- marked for deletion)
# return slot1
#
# return "mything"
#
# If, however (and this can happen under some situations) slot1 is eliminated first, the following can occur:
#
# slot0 = "mything"
# (slot1 = slot0 -- marked for deletion)
# return slot0
#
# (slot0 = "mything" -- marked for deletion)
# (slot1 = "mything" -- marked for deletion, substituion was made here)
# return slot0
#
# Which method is used depends on the ordering of the collected slots.
#
# Now, why does this occur? The visitor system that collects all the slots does so node-by-node so it should
# pick up the earlier slots first. This is broken due to the committing system: when a slot is first used, it
# it not immediately added to the slots list. Rather, it is marked as a 'known slot', and any references to
# it will be added. This is done as one slot may refer to multiple variables, as per below:
#
# addr1:   slot0 = my_global
# addr2:   slot1 = slot0 -- slot1 is my_global
# addr3:   slot1 = slot1() -- slot1 is the result of the function execution
#
# Whenever a slot is reassigned, it is "committed" into the slots array. At the end of parsing, any uncommitted
# slots are committed. In this case the slot0, it is only assigned at addr1, and is therefore committed at the
# very end, after everything else. slot1 is assigned both at addr2 and addr3. When addr3 is visited, slot1 gets
# committed to the stack as the same slot is used to hold another different value.
# The slots list is then as follows: [addr2_slot1, addr1_slot0, addr3_slot1], and we get broken output.
#
# Here's a minimal code sample to reproduce this:
# local some_local = my_global
# local testing = some_local()
#
# This is now fixed via _sort_slots - slots are given an ID in the order they first appear, and this is used to
# sort them. This should solve this issue for good.


def eliminate_temporary(ast):
    _eliminate_multres(ast)

    slots, unused = _collect_slots(ast)
    _sort_slots(slots)
    _eliminate_temporary(slots)

    # _remove_unused(unused)

    _cleanup_invalid_nodes(ast)

    return ast


def simplify_ast(ast, eliminate_slots=True):
    traverse.traverse(_SimplifyVisitor(eliminate_slots=eliminate_slots), ast)


def _eliminate_temporary(slots):
    simple = []
    massive = []
    tables = []
    iterators = []

    for info in slots:
        assignment = info.assignment

        if not isinstance(assignment, nodes.Assignment):
            assert isinstance(assignment, (nodes.IteratorWarp,
                                           nodes.NumericLoopWarp,
                                           nodes.FunctionDefinition))

            src = info.references[1].identifier
            simple.append((info.references, src))
            continue

        assert len(assignment.expressions.contents) == 1

        is_massive = len(assignment.destinations.contents) > 1

        if is_massive:
            _fill_massive_refs(info, simple, massive, iterators)
        else:
            _fill_simple_refs(info, simple, tables)

    _eliminate_simple_cases(simple)
    _eliminate_into_table_constructors(tables)
    _eliminate_mass_assignments(massive)
    _eliminate_iterators(iterators)


def _fill_massive_refs(info, simple, massive, iterators):
    ref = info.references[1]
    holder = _get_holder(ref.path)

    src = info.assignment.expressions.contents[0]

    assert isinstance(src, (nodes.FunctionCall,
                            nodes.Vararg,
                            nodes.Primitive))
    if isinstance(holder, nodes.Assignment):
        dst = holder.destinations.contents[0]

        assert len(info.references) == 2
        orig = info.references[0].identifier

        assignment = ref.path[-3]

        assert isinstance(assignment, nodes.Assignment)

        massive.append((orig, info.assignment, assignment, dst))
    elif isinstance(holder, nodes.IteratorWarp):
        assert len(info.references) == 2
        iterators.append((info.assignment, src, holder))
    elif isinstance(src, nodes.Primitive) and src.type == src.T_NIL:
        assert len(info.references) == 2

        # Create a new primitive, so it won't mess with the
        # writer's ignore list
        src = nodes.Primitive()
        src.type = nodes.Primitive.T_NIL

        simple.append((info, ref, src))


def _fill_simple_refs(info, simple, tables):
    src = info.assignment.expressions.contents[0]

    src_is_table = isinstance(src, nodes.TableConstructor)

    holders = set()

    # Collect all the simple refs as we go through, then make a policy decision about what to
    # do with them at the end. This also folds in the table constructor elements, even if simple
    # inlining cannot be performed (though mutator.py would likely pick this up regardless).
    new_simple = []

    # Check if we've had a single non-table-constructor-write reference yet. If so, none of the
    # following references can be part of the constructor.
    # Without this, the following:
    #
    # local test = {}
    # f(test)
    # test.abc = "hi"
    #
    # Decompiles to:
    #
    # slot0 = { abc = "hi" }
    # f(slot0)
    #
    # Note that when debugging this, it may be wise to disable mutator.py - it can interfere
    # with the results and move things into the constructor that otherwise wouldn't be.
    all_ctor_refs = True

    for ref in info.references[1:]:
        holder = _get_holder(ref.path)

        is_element = isinstance(holder, nodes.TableElement)

        if is_element:
            # Fixes an error on this:
            # local a = tbl[var or 123]:func()
            # This is due to the compiler only evaluating (var or 123) once, then mov-ing that to
            # another slot, and this results in two different slot references that have the same holder.
            if holder in holders:
                continue

            holders.add(holder)

        path_index = ref.path.index(holder)

        statement = _get_holder(ref.path[:path_index])

        statement_is_assignment = isinstance(statement, nodes.Assignment)

        if statement_is_assignment:
            is_dst = statement.destinations.contents[0] == holder
        else:
            is_dst = False

        if debug_verify:
            for tst_info, tst_ref, _ in new_simple:
                if tst_info == info:
                    tst_holder = tst_ref.path[-2]
                    assert tst_holder != ref.path[-2]
                    assert tst_holder != holder

        # Could be more then one reference here
        if src_is_table and is_element and is_dst and all_ctor_refs:
            assert holder.table == ref.identifier
            tables.append((info, ref))
        else:
            new_simple.append((info, ref, None))
            all_ctor_refs = False

    # Don't attempt to simplify any slots that have more than two usages (excluding table constructor elements).
    # This is a major policy change, as slotworks used to inline almost anything and
    # everything, with the exception of the results of function calls with more than three
    # uses.
    # This caused a LOT of incorrect decompilation results, however this is only noticeable
    # when running against stripped code - when a slot has a name attached, it cannot be
    # simplified and thus many of these issues would not appear.
    # For an example of the issues this caused, see issue #19 (https://gitlab.com/znixian/luajit-decompiler/issues/19)
    # Also note that we only inline the use if it's still valid at the end.
    #
    # And as for the issue 19 problem, why isn't that still happening like this? There's still
    # only one simple reference, since the other one has been moved into the tables system. The
    # answer is 55b2f5c, which introduced all_ctor_refs. Since the table is referenced before the
    # third use, it cannot be moved into the constructor (well, mutator will move it in, but it'll
    # be safe from being eliminated)
    if len(new_simple) == 1:
        simple += new_simple


LIST_TYPES = (nodes.VariablesList,
              nodes.IdentifiersList,
              nodes.ExpressionsList,
              nodes.StatementsList)

OPERATOR_TYPES = (nodes.BinaryOperator, nodes.UnaryOperator)


def _get_holder(path):
    for node in reversed(path[:-1]):
        if not isinstance(node, LIST_TYPES):
            return node

    return None


def _eliminate_simple_cases(simple):
    for info, ref, src in simple:
        holder = ref.path[-2]
        dst = ref.identifier

        if src is None:
            src = info.assignment.expressions.contents[0]

        # if the assignment's src is FunctionDefinition and references 3 times(one time for assignment,and two
        # times for call),so marked the identifier to local type and set the name to tmp slot
        # TODO figure out *why* the functions are ending up here and fix it there
        if isinstance(src, nodes.FunctionDefinition) and len(info.references) >= 3:
            first = info.references[0]
            first.identifier.type = nodes.Identifier.T_LOCAL
            if first.identifier.name is None:
                first.identifier.name = 'slot%d' % first.identifier.slot
            continue
        elif isinstance(src, OPERATOR_TYPES) \
                and isinstance(holder, nodes.TableElement) \
                and holder.key == dst \
                and isinstance(ref.path[-3], nodes.FunctionCall):
            # Handle a special case where a function has been incorrectly marked as a method now that
            # a slot will be reduced to an expression with an operator
            function = ref.path[-3]
            if function.is_method and \
                    (not isinstance(function, nodes.TableElement)
                     or function.key.type != nodes.Constant.T_STRING):
                function.arguments.contents.insert(0, holder.table)
                function.is_method = False

        _mark_invalidated(info.assignment)

        if isinstance(holder, LIST_TYPES):
            conts = holder.contents
            found = _replace_node_in_list(conts, dst, src)
        else:
            found = _replace_node(holder, dst, src)

        assert found


def _eliminate_into_table_constructors(tables):
    for info, ref in tables:
        constructor = info.assignment.expressions.contents[0]
        table_element = ref.path[-2]
        assignment = ref.path[-4]

        assert isinstance(assignment, nodes.Assignment)

        assert len(assignment.expressions.contents) == 1
        key = table_element.key
        value = assignment.expressions.contents[0]

        success = insert_table_record(constructor, key, value, False)

        # If this would involve overwriting another record, handle it normally
        if not success:
            continue

        _mark_invalidated(assignment)


def _eliminate_mass_assignments(massive):
    for identifier, assignment, base_assignment, globalvar in massive:
        destinations = assignment.destinations.contents
        found = _replace_node_in_list(destinations, identifier, globalvar)

        _mark_invalidated(base_assignment)

        assert found


def _replace_node(holder, original, replacement):
    for key, value in holder.__dict__.items():
        if value == original:
            setattr(holder, key, replacement)
            return True

    return False


def _replace_node_in_list(node_list, original, replacement):
    try:
        index = node_list.index(original)
    except ValueError:
        return False

    node_list[index] = replacement
    return True


def _eliminate_iterators(iterators):
    processed_warps = set()

    for assignment, src, warp in iterators:
        if warp in processed_warps:
            continue

        # Handle `for a in b` where `b` is a variable, or indexing a table (`a.b`)
        # In those cases, the first element in cts will be whatever we should iterate
        #  over, and assignment.destination.contents will only contain two items
        pre = None
        cts = warp.controls.contents
        if len(assignment.destinations.contents) == 2 and len(cts) == 3:
            pre = [cts[0]]
            cts = cts[1:]

        for i, slot in enumerate(assignment.destinations.contents):
            if hasattr(cts[i], "slot"):
                try:
                    assert cts[i].slot == slot.slot
                except (AttributeError, AssertionError):
                    if catch_asserts:
                        setattr(assignment, "_decompilation_error_here", True)
                        print("-- WARNING: Error occurred during decompilation.")
                        print("--   Code may be incomplete or incorrect.")
                    else:
                        raise

        warp.controls.contents = pre or [src]
        processed_warps.add(warp)

        _mark_invalidated(assignment)


def _mark_invalidated(node):
    setattr(node, "_invalidated", True)


def _is_invalidated(node):
    return getattr(node, "_invalidated", False)


def _remove_unused(unused):
    pass


def _collect_slots(ast):
    collector = _SlotsCollector()
    traverse.traverse(collector, ast)

    return collector.slots, collector.unused


def _eliminate_multres(ast):
    traverse.traverse(_MultresEliminator(), ast)
    _cleanup_invalid_nodes(ast)


def _sort_slots(slots):
    def get_slot_id(slot):
        return slot.slot_id

    slots.sort(key=get_slot_id)


class _MultresEliminator(traverse.Visitor):
    def __init__(self):
        super().__init__()
        self._last_multres_value = None

    def leave_assignment(self, node):
        src = node.expressions.contents[0]
        dst = node.destinations.contents[0]

        if isinstance(dst, nodes.MULTRES):
            assert len(node.destinations.contents) == 1
            assert len(node.expressions.contents) == 1

            assert isinstance(src, (nodes.FunctionCall, nodes.Vararg))

            assert self._last_multres_value is None

            self._last_multres_value = src

            _mark_invalidated(node)
        else:
            for i, src in enumerate(node.expressions.contents):
                if isinstance(src, nodes.MULTRES):
                    break
            else:
                return

            assert self._last_multres_value is not None

            node.expressions.contents[i] = self._last_multres_value
            self._last_multres_value = None

    def _process_multres_in_list(self, nodes_list):
        for i, node in enumerate(nodes_list):
            if isinstance(node, nodes.MULTRES):
                break
        else:
            return

        assert self._last_multres_value is not None

        nodes_list[i] = self._last_multres_value
        self._last_multres_value = None

    def visit_function_call(self, node):
        self._process_multres_in_list(node.arguments.contents)

    def visit_return(self, node):
        self._process_multres_in_list(node.returns.contents)


class _SlotReference:
    def __init__(self):
        self.path = []
        self.identifier = None


class _SlotInfo:
    def __init__(self, id):
        self.slot = 0

        self.assignment = None
        self.references = []
        self.termination = None

        self.function = None

        # An ID representing the position in the input
        # This is used to ensure correct ordering of the slots, preventing reverse references (see comment about
        # the temporary slot cleanup eliminating assignments)
        self.slot_id = id


class _SlotsCollector(traverse.Visitor):
    class _State:
        def __init__(self):
            self.known_slots = {}
            self.function = None

    # ##

    def __init__(self):
        super().__init__()
        self._states = []
        self._path = []
        self._skip = None
        self._next_slot_id = 0

        self.slots = []
        self.unused = []

        self._push_state()

    # ##

    def _state(self):
        return self._states[-1]

    def _push_state(self):
        self._states.append(_SlotsCollector._State())

    def _pop_state(self):
        self._states.pop()

    # Slots are stored (at most) twice: once by their id and the most recent slot assignment
    # will be stored with id -1. This way we can prevent the loss of information after an elimination
    # step where an expression references the same slot at multiple states (ids).
    def _get_slot(self, slot, exact=True):
        slot_states = self._state().known_slots.get(slot.slot)
        if slot_states:
            info = slot_states.get(slot.id)
            if exact and info and info.slot_id != slot.id:
                return None
            return info
        return None

    def _set_slot(self, slot, info):
        slot_states = self._state().known_slots.get(slot.slot)
        if not slot_states:
            slot_states = {}
            self._state().known_slots[slot.slot] = slot_states
        slot_states[slot.id] = info
        if slot.id != -1:
            slot_states[-1] = info

    def _remove_slot(self, slot):
        slot_states = self._state().known_slots.get(slot.slot)
        if slot_states:
            if slot.id != -1:
                info = slot_states.get(slot.id)
                if info == slot_states.get(-1):
                    del slot_states[-1]
            del slot_states[slot.id]
            if not slot_states:
                del self._state().known_slots[slot.slot]

    def _commit_info(self, info):
        assert len(info.references) > 0

        if len(info.references) == 1:
            self.unused.append(info)
        else:
            self.slots.append(info)

    def _commit_slot(self, slot, node):
        info = self._get_slot(slot)

        if info is None:
            return

        info.termination = node

        self._remove_slot(slot)

        self._commit_info(info)

    def _register_slot(self, slot, node):
        self._commit_slot(slot, node)

        # We need to re-use known slot ids here to avoid assigning a new id to a slot that has been registered on a
        # previous slot collection run.
        slot_id = slot.id
        if slot_id == -1:
            slot_id = self._next_slot_id
            self._next_slot_id += 1
            slot.id = slot_id

        info = _SlotInfo(slot_id)
        info.slot = slot.slot
        info.assignment = node
        info.function = self._state().function

        self._set_slot(slot, info)

    def _register_all_slots(self, node, slots):
        for slot in slots:
            if not isinstance(slot, nodes.Identifier):
                continue

            if slot.type != nodes.Identifier.T_SLOT:
                continue

            self._register_slot(slot, node)

    def _commit_all_slots(self, slots, node):
        for slot in slots:
            if not isinstance(slot, nodes.Identifier):
                continue

            self._commit_slot(slot, node)

    def _register_slot_reference(self, slot, node):
        # Slot references may have a reference to a slot that was identified in a previous block. WHen
        # this is the case, we need to use the slot that has been assigned most recently.
        info = self._get_slot(slot, False)

        if info is None:
            return

        reference = _SlotReference()
        reference.identifier = node

        # Make sure the identifier node stores the correct slot reference.
        if node.id == -1:
            node.id = info.slot_id

        # Copy the list, but not contents
        reference.path = self._path[:]

        info.references.append(reference)

    # ##

    def visit_assignment(self, node):
        self._visit(node.expressions)
        self._skip = node.expressions

        self._register_all_slots(node, node.destinations.contents)

    def leave_assignment(self, node):
        self._skip = None

    def visit_identifier(self, node):
        if node.type == nodes.Identifier.T_SLOT:
            self._register_slot_reference(node, node)

    # ##

    def visit_function_definition(self, node):
        self._push_state()
        self._state().function = node

    def leave_function_definition(self, node):
        self._pop_state()

    def leave_block(self, node):
        for info_states in self._state().known_slots.values():
            for slot_id, info in info_states.items():
                # Commit slots only once, so ignore the extra references to the "most recent" slots.
                if slot_id == info.slot_id:
                    self._commit_info(info)

        self._state().known_slots = {}

    def visit_iterator_warp(self, node):
        self._commit_all_slots(node.variables.contents, node)

    def visit_numeric_loop_warp(self, node):
        self._commit_slot(node.index, node)

    # ##

    def _visit_node(self, handler, node):
        self._path.append(node)

        traverse.Visitor._visit_node(self, handler, node)

    def _leave_node(self, handler, node):
        self._path.pop()

        traverse.Visitor._leave_node(self, handler, node)

    def _visit(self, node):
        if self._skip == node:
            return

        traverse.Visitor._visit(self, node)


def _cleanup_invalid_nodes(ast):
    traverse.traverse(_TreeCleanup(), ast)


class _TreeCleanup(traverse.Visitor):
    def visit_block(self, node):
        patched = []

        for subnode in node.contents:
            if not _is_invalidated(subnode):
                patched.append(subnode)

        node.contents = patched


class _SimplifyVisitor(traverse.Visitor):

    def __init__(self, eliminate_slots=True):
        super().__init__()
        self._dirty = False
        self._eliminate_slots = eliminate_slots

    def leave_block(self, node):
        if self._dirty:
            if self._eliminate_slots:
                eliminate_temporary(node)
            self._dirty = False

    # Identify method calls, and mark them as such early. This eliminates their 'this' argument, which allows
    # the elimination of slots that would otherwise have three uses.
    def visit_function_call(self, node):
        if node.is_method:
            return

        args = node.arguments.contents
        func = node.function

        if len(args) < 1 or not isinstance(args[0], nodes.Identifier):
            return

        arg0 = args[0]
        if not isinstance(func, nodes.TableElement) or not isinstance(func.table, nodes.Identifier):
            return
        elif isinstance(func.key, nodes.Identifier):
            if func.key.type != nodes.Identifier.T_SLOT:
                return
        elif not isinstance(func.key, nodes.Constant) or func.key.type != nodes.Constant.T_STRING:
            return

        table = func.table

        if arg0.name != table.name or arg0.type != table.type or arg0.slot != table.slot:
            return

        self._dirty = True
        node.is_method = True
        del args[0]
