import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse
import ljd.lua.writer as writer

# Contains our useful colour class, though ideally we wouldn't
# be importing from the test package.
from test.utils import Colour, sgr

import io
from typing import List, Dict, Optional, Set
from dataclasses import dataclass


# Represents a warp to be shown in the gutter.
@dataclass()
class _GutterWarp:
    src: nodes.Block
    dst: nodes.Block
    colour: Colour

    # The position in the gutter (0=right, increasing going further left)
    pos: Optional[int] = None

    # The lines each block takes up, set later on
    block_lines: Optional = None

    # Is this warp part of a loop, jumping back to the start?
    # These are the only warps that jump backwards (afaik)
    def is_loop_warp(self):
        return self.block_lines[self.src][0] > self.block_lines[self.dst][0]

    # The line on which the warp starts
    def src_line(self):
        # Since we always start at the end of the block, -1 to get the last line
        # of code rather than part of the box
        return self.block_lines[self.src][1] - 1

    # Get the line we jump to
    def dst_line(self):
        # The mutator shuffles all the loop warps around, so the loop warp is in
        # the block directly before the start of the loop, and makes the last
        # block (that actually had the loop warp) jump to it, despite the fact
        # it's only supposed to be called once.
        # Thus to make it less confusing, make loop warps point at the last line
        # of the block which describes the loop parameters
        lines = self.block_lines[self.dst]
        return lines[1] - 1 if self.is_loop_warp() else lines[0] + 1

    def get_jump_lines(self) -> (int, int):
        # Since we don't know that the jump will be forwards, take all the line numbers
        # involved and sort them.
        return sorted([self.src_line(), self.dst_line()])

    def get_jump_lines_range(self):
        # Add one to make it inclusive
        lines = self.get_jump_lines()
        return range(lines[0], lines[1] + 1)


def print_graph(ast: nodes.FunctionDefinition):
    # The connectors between the nodes
    gutter: List[_GutterWarp] = []

    # The range of lines occupied by each block
    block_lines: Dict[nodes.Block, (int, int)] = dict()

    # Somewhere to store the main output, and we'll add the gutter later
    main_text = io.StringIO()

    for i, block in enumerate(ast.statements.contents):
        start_line = main_text.getvalue().count("\n")

        assert isinstance(block, nodes.Block)

        # For the block's warp, build it's gutter items and the bit of text
        # describing the jump that gets put on the end of the block's contents
        targets, jump_note = _warp_targets(block)

        # Draw the actual block contents and it's Unicode box characters
        _draw_block(block, main_text, jump_note)

        # Store the line numbers the block takes up
        end_line = main_text.getvalue().count("\n") - 1  # note this is on the last line, not past it
        block_lines[block] = (start_line, end_line)

        # Find what the next block is, if any
        next_block: Optional[nodes.Block]
        if i == len(ast.statements.contents) - 1:
            next_block = None
        else:
            next_block = ast.statements.contents[i + 1]

        # And if any of the warps point to the next block, draw it
        by_dest = dict([(jmp.dst, jmp) for jmp in targets])
        if next_block in by_dest:
            jmp = by_dest[next_block]
            main_text.write(" %s↓%s\n" % (sgr(jmp.colour.fg()), sgr("")))
            # Remove it so it doesn't also get added to the gutter
            del by_dest[next_block]

        # And since we deleted the next-block-warp from the dict, turn that back into items
        gutter += by_dest.values()

    # Set the block_lines for all the gutters, which is used for all the line
    # number calculations.
    for jump in gutter:
        jump.block_lines = block_lines

    # Since we're counting newlines without the addition it would have been the line number
    # of the last line, hence the +1.
    total_lines = main_text.getvalue().count("\n") + 1

    def gutter_length_finder(item: _GutterWarp) -> int:
        points = item.get_jump_lines()
        return points[1] - points[0]

    # Store what positions on each line of the gutter are already taken
    gutter_lines_blocked: Dict[int, Set[int]] = dict()

    # In order of shortest to longest, go through each jump
    # This is so short, local jumps get preferential access to the right-most slots, rather
    # than some giant long jump consuming it.
    # Those giant jumps will get put on the left-most side of the gutter, where
    # they're easiest to ignore.
    for jump in sorted(gutter, key=gutter_length_finder):
        # Build a set of all the positions, across all the relevant lines, that
        # already have a jump inside them
        occupied_positions = set()
        for line in jump.get_jump_lines_range():
            if line in gutter_lines_blocked:
                occupied_positions.update(gutter_lines_blocked[line])

        # Then find the lowest index (right-most slot) that's not already taken
        pos = 0
        while pos in occupied_positions:
            pos += 1

        jump.pos = pos

        # And mark those lines as blocked again
        for line in jump.get_jump_lines_range():
            gutter_lines_blocked.setdefault(line, set()).add(pos)

    # Set up the gutter area - a list of each line, with each line being a list of strings for the columns
    gutter_width = max([j.pos for j in gutter]) + 1  # +1 since these are 0-based indices
    gutter_area = []
    for i in range(0, total_lines):
        gutter_area.append([" "] * gutter_width)

    # Fill in the gutter text
    for jump in gutter:
        dir_idx = 1 if jump.is_loop_warp() else 0
        lines = jump.get_jump_lines()
        for line in range(lines[0], lines[1] + 1):
            if line == lines[0]:
                char = "┌↱"[dir_idx]
            elif line == lines[1]:
                char = "↳└"[dir_idx]
            else:
                char = "│"
            gutter_area[line][jump.pos] = sgr(jump.colour.fg()) + char + sgr("")

    # Finally zip together the gutter and main area, and draw it
    for gutter_line, main_line in zip(gutter_area, main_text.getvalue().split("\n")):
        print("".join(reversed(gutter_line)) + main_line)


