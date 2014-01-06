import copy

import ljd.bytecode.instructions as ins
from ljd.bytecode.helpers import get_jump_destination, set_jump_destination


def apply(instructions):
	step0 = instructions
	step1 = _swap_iterator_loop_boundaries(step0)
	step2 = _replace_forl_with_jump_to_init(step1)
	return step2


#
# Swap the the JMP instruction pointing to the ITERC/N with it's target
# (ITERC/N + the following ITERL)
# This is to make our lives easier when eliminating slots, so each slot-rich
# warp will be defined in the block with the slots defined.
#
# We have to keep both ITERC/N and ITERL instructions because we can put only
# so much information into a single instruction
#
def _swap_iterator_loop_boundaries(instructions):
	patched = []

	last_swap = 0

	for addr, instruction in enumerate(instructions):
		opcode = instruction.opcode

		if opcode != ins.JMP.opcode and opcode != ins.ISNEXT.opcode:
			continue

		destination = get_jump_destination(addr, instruction)

		target = instructions[destination]

		if target.opcode != ins.ITERC.opcode			\
				and target.opcode != ins.ITERN.opcode:
			continue

		# Append everything since the last swap
		patched += instructions[last_swap:addr]

		# Append a COPIES of the ITERC/ITERL instructions
		# from the target addr
		patched.append(copy.deepcopy(instructions[destination]))
		patched.append(copy.deepcopy(instructions[destination + 1]))

		# Append the in-middle code
		patched += instructions[addr + 1:destination]

		# Append a COPY of the JMP - we are going to patch the
		# destination and we don't want to touch the original
		# instructions
		patched.append(copy.deepcopy(instruction))

		# We've processed everything up to the last ITERL position
		last_swap = destination + 2

		# Now fix the jump destinations to make things look natural

		# Point the JMP to the first initialization instruction
		jmp = patched[destination + 1]
		assert jmp.opcode == instruction.opcode

		init_addr = _calculate_iterator_init_begin(addr, patched)
		set_jump_destination(destination + 1, jmp, init_addr)

		# Point the ITERL to a after-JMP location

		iterl = patched[addr + 1]
		assert iterl.opcode == ins.ITERL.opcode

		# Originally ITERL is looking at the first body instruction
		# So we just need to negate the jump (and move it a bit due
		# to relative nature of the value and ITERL being a second
		# instruction in the ITERC+ITERL pair)
		iterl.CD = -iterl.CD - 1
		iterl.description = iterl.description.replace("!=", "==")

	patched += instructions[last_swap:]

	return patched


#
# The numeric loop has all the instructions set properly, but we want the
# FORL instruction (the ending boundary of the numeric loop) to be a JMP at a
# control variables' initialization, not at the first body instruction.
#
# That makes no sense for the runtime, but who cares - that will simplify a
# task of control flow rebuild significantly
#
def _replace_forl_with_jump_to_init(instructions):
	# Copy all the contents (as references) in a single chunk to speed up
	# the process
	patched = instructions[:]

	# Loop over instructions as we will replace some of the loop contents.
	# We need to copy all the FORL instructions replacing the references
	for addr, instruction in enumerate(instructions):
		opcode = instruction.opcode

		if opcode < ins.FORL.opcode or opcode > ins.JFORL.opcode:
			continue

		destination = get_jump_destination(addr, instruction)

		fori_addr = destination - 1
		init_addr = _calculate_numeric_init_begin(fori_addr, patched)

		jmp = ins.JMP()
		# Set anything, we don't care about correctness of the
		# resulting bytecode. This is a "first free slot" operand, so
		# it has no use for us
		jmp.A = 666

		set_jump_destination(addr, jmp, init_addr)

		patched[addr] = jmp

	return patched


def _calculate_iterator_init_begin(iterc_addr, instructions):
	iterc = instructions[iterc_addr]
	assert iterc.opcode in (ins.ITERC.opcode, ins.ITERN.opcode)

	slots = set((iterc.A - 1, iterc.A - 2, iterc.A - 3))

	return _calculate_slots_init_address(iterc_addr, instructions, slots)


def _calculate_numeric_init_begin(fori_addr, instructions):
	fori = instructions[fori_addr]
	assert fori.opcode in (ins.FORI.opcode, ins.JFORI.opcode)

	slots = set((fori.A, fori.A + 1, fori.A + 2))

	return _calculate_slots_init_address(fori_addr, instructions, slots)


def _calculate_slots_init_address(addr, instructions, slots):
	while addr > 0 and len(slots) > 0:
		addr -= 1

		instruction = instructions[addr]
		opcode = instruction.opcode

		if opcode == ins.CALL.opcode or opcode == ins.CALLM.opcode:
			first_slot = instruction.A
			last_return = first_slot + instruction.B - 2

			last_argument = first_slot + instruction.CD

			if opcode != ins.CALLM.opcode:
				last_argument -= 1

			for slot in range(first_slot, last_return + 1):
				slots.remove(slot)

			# Including the function slot itself (instruction.A)
			for slot in range(first_slot, last_argument + 1):
				slots.add(slot)

			if opcode == ins.CALLM.opcode:
				slots.add(-1)
		elif instruction.A_type == ins.T_DST:
			slots.remove(instruction.A)

			if instruction.B_type == ins.T_VAR:
				slots.add(instruction.B)

			if instruction.CD_type == ins.T_VAR:
				slots.add(instruction.CD)

	return addr


