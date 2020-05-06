#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import os
import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse
from ljd.ast.helpers import insert_table_record

from typing import List
from dataclasses import dataclass

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
# (slot0 = "mything" -- marked for deletion)
# slot1 = "mything"
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


@dataclass
class RefsProcessData:
    slots: List['_SlotInfo']
    simple: List
    massive: List
    tables: List
    iterators: List
    unsafe: List


def eliminate_temporary(ast, ignore_ambiguous=True, identify_slots=False, safe_mode=True, unwarped=False):
    _eliminate_multres(ast)

    slots, unused = _collect_slots(ast, identify_slots=identify_slots, unwarped=unwarped)
    _sort_slots(slots)
    _eliminate_temporary(ast, slots, ignore_ambiguous, safe_mode=safe_mode, unwarped=unwarped)

    # _remove_unused(unused)

    if not unwarped:
        _cleanup_invalid_nodes(ast)

    return ast


def simplify_ast(ast, dirty_callback=None):
    traverse.traverse(_SimplifyVisitor(dirty_callback=dirty_callback), ast)


def _eliminate_temporary(ast, slots, ignore_ambiguous=True, safe_mode=True, unwarped=False):
    data = RefsProcessData(slots, [], [], [], [], [])

    _fill_refs(data, ignore_ambiguous and safe_mode, True)

    _eliminate_simple_cases(data.simple)
    _recheck_unsafe_cases(ast, data.unsafe, ignore_ambiguous=False, safe_mode=safe_mode, unwarped=unwarped)

    _eliminate_into_table_constructors(data.tables)
    _eliminate_mass_assignments(data.massive)
    _eliminate_iterators(data.iterators)


def _fill_refs(data: RefsProcessData, ignore_ambiguous=True, safe_mode=True):
    # A SlotInfo represents a slot being used in a specific, limited context. There must be only
    # one write into the slot, but there can by any number of reads from it.
    # For example (slot1 being the slot in question, hence in caps):
    #
    # slot0 = f()
    # SLOT1 = slot0
    # my_gbl_1 = SLOT1
    # my_gbl_2 = SLOT1
    #
    # This is a limited enough scope that we can - under some conditions - inline through that
    # slot. See the comment at the top of the file for more context.
    #
    # A massive slot is when it's in a large assignment, such as:
    # slot0, slot1 = f()

    for info in data.slots:
        assignment = info.assignment

        if not isinstance(assignment, nodes.Assignment):
            assert isinstance(assignment, (nodes.IteratorWarp,
                                           nodes.NumericLoopWarp,
                                           nodes.FunctionDefinition))

            src = info.references[1].identifier
            data.simple.append((info.references, src))
            continue

        assert len(assignment.expressions.contents) == 1

        is_massive = len(assignment.destinations.contents) > 1

        if is_massive:
            _fill_massive_refs(info, data, ignore_ambiguous, safe_mode)
        else:
            _fill_simple_refs(info, data, ignore_ambiguous, safe_mode)


def _recheck_unsafe_cases(ast, unsafe, ignore_ambiguous, safe_mode=True, unwarped=False):
    if not unsafe:
        return

    blocks = set()
    slots = set()
    for info in unsafe:
        slots.add(str(info.slot) + "#" + str(info.slot_id))
        if not unwarped:
            for ref in info.references[1:]:
                for node in reversed(ref.path):
                    if isinstance(node, nodes.Block):
                        blocks.add(node)
                        break

    if not blocks and not unwarped:
        return

    def _node_dirty_cb(node):
        if not unwarped and not isinstance(node, nodes.Block):
            return

        _cleanup_invalid_nodes(node)

        # Collect slots in the block, but only keep those that were deemed unsafe to eliminate before.
        new_slots, _ = _collect_slots(node, unwarped=unwarped)
        if safe_mode:
            for idx, info in enumerate(new_slots):
                if (str(info.slot) + "#" + str(info.slot_id)) not in slots:
                    del new_slots[idx]

        _sort_slots(new_slots)

        new_data = RefsProcessData(new_slots, [], [], [], [], [])

        _fill_refs(new_data, ignore_ambiguous and safe_mode, safe_mode)
        _eliminate_simple_cases(new_data.simple)

    if unwarped:
        simplify_ast(ast, dirty_callback=_node_dirty_cb)
    else:
        for block in blocks:
            simplify_ast(block, dirty_callback=_node_dirty_cb)