# Take an AST node, and convert it to a string
def _node_to_str(node) -> str:
    # Use the private methods directly, since the main write method requires a FunctionDefinition
    visitor = writer.Visitor()
    traverse.traverse(visitor, node)

    sio = io.StringIO()
    # noinspection PyProtectedMember
    writer._process_queue(sio, visitor.print_queue, None)
    text = sio.getvalue()
    sio.close()
    return text.strip()


def _draw_block(block: nodes.Block, fd: io.StringIO, jump_note: str):
    assert isinstance(block, nodes.Block)

    sl = nodes.StatementsList()
    sl.contents = block.contents
    text = _node_to_str(sl)

    # The jump node should be spaced out by one line. If it's empty, this
    # just gets trimmed off again so we don't end up with redundant whitespace
    text += "\n\n" + jump_note
    text = text.strip()

    title = "Block %d" % block.index
    _draw_rect(title, text, fd)


# Draw a bit of text - encased in a rectangle of Unicode block drawing chars - to
# the given writer.
def _draw_rect(title: str, contents: str, fd: io.StringIO):
    lines = contents.split("\n")
    width = max([len(s) for s in lines])
    min_header_len = 4 + len(title)
    width = max(min_header_len, width)
    fd.write("╔═╡%s╞%s╗\n" % (title, "═" * (width - 3 - len(title))))
    for line in lines:
        fd.write("║%s║\n" % line.ljust(width))
    fd.write("╚%s╝\n" % ("═" * width))


# Take a given block, and return all the warps out of it, along with a note
# that should go in the block describing the jump
def _warp_targets(block: nodes.Block) -> (List[_GutterWarp], str):
    warp = block.warp

    def to(tgt, colour):
        return _GutterWarp(block, tgt, colour)

    def loop_warp():
        return [to(warp.body, Colour.BLUE), to(warp.way_out, Colour.YELLOW)]

    if isinstance(warp, nodes.UnconditionalWarp):
        return [to(warp.target, Colour.BLUE)], ""
    elif isinstance(warp, nodes.ConditionalWarp):
        text = "IfJmp(%s)" % _node_to_str(warp.condition)
        return [to(warp.true_target, Colour.GREEN), to(warp.false_target, Colour.RED)], text
    elif isinstance(warp, nodes.NumericLoopWarp):
        text = "For %s = %s" % (_node_to_str(warp.index), _node_to_str(warp.controls))
        return loop_warp(), text
    elif isinstance(warp, nodes.IteratorWarp):
        text = "For %s in %s" % (_node_to_str(warp.variables), _node_to_str(warp.controls))
        return loop_warp(), text
    else:
        assert isinstance(warp, nodes.EndWarp)
        return [], ""
