import copy
import sys

import ljd.ast.nodes as nodes
import ljd.ast.slotworks as slotworks
import ljd.ast.traverse as traverse
from ljd.ast.helpers import *

binop = nodes.BinaryOperator

verbose = False
catch_asserts = False


def exp_debug(*args):
    if verbose:
        print(*args, file=sys.stdout)


# ##
# ## REMEMBER
# ##
# ## Block indices are unreliable while you are mangling them!
# ##
# ## P.S. Probably they should not be named indices... But they ARE used as
# ## indices during other phases. Sometimes.
# ##


class _StatementsCollector(traverse.Visitor):
    def __init__(self):
        super().__init__()
        self.result = []

    def visit_statements_list(self, node):
        if len(node.contents) > 0 or hasattr(node, "_decompilation_error_here"):
            self.result.append(node)


class _FunctionsCollector(traverse.Visitor):
    def __init__(self):
        super().__init__()
        self.result = []

    def visit_function_definition(self, node):
        self.result.append(node)


def unwarp(node, conservative=False):
    try:
        _run_step(_fix_loops, node, repeat_until=False)
        _run_step(_fix_loops, node, repeat_until=True)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_fix_loops, node)\n", file=sys.stdout)
        else:
            raise

    try:
        _run_step(_unwarp_expressions, node)

        # Under some conditions the expressions unwarper causes new assignments to become expressions themselves.
        # Instead of doing some difficult bookkeeping, we just unwarp expressions again.
        #
        # An example where this is needed is an expression like x = x or { a and b }
        #
        # There's probably a better (read: faster) way to do this, but it works for now.
        _run_step(_unwarp_expressions, node)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_unwarp_expressions, node)\n", file=sys.stdout)
        else:
            raise

    # There could be many negative jumps within while conditions, so
    # filter them first
    try:
        _run_step(_unwarp_loops, node, repeat_until=False)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_unwarp_loops, node, repeat_until=False)\n", file=sys.stdout)
        else:
            raise

    try:
        _run_step(_unwarp_loops, node, repeat_until=True)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_unwarp_loops, node, repeat_until=True)\n", file=sys.stdout)
        else:
            raise

    try:
        _run_step(_unwarp_ifs, node)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_unwarp_ifs, node)\n", file=sys.stdout)
        else:
            raise

    try:
        _run_step(_cleanup_ast, node)
        pass
    except:
        if catch_asserts:
            print("-- Decompilation Error: _run_step(_cleanup_ast, node)\n", file=sys.stdout)
        else:
            raise

    try:
        _glue_flows(node, conservative)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _glue_flows(node)\n", file=sys.stdout)
        else:
            raise

    try:
        _trim_redundant_returns(node)
    except:
        if catch_asserts:
            print("-- Decompilation Error: _trim_redundant_returns(node)\n", file=sys.stdout)
        else:
            raise

    try:
        slotworks.simplify_ast(node)
    except:
        if catch_asserts:
            print("-- Decompilation Error: ljd.ast.slotworks.simplify_ast(self.ast)\n", file=sys.stdout)
        else:
            raise


def _run_step(step, node, **kargs):
    for statements in _gather_statements_lists(node):
        statements.contents = step(statements.contents, **kargs)

    # Fix block indices in case anything was moved
    for statements in _gather_statements_lists(node):
        for i, block in enumerate(statements.contents):
            if block.index != i:
                block.former_index = block.index
                block.index = i


def _gather_statements_lists(node):
    collector = _StatementsCollector()
    traverse.traverse(collector, node)
    return collector.result


def _glue_flows(node, conservative=False):
    error_pending = False

    for statements in _gather_statements_lists(node):
        blocks = statements.contents

        # TODO(yzg): 'Return' object has no attribute 'contents'
        assert isinstance(blocks[-1], nodes.Return) or isinstance(blocks[-1].warp, nodes.EndWarp)

        for i, block in enumerate(blocks[:-1]):
            if hasattr(block, "_decompilation_error_here"):
                error_pending = True
            if len(block.contents) == 0:
                continue
            if error_pending:
                setattr(block.contents[0], "_decompilation_error_here", True)
                error_pending = False

            warp = block.warp

            assert _is_flow(warp)

            target = warp.target

            assert target == blocks[i + 1]

            target.contents = block.contents + target.contents
            block.contents = []

        # Most visitors make assumptions on blocks being present. If we want to simplify the AST in multiple passes,
        # these outer blocks cannot simply be eliminated.
        if not conservative or not isinstance(node, nodes.FunctionDefinition):
            if hasattr(blocks[-1], "contents"):  # TODO(yzg): 'Return' object has no attribute 'contents'
                statements.contents = blocks[-1].contents


# Delete returns on the last line of a function, when those returns don't have any arguments
def _trim_redundant_returns(node):
    collector = _FunctionsCollector()
    traverse.traverse(collector, node)

    for funcdef in collector.result:
        statements = funcdef.statements.contents

        if not statements:
            continue

        # If there is an empty return block at the end of this
        last = statements[-1]

        if isinstance(last, nodes.Return):
            if not last.returns.contents:
                del statements[-1]


# ##
# ## IFs AND EXPRESSIONs PROCESSING
# ##

def _unwarp_expressions(blocks):
    pack = []
    pack_set = set()

    start_index = 0
    end_index = 0
    while start_index < len(blocks) - 1:
        start = blocks[start_index]
        warp = start.warp

        if isinstance(warp, nodes.UnconditionalWarp):
            if warp.type == nodes.UnconditionalWarp.T_FLOW:
                start_index += 1
                continue
            elif start_index > 0 and len(start.contents) > 0:
                # Don't continue in the 'false and false' / 'true or true' cases
                if start_index != end_index \
                        or not isinstance(start.contents[-1], nodes.Assignment) \
                        or len(start.contents[-1].expressions.contents) == 0 \
                        or not isinstance(start.contents[-1].expressions.contents[-1], nodes.Primitive):

                    # NOTE Don't skip the last statement (before the return), it may be an expression
                    if start_index == end_index:
                        end_index += 1

                        if end_index < blocks[-1].index - 1:
                            start_index += 1
                        continue
                    elif start_index <= end_index - 1:
                        if start_index != end_index - 1 or end_index < blocks[-1].index - 1:
                            start_index += 1
                            continue

        body, end, end_index = _extract_if_body(start_index, blocks, None)

        if body is None:
            raise NotImplementedError("GOTO statements are not supported")
        elif start_index > 0 and len(body) == 1 and body[0].warpins_count == 0:
            # Unreached true/false, don't include it. This should deal with some unwanted 'and true' expressions.
            if isinstance(body[0].contents[-1], nodes.Assignment) \
                    and len(body[0].contents[-1].expressions.contents) > 0 \
                    and isinstance(body[0].contents[-1].expressions.contents[-1], nodes.Primitive) \
                    and start_index + 1 < blocks[-1].index:
                start_index += 1
                continue

        try:
            expressions, unused = _find_expressions(start, body, end)
        except AttributeError:
            if catch_asserts:
                setattr(start, "_decompilation_error_here", True)
                print("-- WARNING: Error occurred during decompilation.")
                print("--   Code may be incomplete or incorrect.")
                expressions, unused = [], []
            else:
                raise

        if len(expressions) == 0:
            start_index += 1
            continue

        assert pack_set.isdisjoint(expressions)

        expressions_set = set(expressions)

        assert len(expressions_set) == len(expressions)

        endest_end = _find_endest_end(expressions)

        if endest_end != end:
            end_index = blocks.index(endest_end)

        if unused:
            expression_start_index = blocks.index(expressions[0][1])
            if expression_start_index > start_index + 1:
                # Too big of a gap, there may be stuff we missed
                # TODO Unsure if the check is still needed

                missed = []
                for i in range(0, len(unused)):
                    sub_block = unused[i][0]
                    for sub_index in range(start_index + 1, end_index - 1):
                        if sub_block == blocks[sub_index]:
                            missed.append(unused[i])

                missed_set = set(missed)

                assert len(missed_set) == len(missed)

                pack += list(reversed(missed))
                pack_set |= missed_set

        pack += list(reversed(expressions))
        pack_set |= expressions_set

        start_index = end_index

    return _unwarp_expressions_pack(blocks, pack)


def _find_endest_end(expressions):
    endest_end = expressions[0][2]

    for _, _, exp_end, *_ in expressions[1:]:
        if exp_end.index > endest_end.index:
            endest_end = exp_end

    return endest_end


