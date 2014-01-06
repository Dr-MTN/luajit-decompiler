import collections

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


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
# If there is no such reference or the slot is revealed to be a local variable,
# we will create a new assignment and insert it as a first instruction to the
# branching end block
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
			else:
				is_if_false = True
		else:
			is_if_false = False

		processed = False

		if is_if_false:
			end = warp.target
			assert len(end.contents) == 0
			assert isinstance(end.warp, nodes.UnconditionalWarp)

			end = end.warp.target
		else:
			assert isinstance(warp, nodes.ConditionalWarp)

			end = _find_branching_end(start)

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

		if is_if_false:
			_unwarp_if_false(start, end, body, current_topmost_end)
			processed = True
		elif _expression_requirements_fulfiled(body):
			_unwarp_logical_expression(start, end, body,
							current_topmost_end)
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
	pass


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
def _find_branching_end(start):
	warp = start.warp

	queue = collections.deque()

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
# The depth-first search for loops.
#
# We don't need a set or anything, because blocks are ordered and anything
# looping should jump backwards
#
# And it is impossible to have a branched loop, i.e. there is always an only
# "end" point (a jump back) to a "start" point
#
# As we don't care about contents, just return a starting and ending blocks for
# an each loop detected
#
def _find_all_loops(blocks):
	stack = collections.deque()

	first = blocks[0]

	stack.append(first)

	# Duplicates are possible
	loops = set()

	while len(stack) > 0:
		block = stack.pop()

		warp = block.warp

		if isinstance(warp, nodes.UnconditionalWarp):
			if warp.target.index < block.index:
				loops.add((warp.target, block))
			else:
				assert warp.target.index != block.index
				stack.append(warp.target)

			# A special case for an unconditional "break" or
			# if false'ed loops
			next_block = blocks[block.index + 1]
			if next_block.warpins_count == 0:
				stack.append(next_block)
		elif isinstance(warp, nodes.ConditionalWarp):
			if warp.true_target.index <= block.index:
				loops.add((warp.true_target, block))
			else:
				stack.append(warp.true_target)

			if warp.false_target.index <= block.index:
				loops.add((warp.false_target, block))
			else:
				stack.append(warp.false_target)
		elif isinstance(warp, (nodes.IteratorWarp, nodes.NumericLoopWarp)):
			stack.append(warp.body)
			stack.append(warp.way_out)

			# Jump back will be in the last body block
			# We can guess it from the index, but why bother?
			assert warp.body.index > block.index
			assert warp.way_out.index > block.index
		else:
			assert isinstance(warp, nodes.EndWarp)

	return sorted(list(loops), key=lambda x: x[0].index)