def _fill_massive_refs(info, data: RefsProcessData, ignore_ambiguous, safe_mode=True):
    ref = info.references[1]
    holder = _get_holder(ref.path)

    src = info.assignment.expressions.contents[0]

    # When the compiler needs to null out multiple variables, it can use
    # the KNIL instruction to do so. For example, the following:
    #   local a = nil; local b = nil; local c = nil;
    # Compiles down to a single KNIL instruction (assuming a-c are slots 0-2):
    #   KNIL 0 2
    # There's no point in treating it like the result of a function call or
    # vararg, since (AFAIK) the point of massive refs for those is since they
    # can't really be inlined around because they're all tied together. That's
    # not an issue with KNIL (since all the values are independently nil), so
    # we can just hand over to the simple ref filler, which will (or should, may
    # need to look into it) inline it as usual.
    #
    # In particular, this solves the massive_nils test crashing since the results
    # are referenced more than twice.
    if isinstance(src, nodes.Primitive):
        assert src.type == src.T_NIL

        _fill_simple_refs(info, data, ignore_ambiguous, safe_mode)
        return

    def _remove_invalid_references():
        if not safe_mode:
            return
        # TODO need to check why these invalid references end up here and whether they're actually invalid
        while len(info.references) > 2:
            current_ref = info.references[-1].identifier
            if current_ref.id != -1:
                break
            possible_ids = getattr(current_ref, "_ids", [])
            possible_ids.remove(info.slot_id)
            del info.references[-1]

    assert isinstance(src, (nodes.FunctionCall, nodes.Vararg))
    if isinstance(holder, nodes.Assignment):
        dst = holder.destinations.contents[0]

        _remove_invalid_references()

        # It's perfectly valid for there to be >2 references. This does mean we can't eliminate them as
        # massive references. Instead, leave them as a local variable.
        if len(info.references) != 2:
            data.unsafe.append(info)
            return

        orig = info.references[0].identifier

        assignment = ref.path[-3]

        assert isinstance(assignment, nodes.Assignment)

        data.massive.append((orig, info, assignment, dst))
    elif isinstance(holder, nodes.IteratorWarp):
        _remove_invalid_references()
        assert len(info.references) == 2
        data.iterators.append((info, src, holder))


def _fill_simple_refs(info, data: RefsProcessData, ignore_ambiguous, safe_mode=True):
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
        if ignore_ambiguous and ref.identifier.id == -1:
            continue

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
            data.tables.append((info, ref))
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
    nr_simple_cases = len(new_simple)
    if nr_simple_cases == 1 or (not safe_mode and nr_simple_cases == 2):
        data.simple += new_simple
    elif nr_simple_cases > 1:
        data.unsafe.append(info)


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

        # Set later on if we'd be simplifying something down to illegal Lua code. This is when we
        # substitute a primitive to somewhere it's not allowed, such as:
        #    local a=nil; a()  ---> nil()
        # We're doing this here rather than in _fill_simple_refs, since that doesn't actually know what
        # it's substituting - a primitive could work it's way down a bunch of slots and it'd only know about
        # the primitive when eliminating the first slot.
        # See the illegal_type_eliminations test for an example of this
        if isinstance(src, nodes.Primitive) or isinstance(src, nodes.Constant):
            is_str = isinstance(src, nodes.Constant) and src.type == nodes.Constant.T_STRING
            if isinstance(holder, nodes.FunctionCall) and holder.function == ref.identifier:
                continue
            elif isinstance(holder, nodes.TableElement) and holder.table == ref.identifier and not is_str:
                continue

        # if the assignment's src is FunctionDefinition and references 3 times(one time for assignment,and two
        # times for call),so marked the identifier to local type and set the name to tmp slot
        # TODO figure out *why* the functions are ending up here and fix it there
        if isinstance(src, nodes.FunctionDefinition) and len(info.references) >= 3:
            # Make sure it's actually 3 references, ignoring the ambiguous ones
            nr_references = 0
            for _ref in info.references:
                if _ref.identifier.id == -1 and len(getattr(_ref, "_ids", [])) != 1:
                    continue
                nr_references += 1
            if nr_references >= 3:
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
    for identifier, info, base_assignment, globalvar in massive:
        # If the assignment using the slot has already been invalidated, then skip it.
        # For example, the following:
        #
        # local a, b = f()
        # print(a)
        #
        # Would be (roughly) compiled to:
        #
        # 001 local slot1, slot2 = f()
        # 002 local slot3 = slot1
        # 003 print(slot3)
        #
        # Both the massives elimination and simples elimination would eliminate 002 (corresponding
        # to the base_assignment variable in this method), moving slot3 into the massive assignment.
        # The simple elimination would also eliminate slot3, substituting slot1 into the print directly.
        # This would result in:
        #
        # local slot3, slot2 = f()
        # print(slot1)
        #
        # Since this is run after the simple elimination, check to ensure our target hasn't been swept
        # out from under us.
        if _is_invalidated(base_assignment):
            continue

        destinations = info.assignment.destinations.contents
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

    for info, src, warp in iterators:
        assignment = info.assignment
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