def _unwarp_ifs(blocks, top_end=None, topmost_end=None):
    boundaries = []

    start_index = 0

    while start_index < len(blocks) - 1:
        start = blocks[start_index]
        warp = start.warp

        abort_loop = False
        if isinstance(warp, nodes.UnconditionalWarp):
            if warp.type == nodes.UnconditionalWarp.T_FLOW:
                start_index += 1
                continue

            # Remove unreachable True assignments that are the result of expressions in assignments
            while True:
                if len(start.contents) != 1 \
                        or not isinstance(start.contents[0], nodes.Assignment) \
                        or len(start.contents[0].destinations.contents) != 1 \
                        or start_index >= len(blocks) - 1:
                    break

                expression = start.contents[0].expressions.contents[0]
                if not isinstance(expression, nodes.Primitive) or expression.type != nodes.Primitive.T_FALSE:
                    break

                next_block = blocks[start_index + 1]
                if next_block.warpins_count != 0:
                    break

                if len(next_block.contents) != 1:
                    break

                expression = next_block.contents[0].expressions.contents[0]
                if not isinstance(expression, nodes.Primitive) or expression.type != nodes.Primitive.T_TRUE:
                    break

                abort_loop = True
                break

        body, end, end_index = _extract_if_body(start_index, blocks, topmost_end)

        if body is None:
            if catch_asserts:
                setattr(start, "_decompilation_error_here", True)
                print("-- WARNING: Error occurred during decompilation.")
                # print("--   GOTO statements are not supported")
                print("--   Code may be incomplete or incorrect.")
                _set_flow_to(start, blocks[start_index + 1])
                start_index += 1
                continue
            else:
                raise NotImplementedError("GOTO statements are not"
                                          " supported")

        is_end = isinstance(body[-1].warp, nodes.EndWarp)

        # Check for empty else blocks and skip them
        if is_end and len(body) == 1 and not body[0].contents \
                and _get_target(start.warp, True) == _get_target(body[0].warp, True):
            abort_loop = True

        if not abort_loop:
            try:
                _unwarp_if_statement(start, body, end, end)
            except (AssertionError, IndexError):
                if catch_asserts:
                    setattr(start, "_decompilation_error_here", True)
                    print("-- WARNING: Error occurred during decompilation.")
                    print("--   Code may be incomplete or incorrect.")
                else:
                    raise

        if is_end:
            _set_end(start)
        else:
            _set_flow_to(start, end)

        boundaries.append((start_index, end_index - 1))

        start_index = end_index

    return _remove_processed_blocks(blocks, boundaries)


def _extract_if_body(start_index, blocks, topmost_end):
    body = start_index > 0 and blocks[start_index:] or blocks
    end = _find_branching_end(body, topmost_end)

    try:
        end_index = blocks.index(end)
    except ValueError:
        if end == topmost_end:
            end_index = len(blocks)
        else:
            return None, None, None

    body = blocks[start_index + 1:end_index]

    return body, end, end_index


def _unwarp_expressions_pack(blocks, pack):
    replacements = {}

    for i, (block, start, end, slot, slot_type, slot_ref, needs_validation) in enumerate(reversed(pack)):
        end = replacements.get(end, end)

        start_index = blocks.index(start)
        end_index = blocks.index(end)

        is_special = False
        skip_expression = False
        before = blocks[:start_index]
        body = blocks[start_index + 1:end_index]

        if block == start and isinstance(block.warp, nodes.UnconditionalWarp):
            skip_expression = True

        if needs_validation:
            # Count the number of assignments. We want to skip long chains.
            num_assignments = 0
            for b in body:
                for c in b.contents:
                    if not isinstance(c, nodes.Assignment):
                        continue

                    if len(c.destinations.contents) != 1:
                        continue

                    if len(c.expressions.contents) != 1:
                        continue

                    destination = c.destinations.contents[0]
                    if is_equal(destination, slot_ref):
                        num_assignments += 1

            skip_expression = num_assignments > 2

        if needs_validation and not skip_expression and isinstance(start.warp, nodes.ConditionalWarp):
            # Make sure the special case should actually be an expression. These special cases have
            # no operations in their true warp, but be conservative and skip nested expressions
            for b in filter(lambda x: isinstance(x.warp, nodes.ConditionalWarp), [start] + body):
                if len(b.warp.true_target.contents) == 1 \
                        and isinstance(b.warp.true_target.contents[0], nodes.NoOp) \
                        and isinstance(b.warp.true_target.warp, nodes.UnconditionalWarp):

                    is_special = True
                    if b != start or (i > 0 and any(w != blocks[i - 1].warp for w in _find_warps_to(before, b))):
                        skip_expression = True
                        break

        if not skip_expression:
            # Check if there's any other warpins to the expressions body. If so,
            # then this subexpression will be taken care of later on
            for body_block in body:
                if _find_warps_to(before, body_block):
                    skip_expression = True
                    break

        if skip_expression:
            continue

        try:
            # Find the subexpression, and place it into the first block. After this
            #  point, the body of the subexpression is no longer needed.
            _unwarp_logical_expression(start, end, body)
        except (AssertionError, IndexError):
            if catch_asserts:
                setattr(start, "_decompilation_error_here", True)
                print("-- WARNING: Error occurred during decompilation.")
                print("--   Code may be incomplete or incorrect.")
            else:
                raise

        # Make sure the expression is equivalent -- check special case, it has to end with the destination
        if is_special:
            expression = start.contents[-1]

            skip_expression = True
            while True:
                if not isinstance(expression, nodes.Assignment):
                    break

                if len(expression.destinations.contents) != 1:
                    break

                if len(expression.expressions.contents) != 1:
                    break

                destination = expression.destinations.contents[0]
                value = expression.expressions.contents[0]

                if isinstance(value, nodes.BinaryOperator):
                    value = value.right

                if not is_equal(value, destination) and \
                        (not isinstance(value, nodes.Primitive) or value.type == nodes.Primitive.T_FALSE):
                    break

                skip_expression = False
                break

            if skip_expression:
                del start.contents[-1]
                continue


        # Note that from here on, this function has basically been rewritten
        #  in order to support subexpressions in subexpressions - eg:
        #
        # a = a and a[c or d]
        #
        # and this affected function calls too:
        #
        # a = a and a(c or d)
        #
        # These were generating results such as:
        #
        # if a then
        #  slot0 = a[c or d]
        # end
        # a = slot0
        #
        # (Actually this isn't it directly - it's to work with a modification
        #   made to _find_expressions, but this is where most of the changes occur)

        # Now the subexpression is gone, the start should warp to the block
        #  directly after the end of the subexpression, which is where the flow
        #  would have ended up anyway.
        _set_flow_to(start, end)

        # We no longer need the body, but there may still be some slots we need to eliminate before we lose
        # the definitions. This works because the expressions we found earlier still have a reference to
        # the nodes these body blocks. Create a temporary block to take care of this.
        if end_index - start_index > 2:
            # TODO: Avoid using a temporary block and process "unused" slots as well
            tmp_block = nodes.Block()
            first_block = blocks[start_index + 1]
            last_block = blocks[end_index - 1]
            tmp_block.first_address = first_block.first_address
            tmp_block.last_address = last_block.last_address
            tmp_block.index = first_block.index
            tmp_block.warpins_count = first_block.warpins_count
            tmp_block.warp = last_block.warp
            for j in range(start_index + 1, end_index):
                tmp_block.contents += blocks[j].contents
            slotworks.eliminate_temporary(tmp_block, False)

        # Leave the starting block in for now, but delete the rest of
        #  the body since we need to do so anyway and not doing so now
        #  will result in it ending up in end_warps
        del blocks[start_index + 1:end_index]

        # Here, we have to act in two different potential ways:
        #  - If there is an if condition that skips this subexpression and jumps straight to end, we
        #     should leave the expression in start, and leave end alone
        #  - If nothing else is referring to end, we should move the subexpression to it and delete the
        #     start node, compacting things down to ensure it gets used correctly later, in an enclosing
        #     subexpression.
        #
        # To do this, look for any nodes warping to the end block
        end_warps = _find_warps_to(blocks, end)

        # This should contain start, at the very least
        assert start in end_warps

        if start_index > 0:
            preceding_block = blocks[start_index - 1]
            if hasattr(preceding_block, "warp") \
                    and isinstance(preceding_block.warp, nodes.UnconditionalWarp):
                target_index = blocks.index(_get_target(preceding_block.warp))

                if target_index in range(start_index + 1, end_index - 1):
                    continue

        if len(end_warps) == 1:
            # Nothing (aside from the start block) is referring to the end block, thus it's safe
            #  to merge them.

            end.contents = start.contents + end.contents
            start.contents = []

            del blocks[start_index]

            _replace_targets(blocks, start, end)

            replacements[start] = end

            slotworks.eliminate_temporary(end, False)
            slotworks.simplify_ast(end, dirty_callback=slotworks.eliminate_temporary)
        else:
            slotworks.eliminate_temporary(start, False)
            slotworks.simplify_ast(end, dirty_callback=slotworks.eliminate_temporary)

    return blocks


