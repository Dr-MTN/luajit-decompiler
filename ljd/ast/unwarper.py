import collections
import copy

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse

binop = nodes.BinaryOperator


# ##
# ## REMEMBER
# ##
# ## Block indices are unreliable while you are mangling them!
# ##
# ## P.S. Probably then should not be named indices... But they ARE used as
# ## indices during other phases
# ##


class _StatementsCollector(traverse.Visitor):
	def __init__(self):
		self.result = []

	def visit_statements_list(self, node):
		self.result.append(node)


def unwarp(node):
	_run_step(_unwarp_loops, node)
	_run_step(_unwarp_ifs, node)
	pass


def _run_step(step, node):
	for statements in _gather_statements_lists(node):
		statements.contents = step(statements.contents)

	# Fix block indices in case anything was moved
	for statements in _gather_statements_lists(node):
		for i, block in enumerate(statements.contents):
			block.index = i


def _gather_statements_lists(node):
	collector = _StatementsCollector()
	traverse.traverse(collector, node)
	return collector.result


#
# We are considering two adequate cases of logical expressions
# 1. A normal expression
#    (x < 300 and y > 200) or ((x < 100) and (y == 3)) or invalid_coords(x, y)
# 2. An ?: operator replacement
#    a = coords_valid and (x*y + 100) else -1
#
# And one less adequate case:
# 3. A weird compact if:
#    junk = everything_is_ok and print("Everything ok!") else crash_something()
#
# ... because Lua syntax disallow logical expressions as statements
#
# There is no way to always say exactly if the given logical construction is an
# expression or a statement. But there are a few requirements and signs to
# guess this more or less precisely.
#
# There is an additional problem with the second case if the variable is local,
# especially if it is unused afterwards.
#
# REQUIREMENTS:
# 1. All the blocks in the construction are either empty or contain a single
# 	assignment to the same undefined slot or local variable (of the same
# 	slot - an undefined slot may suddenly became a local variable due to
# 	weird luajit local variable markings)
#
# SIGNS:
# 1. [Exact] There are jumps across "normal" branches, i.e. from a "then"
# 	clause to an "else" cause on the same level. Jumps ouside of the
# 	topmost if doesn't count - that's ok even for normal statements.
# 2. [More or less] There are undefined slot assignments. May break without
# 	a debug information.
# 3. [More or less] Same as requirement 1 - there are empty blocks
# 	or blocks with single assignments to the same slot or local vairable.
# 	Some idiot may write the same thing by normal statements.
# 4. [More or less] All statements in blocks are on the same line. Will break
# 	without a debug information. Expression could be multiline.
#
# Generally we will check the requirement and the first sign.
#
# If the requirement is fulfilled we will consider this as an expression - at
# least it will compile.
# If the requirement is not fulfilled, but the first sign is - that's an error.
# If neither the requirement, nor the first sign are fulfilled - that's a
# statement.
#
# If the undefined slot will remain undefined we will traverse the first
# instruction of the branching end block - there should be a reference the slot
#
# In either case we just put a new assignment. There will be the second slot
# elimination phase after this phase
#
def _unwarp_ifs(blocks, top_end=None, topmost_end=None):
	boundaries = []

	start_index = 0

	while start_index < len(blocks) - 1:
		start = blocks[start_index]
		warp = start.warp

		if isinstance(warp, nodes.UnconditionalWarp):
			if warp.type == nodes.UnconditionalWarp.T_FLOW:
				start_index += 1
				continue

		processed = False

		end = _find_branching_end(start, blocks)

		try:
			end_index = blocks.index(end)
		except ValueError:
			assert end == topmost_end, 	\
				"GOTO statements are not supported"
			end_index = len(blocks)

		body = blocks[start_index + 1:end_index]

		if topmost_end is None:
			current_topmost_end = end
		else:
			current_topmost_end = topmost_end

		if _expression_requirements_fulfiled(body):
			_unwarp_logical_expression(start, end, body,
							current_topmost_end)
			processed = True
		else:
			_unwarp_if_statement(start, end, body,
							current_topmost_end)
			processed = True

		if processed:
			boundaries.append((start_index, end_index - 1))

			start.warp = nodes.UnconditionalWarp()
			start.warp.type = nodes.UnconditionalWarp.T_FLOW
			start.warp.target = end

		start_index = end_index

	return _remove_processed_blocks(blocks, boundaries)