def _collect_slots(ast, identify_slots=False, unwarped=False):
    collector = _SlotsCollector(identify_slots, unwarped)
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
    references: List[_SlotReference]

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
            self.all_known_slots = {}

            self.block_slots = {}
            self.block_refs = {}
            self.block = None

            self.function = None

    # ##

    def __init__(self, identify_slots=False, unwarped=False):
        super().__init__()
        self._states = []
        self._path = []
        self._root = None
        self._skip = None
        self._next_slot_id = 0
        self._identify = identify_slots
        self._unwarped = unwarped
        self._level = 0

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

    # ##

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
        state = self._state()
        for target in [state.known_slots, state.all_known_slots]:
            slot_states = target.get(slot.slot)
            if not slot_states:
                slot_states = {}
                target[slot.slot] = slot_states
            slot_states[slot.id] = info
            if slot.id != -1:
                slot_states[-1] = info

    def _remove_slot(self, slot):
        state = self._state()
        for target in [state.known_slots, state.all_known_slots]:
            slot_states = target.get(slot.slot)
            if slot_states:
                if slot.id != -1:
                    info = slot_states.get(slot.id)
                    if info == slot_states.get(-1):
                        del slot_states[-1]
                del slot_states[slot.id]
                if not slot_states:
                    del target[slot.slot]

    def _find_slot_assignments(self, index, block=None, visited=None):
        state = self._state()
        refs = state.block_refs
        block = block or state.block

        known_slots = state.block_slots.get(block)
        slot_states = known_slots and known_slots.get(index)
        if slot_states:
            info = slot_states.get(-1)
            if info:
                return [info]

        blocks_to_check = refs.get(block)
        if not blocks_to_check:
            return None

        # Keep track of visited nodes to prevent infinite loops
        visited = visited or set()
        visited.add(block)

        possibilities = set()
        for ref in blocks_to_check:
            if ref in visited:
                continue

            found = self._find_slot_assignments(index, ref, visited)
            if found:
                for info in found:
                    possibilities.add(info)

        return list(possibilities)

    def _commit_info(self, info):
        assert len(info.references) > 0

        if len(info.references) == 1:
            self.unused.append(info)
        else:
            self.slots.append(info)

    def _commit_slot(self, slot, node):
        info = self._get_slot(slot) # False

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

    def _register_slot_reference(self, info, node, update_id=True):
        reference = _SlotReference()
        reference.identifier = node

        # Make sure the identifier node stores the correct slot reference.
        if node.id == -1:
            possible_ids = getattr(node, "_ids", [])
            if info.slot_id not in possible_ids:
                if update_id:
                    if len(possible_ids) > 0:
                        # Slot matches, but not the id.
                        return
                    node.id = info.slot_id
                elif self._identify:
                    possible_ids.append(info.slot_id)
                    setattr(node, "_ids", possible_ids)
                    possible_ids.sort()

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
        if node.type != nodes.Identifier.T_SLOT:
            return

        # Slot references may have a reference to a slot that was identified in a previous block. When
        # this is the case, we need to use the slot that has been assigned most recently.
        info = self._get_slot(node, False)
        if info:
            self._register_slot_reference(info, node)
            return

        # No direct reference is found, so look through blocks and register all references
        assignments = self._find_slot_assignments(node.slot)
        if assignments:
            update_ids = self._identify and len(assignments) == 1
            for info in assignments:
                self._register_slot_reference(info, node, False)

    # ##

    def visit_function_definition(self, node):
        self._push_state()
        self._state().function = node

        self._level += 1

    def leave_function_definition(self, node):
        self._level -= 1
        if self._unwarped and self._level == 0:
            state = self._state()
            for info_states in state.known_slots.values():
                for slot_id, info in info_states.items():
                    # Commit slots only once, so ignore the extra references to the "most recent" slots.
                    if slot_id == info.slot_id:
                        self._commit_info(info)

        self._pop_state()

    def visit_block(self, node):
        state = self._state()
        state.block = node
        state.block_slots[node] = state.known_slots

    def leave_block(self, node):
        state = self._state()

        refs = None
        warp = node.warp
        if isinstance(warp, nodes.ConditionalWarp):
            refs = [warp.true_target, warp.false_target]
        elif isinstance(warp, nodes.UnconditionalWarp):
            refs = [warp.target]
        elif isinstance(warp, nodes.NumericLoopWarp):
            refs = [warp.way_out]
        elif isinstance(warp, nodes.IteratorWarp):
            refs = [warp.way_out]

        for ref in refs or []:
            if not ref: continue
            block_refs = state.block_refs.setdefault(ref, set())
            block_refs.add(node)

        for info_states in state.known_slots.values():
            for slot_id, info in info_states.items():
                # Commit slots only once, so ignore the extra references to the "most recent" slots.
                if slot_id == info.slot_id:
                    self._commit_info(info)

        state.known_slots = {}

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

        is_root_node = False
        if self._root is None:
            is_root_node = True
            self._root = node

        traverse.Visitor._visit(self, node)

        if is_root_node:
            self._root = None


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

    def __init__(self, dirty_callback=None):
        super().__init__()
        self._dirty = False
        self._dirty_cb = dirty_callback
        self._root = None

    def _visit_node(self, handler, node):
        if not self._root:
            self._root = node

        traverse.Visitor._visit_node(self, handler, node)

    def _leave_node(self, handler, node):
        if self._root == node:
            self._root = None
            if self._dirty:
                if self._dirty_cb:
                    self._dirty_cb(node)
                self._dirty = False

        traverse.Visitor._leave_node(self, handler, node)

    def leave_block(self, node):
        if self._dirty:
            if self._dirty_cb:
                self._dirty_cb(node)
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