def _split_by_slot_use(statements, min_i, warp, slot):
    known_slots = {slot}

    split_i = min_i

    for i, statement in enumerate(statements):
        if isinstance(statement, nodes.Assignment):
            sets = _extract_destination_slots(statement)

            if i < min_i:
                known_slots |= sets
            else:
                known_slots -= sets

            if len(known_slots) == 0:
                break

        split_i = i + 1

    if split_i < len(statements):
        return split_i

    if isinstance(warp, nodes.ConditionalWarp):
        known_slots -= _gather_slots(warp)

        if len(known_slots) == 0:
            split_i += 1

    return split_i


def _extract_destination_slots(statement):
    sets = set()

    for node in statement.destinations.contents:
        if not isinstance(node, nodes.Identifier):
            continue

        if node.type == nodes.Identifier.T_SLOT:
            sets.add(node.slot)

    return sets


def _gather_slots(node):
    class Collector(traverse.Visitor):
        def __init__(self):
            super().__init__()
            self.slots = set()

        def visit_identifier(self, visited_node):
            if visited_node.type == nodes.Identifier.T_SLOT:
                self.slots.add(visited_node.slot)

    collector = Collector()

    traverse.traverse(collector, node)

    return collector.slots


def _find_expressions(start, body, end, level=0, known_blocks=None):
    block = None
    known_blocks = known_blocks or set()
    known_blocks.add(start)

    def _add_warps_to_known_blocks(node):
        refs = None
        warp = node.warp
        if isinstance(warp, nodes.ConditionalWarp):
            refs = [warp.true_target, warp.false_target]
        elif isinstance(warp, nodes.UnconditionalWarp):
            refs = [warp.target]

        for ref in refs or []:
            if not ref: continue
            known_blocks.add(ref)

    _add_warps_to_known_blocks(start)

    # Explicitly allow the local a = x ~= "b" case
    slot, slot_type, slot_ref = _get_simple_local_assignment_slot(start, body, end)

    slot_assignments = []
    expressions = []
    unused = []

    # We have something at the end, but not the true/false?

    i = 0
    extbody = [start] + body

    is_local = False
    sure_expression = None
    needs_validation = False

    # Note the subexpression processing here has been rewritten from earlier versions - there
    #  used to be a problem where the following code:
    #
    # if a then
    #  if b then
    #   c()
    #  end
    #  d = e or f -- note, you need two of these
    #  g = h or i
    # end
    #
    # Would come out as the following:
    #
    # if a then
    #  if b then
    #   c()
    #   d = e or f
    #   g = h or i
    #  end
    # end
    #
    # It seems the processing wasn't taking note of the second (index=1) block, and
    #  this led to everything getting merged together. In the end it became quicker to
    #  rewrite the subexpression code, and avoid processing blocks already done so as part
    #  of the subexpression checks. So far I have not seen any issues with this, but if you find
    #  any (which isn't unlikely), please report it.
    #
    # Rewriting it also had the nice side-effect of cleaning up the code somewhat, since it's
    #  significantly shorter, easier to read readable, and should in fact run faster too.

    while i < len(extbody):
        current_i = i
        i += 1
        block = extbody[current_i]

        if block in known_blocks:
            _add_warps_to_known_blocks(block)

        subs = []
        subs_unused = []

        # Look for a self-contained conditional, and process that, then skip
        #  over it.
        branch_end = _find_branching_end(extbody[current_i:], None)
        if branch_end and branch_end in extbody:
            be_index = extbody.index(branch_end)
            i = be_index  # NOTE This misses things, so re-check it later

            body = extbody[current_i+1:be_index]
            subs, subs_unused = _find_expressions(block, body, branch_end, level + 1, known_blocks)

        if len(subs) != 0:
            endest_end = _find_endest_end(subs)
            new_i = extbody.index(endest_end)

            # Loop? No way!
            assert new_i > current_i

            # It should end with a conditional warp if that's
            # really a subexpression-as-operand
            end_warp = endest_end.warp

            # If any of the subexpressions are put into local variables, then this
            #  must be an if block, rather than an expression.
            for _, sub_start, sub_end, sub_slot, sub_slot_type, *_ in subs:
                if sub_slot_type == nodes.Identifier.T_LOCAL:
                    return expressions, unused

                # Search the body of the subexpression - if it contains anything other
                # than assignments, then it must be an if..end rather than an expression
                #
                # Here's an example of something that fails to decompile without this:
                #
                # local myvar = nil
                # if test_var then
                #         unrelated_func()
                #         myvar = (myvar or f()) + var
                # else
                #         unrelated_func()
                #         myvar = (myvar or f()) + var
                # end

                # Fetch the subexpression body
                sub_start_i = extbody.index(sub_start)
                sub_end_i = extbody.index(sub_end)
                sub_body = extbody[sub_start_i:sub_end_i]

                # And check it
                for sub_block in sub_body:
                    for item in sub_block.contents:
                        if not isinstance(item, nodes.Assignment):
                            return expressions, subs

            # TODO This can skip expressions in the current blocks body. Solved by a second call for now.

            expressions = subs + expressions
            i = new_i
            continue
        elif subs_unused:
            unused = subs_unused + unused
        elif i > current_i + 1:
            # We may not have checked all sub expressions
            i = current_i + 1

        if isinstance(block.warp, nodes.ConditionalWarp):
            condition = block.warp.condition

            is_end = block.warp.false_target == end
            is_binop = isinstance(condition, nodes.BinaryOperator)
            block_slot = getattr(block.warp, "_slot", slot)

            if is_end:
                if is_binop:
                    return expressions, unused
                elif slot < 0 <= block_slot:
                    slot = block_slot
                    slot_type = nodes.Identifier.T_SLOT
                    slot_ref = block

                    if sure_expression is None:
                        sure_expression = True
                elif slot != block_slot:
                    # TODO: We need to check the rest, but it's too eager
                    sure_expression = False
                    continue
                elif sure_expression is None:
                    sure_expression = True
            elif len(block.warp.true_target.contents) == 1:
                skip = False

                # Check for a special case 'x = y and z' that has a no-op condition in the true case
                if isinstance(block.warp.true_target.contents[0], nodes.NoOp) \
                        and isinstance(block.warp.true_target.warp, nodes.UnconditionalWarp):
                    sure_expression = True
                    needs_validation = True
                    skip = True
                if skip:
                    slot_ref = block
                    i += 1
                    continue

        elif isinstance(block.warp, nodes.UnconditionalWarp):
            if block == start and len(block.contents) == 0:
                return [], expressions

        if len(block.contents) == 0:
            continue

        if block != start and len(block.contents) > 1:
            return expressions, unused

        assignment = block.contents[-1]

        if not isinstance(assignment, nodes.Assignment):
            if block == start:
                continue

            if isinstance(assignment, nodes.NoOp):
                if _get_target(block.warp, True) != end:
                    continue

            return expressions, unused

        destinations = assignment.destinations.contents

        if len(destinations) != 1:
            if block == start:
                continue

            return expressions, unused

        if block.warpins_count == 0 and level > 0:
            return expressions, unused

        dst = destinations[0]

        if not isinstance(dst, nodes.Identifier):
            if block == start:
                continue

            return expressions, unused

        if isinstance(block.warp, nodes.ConditionalWarp):
            if block == start:
                continue

            return expressions, unused

        if not sure_expression and sure_expression is not None:
            return expressions, unused

        if slot < 0:
            # If all encounters are locals, which means
            # that the first encounter is a local
            if dst.type == nodes.Identifier.T_LOCAL:
                is_local = True
            elif dst.type == nodes.Identifier.T_UPVALUE:
                return [], expressions

            slot_assignments.append(assignment)

            slot = dst.slot
            slot_type = dst.type
            slot_ref = dst
        elif slot == dst.slot:
            slot_assignments.append(assignment)

            slot_type = dst.type
            slot_ref = dst

            if dst.type == nodes.Identifier.T_UPVALUE:
                return [], expressions
        else:
            assert block != start

            return [], expressions

    if slot < 0:
        return [], expressions

    true, _false, body = _get_terminators(body)

    if sure_expression is None:
        if true is not None:
            sure_expression = True

        if len(expressions) > 0 and block in known_blocks:
            matching_end_warp = False
            for _, _, exp_end, *_ in expressions:
                if exp_end.warp == block.warp:
                    matching_end_warp = True
                    break
            if not matching_end_warp:
                needs_validation = True  # may be better off as a regular if statement
                sure_expression = True

    if not sure_expression and is_local:
        allow_through = False

        # allow constants
        if len(slot_assignments) == 2 and (start.index == 0 or start.contents):
            value = slot_assignments[-2].expressions.contents[0]
            if isinstance(value, nodes.Constant) \
                    or (isinstance(value, nodes.Primitive) and value.type == nodes.Primitive.T_TRUE):

                allow_through = True
                # Constant assignment, but don't make it an expression if the previous assignment assigns the same slot
                if start.contents \
                        and isinstance(start.contents[-1], nodes.Assignment) \
                        and len(assignment.expressions.contents) == 1:
                    assignment = start.contents[-1]
                    expression = assignment.expressions.contents[0]
                    if isinstance(expression, nodes.Primitive) and expression.type == nodes.Primitive.T_NIL:
                        for dst in assignment.destinations.contents:
                            if isinstance(dst, nodes.Identifier) and dst.slot == slot:
                                allow_through = False
                                break

        if not allow_through:
            return expressions, unused

    # TODO Actually prevent bad blocks from being part of the body instead of trying to eliminate it here
    if not sure_expression and block not in known_blocks and \
            (isinstance(end, nodes.EndWarp) or extbody.index(block) < len(extbody) - 1):
        return expressions, unused

    return expressions + [(block, start, end, slot, slot_type, slot_ref, needs_validation)], unused