def _unwarp_if_false(start, end, body, topmost_end):
	assert len(body[0].contents) == 0
	assert isinstance(body[0].warp, nodes.UnconditionalWarp)

	# That's some weirdness - luajit generate two JMPs with the first one
	# jumping at the second one, so we got two blocks in body here.
	body.pop(0)

	node = nodes.If()
	node.expression = nodes.Primitive()
	node.expression.type = nodes.Primitive.T_FALSE

	node.then_block.contents = _unwarp_ifs(body, body[-1], topmost_end)

	assert body[0].warpins_count == 0

	body[-1].warp = nodes.EndWarp()

	start.contents.append(node)


def _expression_requirements_fulfiled(body):
	slot = -1

	for block in body:
		if len(block.contents) == 0:
			continue

		if len(block.contents) > 1:
			return False

		assignment = block.contents[0]

		if not isinstance(assignment, nodes.Assignment):
			return False

		destinations = assignment.destinations.contents

		if len(destinations) > 1:
			return False

		dst = destinations[0]

		if not isinstance(dst, nodes.Identifier):
			return False

		if slot < 0:
			slot = dst.slot
		elif slot != dst.slot:
			return False

	return True


def _unwarp_logical_expression(start, end, body, topmost_end):
	slot = None

	# Find the last occurence of the slot - it could be a local variable at
	# the last occurance
	for block in reversed(body):
		if len(block.contents) != 1:
			continue

		slot = block.contents[0].destinations.contents[0]
		break

	assert slot is not None

	true, false, body = _get_terminators(body)

	parts = _unwarp_expression([start] + body, end, true, false)

	parts = _make_explicit_subexpressions(parts)
	expression = _assemble_expression(parts)

	dst = copy.deepcopy(slot)

	assignment = nodes.Assignment()
	assignment.destinations.contents.append(dst)
	assignment.expressions.contents.append(expression)

	start.contents.append(assignment)


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
# They we need to pack all other blocks into subexpressions. Subexpressions
# always end with a _terminal block_, i.e. the block which warp points to a
# terminator. Idea is that we can guess the operator which is only at the
# right of a terminal block, because we can check if the block's warp condition
# is inverted or not.
#
# If that's an "OR" clause then it will jump out of the current expression if
# the condition is true, so the condition is inverted and the false branch is
# pointing at the way out (at the TRUE terminator - because the result of that
# expression level will be true in that case). (because in the bytecode there
# is only one JMP, so in the "ConditionalWarp" the true branch is fake and
# always points to the next block =). So if the bytecode wants to jump if
# something is true, then it needs to invert the condition because normally
# it jumps only if the condition is false).
#
# Otherwise, if that's an "AND" clause then it will jump out of the current
# expression level if the condition is false, so the condition is not inverted
# and false branch points to the false.
#
# So, guessing from the terminal blocks we can understand which operators go
# at right of them. Everything in-between these block is considered a
# subexpression. And just because we don't know where exactly the subexpression
# ends we are using greedy approach and trying to pack into subexpression as
# much blocks as possible, including terminal blocks in they point to the same
# terminator and has same inversion status (that is - we are always using the
# rightmost block if there are consequitive similar terminal blocks, ignoring
# all the blocks at the left).
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

	terminators = set((true, false, end))

	subexpression_start = 0

	i = 0
	while i < len(body) - 1:
		block = body[i]
		warp = block.warp

		target = _get_target(warp)

		if target.index < terminator_index:
			i += 1
			continue

		assert target in terminators

		while i < len(body) - 2:
			next_block = body[i + 1]
			next_target = _get_target(next_block.warp)

			if next_target != target:
				break

			next_inverted = _is_inverted(next_block.warp, true, end)

			this_inverted = _is_inverted(warp, true, end)

			# Special hack for unary expressions (x, not x)...
			if next_inverted != this_inverted:
				break

			block = next_block
			warp = next_block.warp
			i += 1

		next_block = body[i + 1]
		subexpression = body[subexpression_start:i + 1]

		operator = _get_operator(block, true, end)

		subexpression = _compile_subexpression(subexpression, operator,
							block, next_block,
							true, end)

		parts.append(subexpression)
		parts.append(operator)

		i += 1
		subexpression_start = i

	if len(body) > 1:
		assert len(parts) > 0
		assert isinstance(parts[-1], int)

	last = body[-1]

	if isinstance(last.warp, nodes.ConditionalWarp):
		if _is_inverted(last.warp, true, end):
			last = _invert(last.warp.condition)
		else:
			last = last.warp.condition
	else:
		assert isinstance(last.warp, nodes.UnconditionalWarp)

		last = _get_last_assignment_source(last)

	parts.append(last)

	return parts


