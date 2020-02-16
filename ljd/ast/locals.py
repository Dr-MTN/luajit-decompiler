#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import copy

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


def mark_locals(ast, alt_mode=False):
    traverse.traverse(_LocalsMarker(alt_mode), ast)


def mark_local_definitions(ast):
    traverse.traverse(_LocalDefinitionsMarker(), ast)


LIST_TYPES = (nodes.VariablesList,
              nodes.IdentifiersList,
              nodes.ExpressionsList,
              nodes.StatementsList)


def _get_holder(path):
    for idx, node in enumerate(reversed(path[:-1])):
        if not isinstance(node, LIST_TYPES):
            return node, len(path) - 2 - idx

    return None, -1


class _LocalsMarker(traverse.Visitor):
    class _State:
        def __init__(self):
            self.pending_slots = {}
            self.debuginfo = None
            self.addr = -1

    def __init__(self, alt_mode=False):
        super().__init__()
        self._states = []
        self._alt_mode = alt_mode

    # ##

    def _push_state(self):
        self._states.append(_LocalsMarker._State())

    def _pop_state(self):
        self._states.pop()

    def _state(self):
        return self._states[-1]

    def _process_slots(self, addr):
        debuginfo = self._state().debuginfo

        cleanup = []

        for slot, pending_slot_nodes in self._state().pending_slots.items():
            varinfo = debuginfo.lookup_local_name(addr, slot, self._alt_mode)

            if varinfo is None:
                continue

            cleanup.append(slot)

            if varinfo.type == varinfo.T_INTERNAL:
                continue

            for node in pending_slot_nodes:
                node.name = varinfo.name
                node.type = node.T_LOCAL

                setattr(node, "_varinfo", varinfo)

        for slot in cleanup:
            del self._state().pending_slots[slot]

    def _reset_slot(self, slot):
        self._state().pending_slots.pop(slot, None)

    def _reset_all(self, slots):
        for slot in slots:
            if isinstance(slot, nodes.Identifier):
                self._reset_slot(slot.slot)

    # ##

    def _get_addr(self, node):
        addr = getattr(node, "_addr", None)

        if not addr:
            if isinstance(node, nodes.Assignment):
                return self._get_addr(node.destinations.contents[0])
            elif isinstance(node, nodes.If):
                return self._get_addr(node.expression)
            elif isinstance(node, nodes.UnaryOperator):
                return self._get_addr(node.operand)
            elif isinstance(node, nodes.BinaryOperator):
                return self._get_addr(node.left) or self._get_addr(node.right)

        return addr

    # ##

    def visit_function_definition(self, node):
        self._push_state()
        self._state().debuginfo = node._debuginfo

    def leave_function_definition(self, node):
        addr = node._instructions_count
        if self._alt_mode:
            addr -= 1
        self._process_slots(addr)

        self._pop_state()

    # ##

    def visit_variables_list(self, node):
        # Last chance for a local = local + 1 type assignments
        self._process_slots(self._state().addr)
        self._reset_all(node.contents)

    def visit_identifiers_list(self, node):
        self._reset_all(node.contents)

    def visit_numeric_loop_warp(self, node):
        self._reset_slot(node.index.slot)

    def leave_numeric_for(self, node):
        if self._alt_mode:
            addr = self._get_addr(node)
            if addr:
                self._process_slots(addr)

    def leave_iterator_for(self, node):
        if self._alt_mode:
            addr = self._get_addr(node)
            if addr:
                self._process_slots(addr)

    def leave_assignment(self, node):
        if self._alt_mode:
            for exp in node.destinations.contents:
                self._process_slots(self._state().addr + 1)
                self._process_slots(self._state().addr + 2)

    # ##

    def visit_identifier(self, node):
        if node.type == nodes.Identifier.T_SLOT:
            queue = self._state().pending_slots
            slots = queue.setdefault(node.slot, [])

            slots.append(node)

    # ##

    def _process_worthy_node(self, node):
        addr = getattr(node, "_addr", None)

        if not isinstance(node, nodes.Identifier) and addr is not None:
            # TODO This was an assertion, but it doesn't always hold up. Why was this required?
            if self._state().addr < addr:
                self._state().addr = addr
            if not self._alt_mode:
                self._process_slots(addr)

    # We need to process slots twice as it could be the last
    # statement in the function/block and it could be an assignment
    # as well so we need to process slots before the reset

    def _leave_node(self, handler, node):
        traverse.Visitor._leave_node(self, handler, node)

        self._process_worthy_node(node)

    def _visit_node(self, handler, node):
        self._process_worthy_node(node)

        traverse.Visitor._visit_node(self, handler, node)