def _get_simple_local_assignment_slot(start, body, end):
    if len(body) != 2:
        return -1, None, None

    true, _false, body = _get_terminators(body)

    if true is None:
        return -1, None, None
    else:
        slot = true.contents[0].destinations.contents[0]
        if not isinstance(slot, nodes.TableElement):
            return slot.slot, slot.type, slot
        elif isinstance(slot.table, nodes.Identifier):
            return slot.table.slot, slot.table.type, slot.table
        else:
            return -1, None, None


def _find_expression_slot(body):
    slot = None

    for block in reversed(body):
        if len(block.contents) == 0: # TODO Why was this != 1? Does it always need to be just one?
            continue

        slot = block.contents[-1].destinations.contents[0]
        break

    return slot


def _unwarp_logical_expression(start, end, body):
    slot = _find_expression_slot(body)

    assert slot is not None

    true, false, body = _get_terminators(body)

    expression = _compile_expression([start] + (body or []), end, true, false)

    dst = copy.deepcopy(slot)

    assignment = nodes.Assignment()
    assignment.destinations.contents.append(dst)
    assignment.expressions.contents.append(expression)

    start.contents.append(assignment)


def _compile_expression(body, end, true, false):
    parts = _unwarp_expression(body, end, true, false)

    if len(parts) < 3:
        assert len(parts) == 1
        return parts[0]

    explicit_parts = _make_explicit_subexpressions(parts)
    expr = _assemble_expression(explicit_parts)
    expr = _optimise_expression(expr)
    return expr


# Rearrange the contents of the expression (without changing it's meaning), to make it easier for the writer
#  to write without adding unnecessary braces. To do that, ensure that chains of operators appear in the
#  correct direction - eg, make (1 + (2 + 3)) into ((1 + 2) + 3). This can't be done on non-commutative
#  operators.
def _optimise_expression(expr, skip_type=None):
    if not isinstance(expr, nodes.BinaryOperator):
        return expr

    type = expr.type

    expr.left = _optimise_expression(expr.left, skip_type=type)
    expr.right = _optimise_expression(expr.right, skip_type=type)

    # Don't reorganise children of a top-level node that's already being reorganised
    if skip_type == expr.type:
        return expr

    # If this operator isn't commutative, we can't rearrange anything for it
    if not expr.is_commutative():
        return expr

    # While == and != are commutative, we can't swap them around like this
    if nodes.BinaryOperator.T_NOT_EQUAL <= expr.type <= nodes.BinaryOperator.T_EQUAL:
        return expr

    # Don't bother handling right-associative operators for now, since that currently only
    #  includes the exponent operator, which isn't commutative.
    if expr.is_right_associative():
        return expr

    children = _find_binary_operator_children(expr, type)

    expr = children.pop(0)
    for op in children:
        next = nodes.BinaryOperator()
        next.type = type
        next.left = expr
        next.right = op
        expr = next

    return expr


def _find_binary_operator_children(op, type):
    if not isinstance(op, nodes.BinaryOperator):
        return [op]

    if op.type != type:
        return [op]

    return _find_binary_operator_children(op.left, type) + _find_binary_operator_children(op.right, type)


#
# The logical expressions:
#
# There are terminators: a true, a false and an end
#
# For an if case the true will be a "then" clause and the false - an "else" or
# "after-the-if" clause. The end is required for a single-variable (unary)
# components and is only used at during topmost phase.
#
# The last block in expression is always "double terminal" - both ends are
# pointing at terminators. It's rather useless so we just append it's condition
# (inverted if needed - it's easy to see if true end targets the false
# terminator) at the end of processing.
#
# Then we need to pack all other blocks into subexpressions. Subexpressions
# always end with a _terminal block_, i.e. the block which warp points to a
# terminator. Idea is that we can guess the operator only right of a
# terminal block, because we can check if the block's warp condition is
# inverted or not.
#
# If that's an "OR" clause then it will jump out of the current expression if
# the condition is true, so the condition is inverted and the false branch is
# pointing at the way out (at the TRUE terminator - because the result of the
# expression level will be true). (because in the bytecode there
# is only one JMP, so a ConditionalWarp's true branch is actually a fake and
# always points to the next block - in the bytecode a "positive" jump
# will be represented by a normal negative jump with inverted condition).
#
# Otherwise, if that's an "AND" clause then it will jump out of the current
# expression level if a condition is false, so the condition is not inverted
# and a false branch points to the false.
#
# This way we can understand which operators go just right of terminal blocks.
# Everything in-between these block is considered a subexpression. And just
# because we don't know where exactly the subexpression ends we are using
# greedy approach and trying to pack into a subexpression as much blocks as
# possible, including any terminal blocks pointing at the same terminator
# with the same inversion status (that is - we are always using the
# rightmost block if there are consequitive similar terminal blocks, ignoring
# all the blocks to the left).
#
# Then comes the trick: the subexpression is a component of this expression and
# we know the operator to the right of it. We can guess now what will
# be evaluated if the subexpression evaluates to "false" and what - if it's
# "true". If the operator is "AND" then the subexpression failure will cause
# the expression failure too, i.e. the "FALSE" target remains the same and the
# true terminator is set to the next block (after the "AND").
#
# If the operator is "OR" the the subexpression success will cause the success
# of the expression, so the "TRUE" target remains the same, but the false
# target is set to the next block (after the "OR").
#
# Now we have a subexpression and both TRUE and FALSE terminators for it.
# Recurse and repeat.
#
def _unwarp_expression(body, end, true, false):
    parts = []

    if true is not None:
        terminator_index = min(true.index, false.index)

        if end is not None:
            terminator_index = min(end.index, terminator_index)
    else:
        assert end is not None

        terminator_index = end.index

    terminators = [true, false, end]

    subexpression_start = 0

    i = 0
    while i < len(body) - 1:
        block = body[i]
        warp = block.warp

        target = _get_target(warp)

        #
        # A chance for
        # (foo and (bar and y or z)) or x
        # type expressions, because the first "foo and ... )) or" part
        # will be broken by the "or z))" part in the code below.
        #
        # So we are going to intercept subexpressions by it's start
        # instead of an end, but only if we are already at the
        # subexpression start (so nothing formally changes, but creates
        # a bit more correct execution order)
        #
        if target.index < terminator_index:
            if i != subexpression_start:
                i += 1
                continue

            target_index = body.index(target)
            last_block = body[target_index - 1]

            last_block_target = _get_target(last_block.warp)

            if last_block_target.index < terminator_index:
                i += 1
                continue

            assert last_block_target in terminators

            subexpression = body[i:target_index]
        else:
            # assert target in terminators

            while i < len(body) - 2:
                next_block = body[i + 1]
                next_target = _get_target(next_block.warp)

                if next_target != target:
                    break

                next_inv = _is_inverted(next_block.warp, true, end)

                this_inv = _is_inverted(warp, true, end)

                # Special hack for unary expressions (x, not x)...
                if next_inv != this_inv:
                    break

                warp = next_block.warp
                i += 1

            subexpression = body[subexpression_start:i + 1]

        last_block = subexpression[-1]
        last_block_index = body.index(last_block)

        next_block = body[last_block_index + 1]

        operator = _get_operator(last_block, true, end)

        new_subexpression = _compile_subexpression(subexpression, operator,
                                               last_block, next_block,
                                               true, end)

        if new_subexpression:
            parts.append(new_subexpression)
            parts.append(operator)

        i = last_block_index + 1
        subexpression_start = i

    last = body[-1]

    if isinstance(last.warp, nodes.ConditionalWarp):
        if _is_inverted(last.warp, true, end):
            last = _invert(last.warp.condition)
        else:
            last = last.warp.condition

        parts.append(last)
    else:
        assert isinstance(last.warp, (nodes.EndWarp,
                                      nodes.UnconditionalWarp))

        src = _get_last_assignment_source(last)

        if src is None:

            special = None
            if len(last.contents) == 1 and isinstance(last.contents[0], nodes.NoOp):
                # Check for a special A = B and A case
                if false.warpins_count == 0 and len(true.contents) == 1:
                    special = false
                elif true.warpins_count == 0 and len(false.contents) == 1:
                    special = true

            if special and special.contents:
                # Special case: use destination
                assignment = special.contents[-1]
                src = assignment.destinations.contents[0]
            else:
                src = nodes.Primitive()

                if last.warp.target == true:
                    src.type = nodes.Primitive.T_TRUE
                else:
                    src.type = nodes.Primitive.T_FALSE

        parts.append(src)

    return parts