def _get_target(warp):
	if isinstance(warp, nodes.ConditionalWarp):
		return warp.false_target
	else:
		assert isinstance(warp, nodes.UnconditionalWarp)
		return warp.target


def _get_operator(block, true, end):
	if isinstance(block.warp, nodes.UnconditionalWarp):
		src = _get_last_assignment_source(block)

		if isinstance(src, nodes.Constant):
			is_true = src.value != 0
		else:
			assert isinstance(src, nodes.Primitive)

			is_true = src.type == nodes.Primitive.T_TRUE

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
	assignment = block.contents[-1]
	assert isinstance(assignment, nodes.Assignment)
	return assignment.expressions.contents[0]


def _get_and_remove_last_assignment_source(block):
	assignment = block.contents.pop()
	assert isinstance(assignment, nodes.Assignment)
	return assignment.expressions.contents[0]


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
		return False

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
	src = assignment.expressions.contents[0]

	if not isinstance(src, nodes.Primitive) or src.type != src.T_TRUE:
		return None, None, body

	prev = body[-2]

	if len(prev.contents) != 1:
		return None, None, body

	src = prev.contents[0].expressions.contents[0]

	if not isinstance(src, nodes.Primitive) or src.type != src.T_FALSE:
		return None, None, body

	return last, prev, body[:-2]


def _assemble_expression(parts):
	if not isinstance(parts, list):
		return parts

	node = nodes.BinaryOperator()
	node.left = _assemble_expression(parts[-3])
	node.type = parts[-2]
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
			if operator > last_operator:
				patched.append(parts[subexpression_start:i])
				subexpression_start = -1
		else:
			patched += [component, operator]

		i += 2

	if subexpression_start >= 0:
		patched.append(parts[subexpression_start:])
	else:
		patched.append(parts[-1])

	return patched


def _unwarp_if_statement(start, end, body, topmost_end):
	warp = start.warp

	node = nodes.If()
	node.expression = warp.condition

	# has an else branch
	if warp.false_target != end and warp.false_target != topmost_end:
		else_start = warp.false_target

		else_start_index = body.index(else_start)

		then_body = body[:else_start_index]

		then_warp_out = then_body[-1].warp

		assert isinstance(then_warp_out, nodes.UnconditionalWarp)
		assert then_warp_out.type == nodes.UnconditionalWarp.T_JUMP
		assert then_warp_out.target == end	\
			or then_warp_out.target == topmost_end

		else_body = body[else_start_index:]

		else_warp_out = else_body[-1].warp

		assert isinstance(else_warp_out, nodes.UnconditionalWarp)
		assert else_warp_out.target == end	\
			or else_warp_out.target == topmost_end

		then_blocks = _unwarp_ifs(then_body, then_body[-1], topmost_end)
		node.then_block.contents = then_blocks

		else_blocks = _unwarp_ifs(else_body, else_body[-1], topmost_end)
		node.else_block.contents = else_blocks

		then_blocks[-1].warp = nodes.EndWarp()
		else_blocks[-1].warp = nodes.EndWarp()
	else:
		then_blocks = _unwarp_ifs(body, body[-1], topmost_end)
		node.then_block.contents = then_blocks
		warp_out = body[-1].warp

		assert isinstance(warp_out, nodes.UnconditionalWarp)
		assert warp_out.target == end or warp_out == topmost_end

		then_blocks[-1].warp = nodes.EndWarp()

	start.contents.append(node)


#
# A modified breadth-first search for an if's "end"
#
# Idea is to keep the farmost block referenced as "end" and out of the
# breadth-first queue, so this branch won't be followed further. Eventually
# either some other branch will reference a block below the current end and
# will become the new end, or all other branches will reference same block.
#
# As we add a block into the queue only if it's index is less then the
# current end, queue will eventually depleed
#
def _find_branching_end(start, blocks):
	warp = start.warp

	queue = collections.deque()

	if not isinstance(start.warp, nodes.ConditionalWarp):
		index = blocks.index(warp.target)

		block = blocks[index - 1]
		warp = block.warp

		while isinstance(warp, nodes.UnconditionalWarp):
			if warp.type == nodes.UnconditionalWarp.T_FLOW:
				return warp.target

			block = warp.target
			warp = block.warp

		if isinstance(warp, nodes.EndWarp):
			return block

	if warp.false_target.index > warp.true_target.index:
		end = warp.false_target
		queue.append(warp.true_target)
	else:
		end = warp.true_target
		queue.append(warp.false_target)

	while len(queue) > 0:
		block = queue.popleft()

		warp = block.warp

		if isinstance(warp, nodes.ConditionalWarp):
			if warp.true_target.index > end.index:
				queue.append(end)
				end = warp.true_target
			elif warp.true_target.index < end.index:
				queue.append(warp.true_target)

			if warp.false_target.index > end.index:
				queue.append(end)
				end = warp.false_target
			elif warp.false_target.index < end.index:
				queue.append(warp.false_target)
		else:
			assert isinstance(warp, nodes.UnconditionalWarp)

			if warp.target.index > end.index:
				queue.append(end)
				end = warp.target
			elif warp.target.index < end.index:
				queue.append(warp.target)

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


