#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import copy

from ljd.ast.helpers import *
from ljd.bytecode.instructions import SLOT_FALSE, SLOT_TRUE


class SimpleLoopWarpSwapper(traverse.Visitor):
    class _State:
        def __init__(self):
            self.loops = []
            self.jumps = []

    def __init__(self):
        self._states = []

    def visit_function_definition(self, node):
        self._states.append(self._State())

    def leave_function_definition(self, node):
        state = self._states.pop()
        if not state:
            return

        # Process UCLO returns. Prefer breaks when possible.
        for blocks, i in state.jumps:
            use_break = False

            block = blocks[i]
            warp = block.warp
            target = warp.target

            for start, end in state.loops:
                if end == target:
                    use_break = blocks.index(start) < i
                    break

            if use_break:
                statement = nodes.Break()
            else:
                statement = target.contents[0]
                target.contents = []

            block.contents.append(statement)
            statement._addr = block.last_address

            warp.type = nodes.UnconditionalWarp.T_FLOW
            warp.target = blocks[i + 1]

    def visit_statements_list(self, node):
        blocks = node.contents

        # Fix up the slot assignments made by the ISTC and ISFC instructions.
        # These instructions are similar to the IST and ISF instructions: they check
        # if the specified 'D' slot is true or false, and the next instruction (which
        # must be a JMP) is conditional on that.
        # The difference with ISTC and ISFC is that they also assign the value from
        # the 'D' slot to the 'A' slot, and only if the comparison/jump is successful.
        #
        # For example, take following code (with some made-up instructions for brevity):
        #
        # 1    IST 5
        # 2    JMP => 6
        # 3    PRINT "Slot 5 is false/nil, putting a backup value into slot 2"
        # 4    MOV 2, "backup value"
        # 5    JMP => 7
        # 6 => MOV 2, 5 # Slot five is valid, move to slot 2
        # 7 => PRINT "Value or backup value: $slot2"
        #
        # That's essentially one way you might implement the Lua 'or' operator; however
        # it involves an extra jump for no good reason. Using ISTC you can simplify it as follows:
        #
        # 1    ISTC 2, 5
        # 2    JMP => 5
        # 3    PRINT "Slot 5 is false/nil, putting a backup value into slot 2"
        # 4    MOV 2, "backup value"
        # 5 => PRINT "Value or backup value: $slot2"
        #
        # For LuaJIT, this is an elegant optimisation when running on the interpreter (I think that's
        # what it's for - it's two more X86 instructions on the interpreter for ISTC vs IST, and
        # the logical operators are very very common so it makes sense) but for us it's a bit of a pain.
        #
        # To avoid this having knock-on effects through the rest of the decompiler, expand it to
        # something more like the first example, by creating a block and assignment that doesn't
        # match up to anything in the bytecode.
        #
        # When builder.py is building the conditional warps, it's not in a very easy position to
        # make such a block. Doing it now is much easier.

        fixed = []
        index_shift = 0

        for i, block in enumerate(node.contents):
            warp = block.warp
            fixed.append(block)

            block.index += index_shift

            is_loop_warp = True
            if isinstance(warp, nodes.IteratorWarp):
                self._swap_iterator_warps(blocks, block)
            elif isinstance(warp, nodes.NumericLoopWarp):
                self._swap_numeric_loop_warps(blocks, block)
            else:
                is_loop_warp = False

            if is_loop_warp:
                self._states[-1].loops.append((warp.body, warp.way_out))
                continue

            if isinstance(warp, nodes.UnconditionalWarp) \
                    and warp.is_uclo:
                assert block != node.contents[-1]
                self._fix_uclo_return(node.contents, i)

            if not isinstance(warp, nodes.ConditionalWarp):
                continue

            if warp.true_target != warp.false_target:
                self._simplify_unreachable_conditional_warps(blocks, i)

            # Left here by builder._build_conditional_warp
            slot = getattr(warp, "_istfc_slot", -1)

            if slot < 0:
                continue

            condition = warp.condition
            if isinstance(condition, nodes.UnaryOperator):
                condition = condition.operand
            assert isinstance(condition, nodes.Identifier)

            new_block = self._create_dummy_block(block, condition.slot, slot)

            fixed.append(new_block)

            index_shift += 1

        node.contents = fixed

    def _fix_uclo_return(self, blocks, i):
        block = blocks[i]
        warp = block.warp
        target = warp.target

        if len(target.contents) != 1:
            return

        statement = target.contents[0]

        if not isinstance(statement, nodes.Return):
            return

        if block.contents and \
                isinstance(block.contents[-1], nodes.Return):
            return

        self._states[-1].jumps.append((blocks, i))

    # Create a new dummy block containing a single assignment between slots, and insert it
    # before the real false_target of the specified block
    # Used for recovering the assignments from ISTC and ISFC - see visit_statements_list
    # (note that ISTC is negated and the jump targets switched, so false_target is called
    #  if the slot is to be set - that is, if the value is false for ISFC or true for ISTC
    #  then the false_target is followed)
    @staticmethod
    def _create_dummy_block(block, src, dst):
        new_block = nodes.Block()
        new_block.first_address = block.last_address
        new_block.last_address = new_block.first_address
        new_block.index = block.index + 1
        new_block.warpins_count = 1

        new_block.warp = nodes.UnconditionalWarp()
        new_block.warp.type = nodes.UnconditionalWarp.T_FLOW
        new_block.warp.target = block.warp.false_target

        statement = nodes.Assignment()

        identifier = nodes.Identifier()
        identifier.type = nodes.Identifier.T_SLOT
        identifier.slot = src

        statement.expressions.contents.append(copy.copy(identifier))

        identifier.slot = dst
        statement.destinations.contents.append(identifier)

        # Put this here for debugging, it'll be visible in the AST dumps and debuggers
        setattr(statement, "_dbg_notes", "dummy block for slot %d->%d" % (src, dst))

        new_block.contents.append(statement)

        block.warp.false_target = new_block

        return new_block

    @staticmethod
    def _swap_iterator_warps(blocks, end):
        warp = end.warp
        index = blocks.index(warp.body)

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

    @staticmethod
    def _swap_numeric_loop_warps(blocks, end):
        warp = end.warp
        index = blocks.index(warp.body)

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

    @staticmethod
    def _simplify_unreachable_conditional_warps(blocks, i):
        block = blocks[i]
        target = block.warp.true_target

        if not target:
            return

        # TODO figure out the interactions between the "and false"d out branches and
        #  inserting slots from ISTC/ISFC in visit_statement_list
        return

        node = target
        while node:
            warp = target.warp
            if not isinstance(warp, nodes.UnconditionalWarp):
                return

            if warp.type == nodes.UnconditionalWarp.T_FLOW:
                return

            if target.contents:
                if len(target.contents) > 1:
                    return

                if not isinstance(target.contents[0], nodes.NoOp):
                    return

            if node != target:
                break

            node = warp.target

        if not isinstance(node.warp, nodes.UnconditionalWarp):
            return

        if node.warp.target != block.warp.false_target:
            return

        old_block_index = blocks.index(node)
        next_block = blocks[old_block_index + 1]

        next_block.warpins_count += 1
        node.warp.target.warpins_count -= 1

        del blocks[old_block_index]

        # Change block to restore the false condition
        new_warp = nodes.ConditionalWarp()
        new_warp.true_target = next_block
        new_warp.false_target = block.warp.false_target
        false_cond = nodes.Identifier()
        false_cond.slot = SLOT_FALSE
        false_cond.type = false_cond.T_SLOT
        new_warp.condition = false_cond
        setattr(new_warp, "_slot", SLOT_FALSE)
        setattr(new_warp, "_addr", getattr(block.warp, "_addr", None))
        target.warp = new_warp
        target.last_address += 1
        del target.contents[0]  # remove noop


class MutatorVisitor(traverse.Visitor):
    # ##

    def leave_if(self, node):
        if len(node.else_block.contents) != 1:
            return

        subif = node.else_block.contents[0]

        if not isinstance(subif, nodes.If):
            return

        elseif = nodes.ElseIf()
        if hasattr(subif, "_decompilation_error_here"):
            setattr(elseif, "_decompilation_error_here", True)
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

    @staticmethod
    def _fill_constructor(table, constructor, statements):
        consumed = 0

        for statement in statements:
            if not isinstance(statement, nodes.Assignment):
                break

            if len(statement.destinations.contents) > 1:
                break

            dst = statement.destinations.contents[0]

            if not isinstance(dst, nodes.TableElement):
                break

            if not is_equal(dst.table, table, False):
                break

            assert len(statement.expressions.contents) == 1

            src = statement.expressions.contents[0]

            if has_same_table(src, table):
                break

            success = insert_table_record(constructor, dst.key, src, False)

            if not success:
                break

            consumed += 1

        return consumed


def pre_pass(ast):
    traverse.traverse(SimpleLoopWarpSwapper(), ast)

    return ast


def primary_pass(ast):
    traverse.traverse(MutatorVisitor(), ast)

    return ast