def _get_target(warp, allow_end=False):
    if isinstance(warp, nodes.ConditionalWarp):
        return warp.false_target
    else:
        if allow_end and isinstance(warp, nodes.EndWarp):
            return getattr(warp, "_target", None)

        assert isinstance(warp, nodes.UnconditionalWarp)
        return warp.target


def _set_target(warp, target):
    if isinstance(warp, nodes.ConditionalWarp):
        warp.false_target = target
    else:
        assert isinstance(warp, nodes.UnconditionalWarp)
        warp.target = target


def _get_operator(block, true, end):
    if isinstance(block.warp, nodes.UnconditionalWarp):
        src = _get_last_assignment_source(block)

        if isinstance(src, nodes.Constant):
            is_true = True
        elif isinstance(src, nodes.BinaryOperator):
            is_true = True
        elif isinstance(src, nodes.Primitive):
            is_true = src.type == nodes.Primitive.T_TRUE
        elif isinstance(src, nodes.Identifier):
            is_true = True
        # walterr: apparently unnecessary?
        # elif isinstance(src, nodes.NoOp):
        #     is_true = block.warp.target == end
        else:
            # assert src is None

            is_true = block.warp.target == true

        if is_true:
            return binop.T_LOGICAL_OR
        else:
            return binop.T_LOGICAL_AND
    else:
        is_inverted = _is_inverted(block.warp, true, end)

        if is_inverted:
            return binop.T_LOGICAL_OR
        else:
            return binop.T_LOGICAL_AND


def _get_last_assignment_source(block):
    if len(block.contents) == 0:
        return None

    assignment = block.contents[-1]

    if isinstance(assignment, nodes.Assignment):
        return assignment.expressions.contents[0]
    elif isinstance(assignment, nodes.FunctionCall):
        return None
    elif isinstance(assignment, nodes.NoOp):
        return None
    elif isinstance(assignment, nodes.Return):
        return assignment.returns.contents[0]
    else:
        assert False


def _get_and_remove_last_assignment_source(block):
    assignment = block.contents.pop()

    if False:  # TODO(yzg)
        assert isinstance(assignment, nodes.Assignment)
        return assignment.expressions.contents[0]
    else:
        if isinstance(assignment, nodes.Assignment):
            return assignment.expressions.contents[0]
        else:
            return assignment


def _compile_subexpression(subexpression, operator,
                           block, next_block, true, end):
    warp = block.warp

    if len(subexpression) == 1:
        if isinstance(warp, nodes.UnconditionalWarp):
            return _get_and_remove_last_assignment_source(block)
        elif _is_inverted(warp, true, end):
            return _invert(warp.condition)
        else:
            return warp.condition
    else:
        if isinstance(warp, nodes.UnconditionalWarp):
            if operator == binop.T_LOGICAL_OR:
                subtrue = warp.target
                subfalse = next_block
            else:
                subtrue = next_block
                subfalse = warp.target
        else:
            if operator == binop.T_LOGICAL_OR:
                subtrue = warp.false_target
                subfalse = warp.true_target
            else:
                subtrue = warp.true_target
                subfalse = warp.false_target

        return _unwarp_expression(subexpression, None, subtrue, subfalse)


def _is_inverted(warp, true, end):
    if isinstance(warp, nodes.UnconditionalWarp):
        return warp.target == end

    if warp.false_target == true:
        return True
    elif warp.false_target == end:
        assert not isinstance(warp.condition, nodes.BinaryOperator)

        if not isinstance(warp.condition, nodes.UnaryOperator):
            return False

        return warp.condition.type == nodes.UnaryOperator.T_NOT

    return False


_NEGATION_MAP = [None] * 100

_NEGATION_MAP[binop.T_LESS_THEN] = binop.T_GREATER_OR_EQUAL
_NEGATION_MAP[binop.T_GREATER_THEN] = binop.T_LESS_OR_EQUAL
_NEGATION_MAP[binop.T_LESS_OR_EQUAL] = binop.T_GREATER_THEN
_NEGATION_MAP[binop.T_GREATER_OR_EQUAL] = binop.T_LESS_THEN

_NEGATION_MAP[binop.T_NOT_EQUAL] = binop.T_EQUAL
_NEGATION_MAP[binop.T_EQUAL] = binop.T_NOT_EQUAL


def _invert(expression):
    if isinstance(expression, nodes.UnaryOperator):
        return expression.operand

    if not isinstance(expression, nodes.BinaryOperator):
        node = nodes.UnaryOperator()
        node.type = nodes.UnaryOperator.T_NOT
        node.operand = expression

        return node

    # Just in case
    expression = copy.deepcopy(expression)

    new_type = _NEGATION_MAP[expression.type]

    if new_type is None:
        if expression.type == binop.T_LOGICAL_OR:
            new_type = binop.T_LOGICAL_AND
        elif expression.type == binop.T_LOGICAL_AND:
            new_type = binop.T_LOGICAL_OR

        expression.left = _invert(expression.left)
        expression.right = _invert(expression.right)

    assert new_type is not None

    expression.type = new_type

    return expression


def _get_terminators(body):
    if len(body) < 2:
        return None, None, body

    last = body[-1]

    if len(last.contents) != 1:
        return None, None, body

    assignment = last.contents[0]

    if not isinstance(assignment, nodes.Assignment):
        return None, None, body

    src = assignment.expressions.contents[0]

    if not isinstance(src, nodes.Primitive) or src.type != src.T_TRUE:
        return None, None, body

    prev = body[-2]

    if len(prev.contents) != 1:
        return None, None, body

    # TODO(yzg) origin: src = prev.contents[0].expressions.contents[0]
    if hasattr(prev.contents[0], "expressions"):
        src = prev.contents[0].expressions.contents[0]
    else:
        src = prev.contents[0]

    if not isinstance(src, nodes.Primitive) or src.type != src.T_FALSE:
        return None, None, body

    return last, prev, body[:-2]


def _assemble_expression(parts):
    if not isinstance(parts, list):
        return parts

    if len(parts) == 1:
        return parts[0]

    node = nodes.BinaryOperator()
    node.left = _assemble_expression(parts[-3])

    node.type = parts[-2]
    assert isinstance(node.type, int)

    node.right = _assemble_expression(parts[-1])

    i = len(parts) - 4

    while i > 0:
        operator = parts[i]
        component = parts[i - 1]

        upper_node = nodes.BinaryOperator()
        upper_node.right = node
        upper_node.left = _assemble_expression(component)

        upper_node.type = operator

        node = upper_node

        i -= 2

    return node