def _unwarp_loops(blocks):
	loops = _find_all_loops(blocks)

	boundaries = []

	for start, end in loops:
		boundary = _unwarp_loop(start, end, blocks)
		boundaries.append(boundary)

	return _remove_processed_blocks(blocks, boundaries)


def _unwarp_loop(start, end, all_blocks):
	if start == end or isinstance(start.warp, nodes.UnconditionalWarp):
		if start != end:
			assert isinstance(end.warp, nodes.ConditionalWarp)

		assert end.warp.false_target == start

		body_blocks = all_blocks[start.index:end.index + 1]

		loop = nodes.RepeatUntil()
		loop.statements.contents = body_blocks
		loop.expression = end.warp.condition

		if start.index > 0:
			container = all_blocks[start.index - 1]
		else:
			container = all_blocks[end.index + 1]
	elif isinstance(start.warp, nodes.ConditionalWarp):
		assert isinstance(end.warp, nodes.UnconditionalWarp)
		assert end.warp.target == start

		body_blocks = all_blocks[start.index + 1:end.index + 1]

		loop = nodes.While()
		loop.statements.contents = body_blocks
		loop.expression = start.warp.condition

		container = start
	elif isinstance(start.warp, nodes.IteratorWarp):
		assert isinstance(end.warp, nodes.UnconditionalWarp)
		assert end.warp.target == start

		body_blocks = all_blocks[start.index + 1:end.index + 1]

		loop = nodes.IteratorFor()
		loop.statements.contents = body_blocks
		loop.identifiers = start.warp.variables
		loop.expressions = start.warp.controls

		container = start
	else:
		assert isinstance(start.warp, nodes.NumericLoopWarp)
		assert isinstance(end.warp, nodes.UnconditionalWarp)
		assert end.warp.target == start

		body_blocks = all_blocks[start.index + 1:end.index + 1]

		loop = nodes.NumericFor()
		loop.statements.contents = body_blocks
		loop.variable = start.warp.index
		loop.expressions = start.warp.controls

		container = start

	assert len(body_blocks) > 0

	container.contents.append(loop)
	container.warp = nodes.UnconditionalWarp()
	container.warp.type = nodes.UnconditionalWarp.T_FLOW

	# There is always a return statement
	next_block = all_blocks[end.index + 1]
	container.warp.target = next_block

	_unwarp_breaks(start, body_blocks, next_block)

	body_blocks[-1].warp = nodes.EndWarp()

	return body_blocks[0].index - 1, body_blocks[-1].index


def _unwarp_breaks(start, blocks, next_block):
	blocks_set = set([start] + blocks)

	for i, block in enumerate(blocks):
		warp = block.warp

		if not isinstance(warp, nodes.UnconditionalWarp):
			continue

		# Ignore ifs and other stuff inside the loop
		if warp.target in blocks_set:
			continue

		assert warp.target == next_block, 		\
			"GOTO statements are not supported"

		block.contents.append(nodes.Break())

		if i + 1 == len(blocks):
			block.warp = nodes.EndWarp()
		else:
			block.warp.type = nodes.UnconditionalWarp.T_FLOW
			block.warp.target = blocks[i + 1]


#
# Thanks to the patching phase we don't need any complex checks here.
#
# Just search for any negative jump - that's a loop and what it's jumping to is
# a loop start.
#
def _find_all_loops(blocks):
	# Duplicates are NOT possible
	loops = []

	for block in blocks:
		warp = block.warp

		if isinstance(warp, nodes.UnconditionalWarp):
			if warp.target.index <= block.index:
				loops.append((warp.target, block))
		elif isinstance(warp, nodes.ConditionalWarp):
			if warp.true_target.index <= block.index:
				loops.append((warp.true_target, block))

			if warp.false_target.index <= block.index:
				loops.append((warp.false_target, block))

	return sorted(loops, key=lambda x: x[0].index)