class _LocalDefinitionsMarker(traverse.Visitor):
    class _State:
        def __init__(self):
            self.known_locals = [None] * 255
            self.addr = 0

    def __init__(self):
        super().__init__()
        self._states = []
        self._path = []

    def _push_state(self):
        self._states.append(_LocalDefinitionsMarker._State())

    def _pop_state(self):
        self._states.pop()

    def _state(self):
        return self._states[-1]

    def _update_known_locals(self, local, addr):
        state = self._state()
        varinfo = state.known_locals[local.slot]

        state.known_locals[local.slot] = getattr(local,
                                                         "_varinfo",
                                                         None)

        if varinfo is None:
            return False

        if varinfo.end_addr <= addr:
            return False

        return True

    # ##

    def visit_function_definition(self, node):
        self._push_state()

        for local in node.arguments.contents:
            if not isinstance(local, nodes.Vararg):
                self._update_known_locals(local, 1)

    def leave_function_definition(self, node):
        self._pop_state()

    def visit_iterator_for(self, node):
        addr = node._addr

        for local in node.identifiers.contents:
            if local.type == nodes.Identifier.T_LOCAL:
                self._update_known_locals(local, addr)

    def visit_numeric_for(self, node):
        addr = node._addr

        if node.variable.type == nodes.Identifier.T_LOCAL:
            self._update_known_locals(node.variable, addr)

    # ##

    def visit_assignment(self, node):
        dst = node.destinations.contents[0]

        addr = self._state().addr
        dst_addr = getattr(dst, "_addr", addr)

        # Update address if necessary
        if addr != dst_addr:
            self._state().addr = dst_addr
            addr = dst_addr

        if not isinstance(dst, nodes.Identifier):
            return

        if dst.type != nodes.Identifier.T_LOCAL:
            return

        known_slot = self._update_known_locals(dst, addr)

        for slot_index, slot in enumerate(node.destinations.contents[1:]):
            slot_is_local = isinstance(slot, nodes.Identifier) and slot.type == nodes.Identifier.T_LOCAL
            also_known = slot_is_local and self._update_known_locals(slot, addr)

            if not known_slot and (not slot_is_local or also_known):
                # Slot is not known, so it cannot be in the same assignment
                new_node = copy.copy(node)
                new_node.destinations = nodes.VariablesList()
                new_node.destinations.contents = node.destinations.contents[slot_index + 1:]
                node.destinations.contents = node.destinations.contents[:slot_index + 1]

                # Find node in the holder
                _, idx = _get_holder(self._path)
                contents = self._path[idx + 1].contents

                for node_index, child_node in enumerate(contents):
                    if node != child_node:
                        continue

                    contents.insert(node_index + 1, new_node)

                # Split off the bad parts, so what remains is good for a local declaration
                break

            elif not slot_is_local:
                return

            assert known_slot == also_known

        if not known_slot:
            node.type = nodes.Assignment.T_LOCAL_DEFINITION

    def _visit_node(self, handler, node):
        self._path.append(node)

        traverse.Visitor._visit_node(self, handler, node)

    def _leave_node(self, handler, node):
        self._path.pop()

        traverse.Visitor._leave_node(self, handler, node)

    def _visit(self, node):
        node_addr = getattr(node, "_addr", -1)

        if node_addr >= 0:
            self._state().addr = node_addr

        traverse.Visitor._visit(self, node)