# Split the topmost expression into smaller subexpressions at each
# operator change to simplify the assembly phase
def _make_explicit_subexpressions(parts):
    patched = []

    i = 0

    last_operator = parts[1]
    subexpression_start = -1

    while i < len(parts) - 1:
        component = parts[i]
        operator = parts[i + 1]

        if operator < last_operator:
            subexpression_start = i
            last_operator = operator
        elif subexpression_start > 0:
            if operator > last_operator \
                    and (i - subexpression_start) % 2 != 0:
                subexpression = parts[subexpression_start:i]

                patched.append(subexpression)
                subexpression_start = -1
        else:
            patched += [component, operator]

        i += 2

    if subexpression_start >= 0:
        patched.append(parts[subexpression_start:])
    else:
        patched.append(parts[-1])

    return patched


def _unwarp_if_statement(start, body, end, topmost_end):
    expression, body, false = _extract_if_expression(start, body, end,
                                                     topmost_end)

    node = nodes.If()
    node.expression = expression

    # has an else branch
    if false != end and false != topmost_end:
        else_start = false

        else_start_index = body.index(else_start)

        then_body = body[:else_start_index]

        then_warp_out = then_body[-1].warp

        assert _is_jump(then_warp_out)
        assert then_warp_out.target in (end, topmost_end)

        else_body = body[else_start_index:]

        else_warp_out = else_body[-1].warp

        if isinstance(else_warp_out, nodes.UnconditionalWarp):
            if else_warp_out.type == nodes.UnconditionalWarp.T_JUMP:
                assert else_warp_out.target in (end, topmost_end)
            else:
                assert else_warp_out.target == end
        else:
            assert isinstance(else_warp_out, nodes.EndWarp)

        _set_end(then_body[-1])
        then_blocks = _unwarp_ifs(then_body, then_body[-1], topmost_end)
        node.then_block.contents = then_blocks

        _set_end(else_body[-1])
        else_blocks = _unwarp_ifs(else_body, else_body[-1], topmost_end)
        node.else_block.contents = else_blocks

        if _get_target(then_warp_out, True) == _get_target(else_warp_out, True) \
                and len(then_blocks) == 1 \
                and len(then_blocks[0].contents) == 1 \
                and isinstance(then_blocks[0].contents[0], nodes.NoOp):

            # Good to merge, but we don't want to break up else-ifs
            if len(else_blocks) != 1 or not isinstance(else_blocks[0].contents[-1], nodes.If):

                # Invert condition and move else block to then
                node.expression = _invert(expression)
                node.then_block.contents = else_blocks
                node.else_block.contents = []

    else:
        warp_out = body[-1].warp

        if not isinstance(warp_out, nodes.EndWarp):
            assert isinstance(warp_out, nodes.UnconditionalWarp)
            assert warp_out.target in (end, topmost_end)

        _set_end(body[-1])
        then_blocks = _unwarp_ifs(body, body[-1], topmost_end)
        node.then_block.contents = then_blocks

    start.contents.append(node)


def _extract_if_expression(start, body, end, topmost_end):
    i = 0
    for i, block in enumerate(body):
        if len(block.contents) != 0:
            break

    assert i < len(body)

    expression = [start] + body[:i]
    body = body[i:]

    falses = set()

    for i, block in enumerate(body[:-1]):
        if not isinstance(block.warp, nodes.UnconditionalWarp):
            continue

        if block.warp.type != nodes.UnconditionalWarp.T_JUMP:
            continue

        if block.warp.target != end and block.warp.target != topmost_end:
            continue

        falses.add(body[i + 1])

    falses.add(end)

    if topmost_end is not None:
        falses.add(topmost_end)

    false, end_i = _search_expression_end(expression, falses)

    if false is None:
        unpacked_falses = sorted(falses,
                                 key=lambda unpacked_false: unpacked_false.index)
        false = unpacked_falses[-1]
        end_i = len(expression)

    assert false is not None
    assert end_i >= 0

    body = expression[end_i:] + body
    expression = expression[:end_i]

    assert len(expression) > 0

    true = body[0]

    expression = _compile_expression(expression, None, true, false)

    return expression, body, false


def _search_expression_end(expression, falses):
    expression_end = -1
    false = None

    for i, block in enumerate(expression):
        target = _get_target(block.warp, True)

        if target not in falses:
            continue

        if false is None or target == false:
            false = target
            expression_end = i + 1
        else:
            break

    return false, expression_end


def _find_branching_end(blocks, topmost_end, loop_start=None):
    end = blocks[0]

    for block in blocks:
        warp = block.warp

        target = _get_target(warp, allow_end=True)

        if isinstance(warp, nodes.EndWarp) and target is None:
            try:
                assert block == end
            except AssertionError:
                if catch_asserts:
                    setattr(block, "_decompilation_error_here", True)
                    print("-- WARNING: Error occurred during decompilation.")
                    print("--   Code may be incomplete or incorrect.")
                    if hasattr(end, "warp") and _get_target(end.warp) == block:
                        return end
                else:
                    raise
            return block

        if isinstance(warp, nodes.UnconditionalWarp) and target == end:
            return end

        if target.index > end.index:
            end = target

    return end


def _remove_processed_blocks(blocks, boundaries):
    remains = []
    last_end_index = -1

    for start, end in boundaries:
        if start == end:
            up_to_index = start
        else:
            up_to_index = start + 1

        remains += blocks[last_end_index + 1:up_to_index]
        last_end_index = end

    remains += blocks[last_end_index + 1:]

    return remains


# ##
# ## LOOPS PROCESSING
# ##


def _fix_loops(blocks, repeat_until):
    loops = _find_all_loops(blocks, repeat_until=repeat_until)

    if len(loops) == 0:
        return blocks

    fixed = _cleanup_breaks_and_if_ends(loops, blocks)

    replacements = {}

    for start, end in fixed:
        end = replacements.get(end, end)
        start_index = blocks.index(start)
        end_index = blocks.index(end)

        # Try and find the outermost loop-marking block - this indicates the start of the
        # loop body is the next block.
        loop_block = None
        for block in blocks[start_index:end_index]:
            if block.loop:
                loop_block = block
                break

        # If this is an iterator loop (for a in b), then there's no body marker (for other types
        # of loops, block.loop would be set on the last block before the body). In this case, don't
        # use the detected loop block as that would cause issues, such as in this program:
        #
        # for a in b do
        #   if id then
        #     for i = c, d, 1 do
        #       print(i)
        #     end
        #   end
        # end
        if isinstance(start.warp, nodes.IteratorWarp):
            loop_block = None

        if not loop_block:
            blocks = _handle_single_loop(start, end, blocks, repeat_until)
            continue

        assert loop_block

        body_start_index = blocks.index(loop_block)

        # Skip the LOOP (or similar) instruction
        # Note that is it guaranteed that there will only be repeat...until loops if
        #  repeat_until is set, due to `assert not repeat_until` in _find_all_loops
        # Also note we don't do this in repeat...until loops is that their first block
        #  contains the user's code, and skipping this would omit that
        if body_start_index == start_index and not repeat_until:
            body_start_index += 1

        loop = _unwarp_loop(start, end, expr_body=blocks[start_index:body_start_index], body=blocks[body_start_index:end_index])
        body = loop.statements.contents

        block = _loop_build_block(start, body, end, blocks, loop, body_start_index)

        if body_start_index == start_index:
            blocks = blocks[:start_index + 1] + [block] + blocks[end_index:]
        else:
            if isinstance(loop, nodes.While) and start_index < body_start_index - 1:
                if any(len(node.contents) > 0 for node in blocks[start_index:body_start_index]):
                    start_index = body_start_index

                # TODO deal with mixed conditions and sub expressions
                before = blocks[:start_index]
                if before:
                    old_start = blocks[start_index]
                    _replace_targets(before, old_start, block)
                    replacements[old_start] = block
            else:
                before = blocks[:body_start_index]
            blocks = before + [block] + blocks[end_index:]

        for i, block in enumerate(body):
            warp = block.warp

            if _is_flow(warp):
                assert _get_target(warp) == body[i + 1]

            if isinstance(warp, nodes.ConditionalWarp):
                assert warp.true_target in body
                assert warp.false_target in body
            elif isinstance(warp, nodes.UnconditionalWarp):
                if warp.target:
                    assert warp.target in body

    for i, block in enumerate(blocks):
        warp = block.warp

        if _is_flow(warp):
            assert _get_target(warp) == blocks[i + 1]

        if isinstance(warp, nodes.ConditionalWarp):
            assert warp.true_target in blocks
            assert warp.false_target in blocks
        else:
            target = _get_target(warp, True)
            if target:
                assert target in blocks

    return blocks


def _handle_single_loop(start, end, blocks, repeat_until):
    start_index = blocks.index(start)
    end_index = blocks.index(end)

    if repeat_until:
        body = blocks[start_index:end_index]
    else:
        body = blocks[start_index + 1:end_index]

    loop = _unwarp_loop(start, end, body)
    body = loop.statements.contents

    block = _loop_build_block(start, body, end, blocks, loop, start.index + 1)

    blocks = blocks[:start_index + 1] + [block] + blocks[end_index:]
    return blocks


def _loop_build_block(start, body, end, blocks, loop, block_index):
    block = nodes.Block()
    block.first_address = body[0].first_address
    block.last_address = body[-1].last_address
    block.index = block_index
    block.contents.append(loop)

    block.warp = nodes.UnconditionalWarp()
    block.warp.type = nodes.UnconditionalWarp.T_FLOW
    block.warp.target = end

    _replace_targets(blocks, body[0], block)

    # Don't set the _target property of the end block - this will trip up the
    # verification logic down below in very specific situations.
    # See https://gitlab.com/znixian/luajit-decompiler/issues/7#note_149912326
    # for an explanation of why this is a problem.
    # To elaborate on the 'invalid value' part of the comment: this will normally
    # (for nested loops) set an invalid _target property for the end block - that is,
    # it's pointing outside the contents of the loop. This isn't caught by the
    # validator below, since it's still within the 'blocks' variable.
    _set_end(body[-1], force_no_target=True)

    _unwarp_breaks(start, body, end)

    return block


def _unwarp_loops(blocks, repeat_until):
    loops = _find_all_loops(blocks, repeat_until)

    assert not loops

    return blocks


def _cleanup_breaks_and_if_ends(loops, blocks):
    outer_start_index = -1
    outer_end = None

    current_start_index = -1
    current_end = None

    fixed = []

    for start, end in loops:
        if start.index in (outer_start_index, current_start_index):
            end_i = blocks.index(end)
            last_in_body = blocks[end_i - 1]
            warp = last_in_body.warp

            assert isinstance(warp, nodes.UnconditionalWarp)
            assert warp.target == start

            # Break
            if start.index == outer_start_index:
                assert outer_end is not None

                outer_end_i = blocks.index(outer_end)
                warp.target = blocks[outer_end_i - 1]

                assert blocks[outer_end_i - 2] != end
            else:
                assert current_end is not None
                assert start.index == current_start_index

                current_end_i = blocks.index(current_end)

                last = blocks[current_end_i - 1]

                if last == end:
                    last = _create_next_block(end)
                    last.warp = end.warp

                    _set_flow_to(end, last)

                    blocks.insert(current_end_i, last)

                assert not last.contents
                assert isinstance(last.warp, nodes.UnconditionalWarp)
                assert last.warp.target == start

                warp.target = last
        else:
            fixed.append((start, end))

            if current_end is not None \
                    and current_start_index < start.index \
                    and current_end.index >= end.index:
                outer_start_index = current_start_index
                outer_end = current_end
            else:
                outer_start_index = -1
                outer_end = None

            current_start_index = start.index
            current_end = end

    return fixed


def _replace_targets(blocks, original, replacement, allow_add_jumpback=False):
    for block in blocks:
        warp = block.warp

        if isinstance(warp, nodes.UnconditionalWarp):
            if warp.target == original:
                warp.target = replacement
        elif isinstance(warp, nodes.ConditionalWarp):
            if warp.true_target == original:
                warp.true_target = replacement

            if warp.false_target == original \
                    and (warp.false_target.last_address > block.last_address or allow_add_jumpback):
                warp.false_target = replacement
        elif isinstance(warp, nodes.EndWarp):
            pass
        else:
            if warp.way_out == original:
                warp.way_out = replacement

            if warp.body == original:
                warp.body = replacement


def _unwarp_loop(start, end, body, expr_body=None):
    if len(body) > 0:
        last = body[-1]
    else:
        last = start

    if isinstance(start.warp, nodes.IteratorWarp):
        assert isinstance(last.warp, nodes.UnconditionalWarp)
        assert last.warp.target == start

        loop = nodes.IteratorFor()
        loop.statements.contents = body
        loop.identifiers = start.warp.variables
        loop.expressions = start.warp.controls
        loop._addr = body[0].first_address

        _set_flow_to(start, body[0])

    elif isinstance(start.warp, nodes.NumericLoopWarp):
        assert isinstance(last.warp, nodes.UnconditionalWarp)
        assert last.warp.target == start

        loop = nodes.NumericFor()
        loop.statements.contents = body
        loop.variable = start.warp.index
        loop.expressions = start.warp.controls
        loop._addr = body[0].first_address
        _set_flow_to(start, body[0])

    # While (including "while true" and "repeat until false")
    elif isinstance(last.warp, nodes.UnconditionalWarp):
        assert last.warp.target == start

        # while true / repeat until false
        if _is_flow(start.warp):

            prev_to_last = body[-2] if len(body) > 1 else None
            if prev_to_last and isinstance(prev_to_last.warp, nodes.UnconditionalWarp) \
                    and prev_to_last.warp.type == nodes.UnconditionalWarp.T_JUMP \
                    and prev_to_last.warp.target == last \
                    and (len(body) <= 2 or _is_flow(body[-3].warp)):  # not strictly needed, but better be safe
                loop = nodes.RepeatUntil()
                loop.expression = nodes.Primitive()
                loop.expression.type = nodes.Primitive.T_FALSE
                body.pop()  # Remove the jump block specific to this case
            else:
                loop = nodes.While()
                loop.expression = nodes.Primitive()
                loop.expression.type = nodes.Primitive.T_TRUE

            loop.statements.contents = body
        else:
            # There shouldn't be many problems similar to ifs, as
            # we are processing loops in the order from innermost
            # to outermost
            i = 0
            for i, block in enumerate(body):
                # walterr seems to be the only actual code change on the
                # 'experimental' branch.
                # assert len(block.contents) == 0

                if _is_flow(block.warp):
                    break

            assert i < len(body)

            expression = expr_body + body[:i]
            body = body[i:]

            # Sometimes expression may decide to jump to the
            # outer loop start instead
            _fix_expression(expression, start, end)

            true = body[0]
            false = end

            expression = _compile_expression(expression, None,
                                             true, false)

            # If something jumps to the start (instead of the end)
            # - that's a nested if
            loop = nodes.While()
            loop.expression = expression
            loop.statements.contents = body

        _fix_nested_ifs(body, start)

        condition_end = expr_body[-1] if expr_body else start
        _set_flow_to(condition_end, body[0])

    # Repeat until
    else:
        assert isinstance(last.warp, nodes.ConditionalWarp)
        assert last.warp.false_target == start

        i = len(body) - 1

        while i >= 0:
            block = body[i]
            warp = block.warp

            if _is_flow(warp):
                i += 1
                break

            if len(block.contents) != 0:
                break

            i -= 1

        expression = body[i:]
        body = body[:i + 1]

        assert len(expression) > 0

        first = expression[0]
        if _is_jump(first.warp):
            # Don't append to the body - it already has it
            expression.pop(0)
            if len(body[-1].contents) == 1 and isinstance(body[-1].contents, nodes.NoOp):
                body[-1].contents = []
            body[-1].contents.append(nodes.Break())

        false = body[0]
        # Don't use end as it could be broken by a previous
        # repeat until pass
        true = expression[-1].warp.true_target

        loop = nodes.RepeatUntil()
        loop.expression = _compile_expression(expression, None,
                                              true, false)

        start_copy = copy.copy(start)
        start.contents = []

        if len(body) > 1:
            _set_flow_to(start_copy, body[1])
        else:
            _set_end(start_copy)

        _set_flow_to(start, start_copy)

        body[0] = start_copy

        loop.statements.contents = body

    return loop


def _create_next_block(original):
    block = nodes.Block()
    block.first_address = original.last_address + 1
    block.last_address = block.first_address
    block.index = original.index + 1
    block.warpins_count = original.warpins_count

    return block


def _set_flow_to(block, target):
    block.warp = nodes.UnconditionalWarp()
    block.warp.type = nodes.UnconditionalWarp.T_FLOW
    block.warp.target = target


def _set_end(block, force_no_target=False):
    target = None

    if block.warp is not None and not force_no_target:
        target = _get_target(block.warp, allow_end=True)

    block.warp = nodes.EndWarp()

    setattr(block.warp, "_target", target)


def _is_flow(warp):
    return isinstance(warp, nodes.UnconditionalWarp) \
           and warp.type == nodes.UnconditionalWarp.T_FLOW


def _is_jump(warp):
    return isinstance(warp, nodes.UnconditionalWarp) \
           and warp.type == nodes.UnconditionalWarp.T_JUMP


def _fix_nested_ifs(blocks, start):
    # We can't point both targets of a conditional warp to the
    # same block. We will have to create a new block
    last = _create_next_block(blocks[-1])

    if isinstance(blocks[-1].warp, nodes.ConditionalWarp):
        blocks[-1].warp.false_target = last
    else:
        _set_flow_to(blocks[-1], last)

    blocks.append(last)
    _set_end(last)

    for block in blocks[:-1]:
        target = _get_target(block.warp)

        if target == start:
            _set_target(block.warp, last)


def _fix_expression(blocks, start, end):
    for block in blocks:
        if len(block.contents) != 0:
            break

        target = _get_target(block.warp)

        if target.index < start.index:
            _set_target(block.warp, end)


def _gather_possible_ends(block):
    warp = block.warp

    ends = {block}

    while _is_jump(warp):
        block = warp.target
        warp = block.warp

        ends.add(block)

    return ends


BREAK_INFINITE = 0
BREAK_ONE_USE = 1


def _unwarp_breaks(start, blocks, next_block):
    blocks_set = set([start] + blocks)

    ends = _gather_possible_ends(next_block)

    breaks = set()

    patched = []

    for i, block in enumerate(blocks):
        warp = block.warp

        if not isinstance(warp, nodes.UnconditionalWarp):
            patched.append(block)
            continue

        target = _get_target(warp)

        if target in blocks_set:
            patched.append(block)
            continue

        assert target in ends, "GOTO statements are not supported"

        if block.warpins_count != 0 \
                and not (len(block.contents) == 1 and isinstance(block.contents[0], nodes.NoOp)):
            new_block = _create_next_block(block)
            new_block.warpins_count = block.warpins_count
            _set_flow_to(block, new_block)

            patched.append(block)
            patched.append(new_block)

            block = new_block
        else:
            patched.append(block)

        if len(block.contents) == 1 and isinstance(block.contents[0], nodes.NoOp):
            block.contents = []
        block.contents.append(nodes.Break())

        if i + 1 == len(blocks):
            _set_end(block)
        else:
            _set_flow_to(block, blocks[i + 1])

        breaks.add(block)

    blocks[:] = patched

    if len(breaks) == 0:
        return

    breaks_stack = []
    warps_out = []
    pending_break = None

    for i, block in enumerate(reversed(blocks)):
        if block in breaks:
            pending_break = None

            if block.warpins_count == 0:
                breaks_stack.append((BREAK_ONE_USE, block))
            else:
                breaks_stack.append((BREAK_INFINITE, block))

            continue

        warp = block.warp

        if not isinstance(warp, nodes.ConditionalWarp):
            if _is_flow(warp):
                pending_break = None

            continue

        target = _get_target(warp)

        if target in blocks_set:
            continue

        assert target in ends, "GOTO statements are not supported"

        if pending_break is None:
            assert len(breaks_stack) > 0

            top_break = breaks_stack[-1]

            _set_target(warp, top_break[1])

            if top_break[0] == BREAK_ONE_USE:
                pending_break = breaks_stack.pop()

                warps_out = []
            else:
                warps_out.append(block)
        else:
            _set_target(warp, pending_break[1])
            warps_out.append(block)

        if len(block.contents) > 0:
            pending_break = None

    while len(breaks_stack) > 0 and breaks_stack[-1][0] == BREAK_INFINITE:
        breaks_stack.pop()

    # And pray for the best...
    while len(warps_out) > 0 and len(breaks_stack) > 0:
        _set_target(warps_out.pop().warp, breaks_stack.pop()[1])


#
# We don't need any complex checks here.
#
# Just search for any negative jump - that's a loop and what it's jumping to is
# a loop start.
#
def _find_all_loops(blocks, repeat_until):
    # Duplicates are NOT possible
    loops = []

    # If two points jump back to the same start, they must (if you know of any
    #  exceptions to this, please let me know) be the same loop, and all but the
    #  last jump are LuaJIT-generated 'continue' statements. These are almost
    #  always conditional jumps, but there is one case I know of which bucks this:
    #
    # while a do
    #  if b then
    #   ...
    #  elseif c
    #   ...
    #  end
    # end
    #
    # Without anything after the if/else statement, the compiler will place an unconditional
    #  jump from the end of the true block back to the start of the loop
    # This keeps track of the loops starting at each potential index, and if
    #  we find a jump to this point, check it and if so remove that loop.
    #
    # This is also not removed by _cleanup_breaks_and_if_ends, for some reason. However it may
    #  end up being possible to remove that pass altogether, and doing it here is simpler.
    starts = dict()

    i = 0

    while i < len(blocks):
        block = blocks[i]
        warp = block.warp

        if isinstance(warp, nodes.UnconditionalWarp):
            if warp.type == nodes.UnconditionalWarp.T_FLOW:
                i += 1
                continue

            start = warp.target
            if start.index <= block.index:
                assert not repeat_until
                assert i < len(blocks) - 1

                if start in starts:
                    pass
                    loops.remove(starts[start])

                loops.append((start, blocks[i + 1]))
                starts[start] = loops[-1]

        # The inline continues mentioned above shouldn't be an issue here, since they
        #  will all be removed during the first pass, and point forwards to their new
        #  EndWarp-containing nodes
        elif repeat_until and isinstance(warp, nodes.ConditionalWarp):
            if warp.false_target.index > block.index:
                i += 1
                continue

            start = warp.false_target
            first = block
            end = block
            last_i = i

            # Find the end of the expression
            while i < len(blocks):
                block = blocks[i]
                warp = block.warp

                if block != first and len(block.contents) != 0:
                    break

                if isinstance(warp, nodes.EndWarp):
                    break

                # Go up to a first negative jump of an
                # another loop

                target = _get_target(warp)
                if target.index < block.index:
                    if target == start:
                        start = target
                        end = block
                        last_i = i
                    else:
                        break

                i += 1

            # And then rollback to the last known negative jump
            # of our loop
            i = last_i

            # There always should be at least one return block
            end_index = blocks.index(end)
            end = blocks[end_index + 1]

            loops.append((start, end))

        i += 1

    # Reverse the order so inner "while" loops are processed before
    # outer loops
    return list(reversed(sorted(loops, key=lambda x: x[0].index)))


def _get_previous_block(block, blocks):
    block_index = blocks.index(block)

    assert block_index > 0

    return blocks[block_index - 1]


# Remove any unnecessary empty blocks (ie, those which are only flowed into once), and
#  merge any two blocks where the first flows into the second, and only the first warps to
#  the second.
def _cleanup_ast(blocks):
    next_i = 0
    while next_i < len(blocks):
        i = next_i
        next_i += 1
        block = blocks[i]

        # Skip the first block, don't want to touch it for now
        if i == 0:
            continue

        targets = _find_warps_to(blocks, block)

        assert targets

        if len(targets) != 1:
            continue

        src = targets[0]
        warp = src.warp

        if not isinstance(warp, nodes.UnconditionalWarp):
            continue

        if warp.type != nodes.UnconditionalWarp.T_FLOW:
            continue

        assert blocks.index(src) == i - 1

        # Move the to-be-deleted block's contents over
        src.contents += block.contents
        src.warp = block.warp
        src.last_address = block.last_address

        blocks.remove(block)

        # Because we're deleting this block, we need to stay at the
        #  same index since the list moved back
        next_i = i

    # Now that everything is nicely packed together, the code to eliminate temporary variables that
    #  are used in the input part of a for..in loop should be able to get everything.
    slotworks.eliminate_temporary(blocks[0], False)

    return blocks


def _find_warps_to(blocks, target):
    sources = []

    for block in blocks:
        warp = block.warp

        if isinstance(warp, nodes.UnconditionalWarp):
            if warp.target == target:
                sources.append(block)
        elif isinstance(warp, nodes.ConditionalWarp):
            if warp.false_target == target or warp.true_target == target:
                sources.append(block)
        elif isinstance(warp, nodes.EndWarp):
            pass
        else:
            if warp.way_out == target or warp.body == target:
                sources.append(block)

    return sources
