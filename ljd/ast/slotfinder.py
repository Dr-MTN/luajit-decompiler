# See doc/SlotFinder.md for context

from typing import List, Optional, Dict, Set
import weakref

import ljd.ast.traverse as traverse
import ljd.ast.nodes as nodes
from ljd.ast.slotworks import SlotInfo, SlotReference


# Find and link up all the slots for a given function. This should be done before any warping
# is performed.
# If a FunctionDefinition is found inside the AST, process will be called a second time from _InputOutputBuilder
def process(ast: nodes.FunctionDefinition):
    traverse.traverse(_SlotIdentifier(), ast)
    _flow_function(ast.statements.contents)
    _finalise(ast.statements.contents)


def _flow_function(blocks: List[nodes.Block]):
    # Setup the flow_ins, to trace back how we could get to a given point
    for blk in blocks:
        for tgt in _BlockMeta.get(blk).flow_out:
            _BlockMeta.get(tgt).flow_in.append(blk)

    # See the SlotFinder doc for an explanation of all this. TL;DR we link up
    # each input with the outputs of all blocks leading to it, and if any of
    # those blocks don't output it we propagate to the blocks leading to that
    # block, and so on.
    dirty: Set[nodes.Block] = set(blocks)
    while len(dirty) > 0:
        old_dirty = dirty
        dirty = set()
        for block in old_dirty:
            _flow_block(block, lambda b: dirty.add(b))


# Finalisation: Collect all the slots and assign them IDs
def _finalise(blocks: List[nodes.Block]):
    # First build a set of all the SlotInfo instances, which should represent every slot in the function.

    # First build a set of all the SlotNets of the inputs and outputs
    slot_nets: Set[_SlotNet] = set()
    for blk in blocks:
        meta = _BlockMeta.get(blk)
        slot_nets |= set(meta.inputs.values())
        slot_nets |= set(meta.outputs.values())

    # Then convert it to the slot infos and add in the internals, which is our complete list
    slots: List[SlotInfo] = [n.get() for n in slot_nets]
    for blk in blocks:
        slots += _BlockMeta.get(blk).internals

    # Move the slot numbers to each Identifier, since that's the only thing that stays around
    # after cleanup, and also isn't broken by Identifiers being removed by Slotworks.
    for slot in slots:
        # Build a list of all the identifiers relating to this SlotInfo.
        idents = [r.identifier for r in slot.references]

        # And finally write the IDs out to the references
        for ref in idents:
            ref.id = slot.slot_id

    # Clean up
    for blk in blocks:
        delattr(blk, '_block_slot_meta')


# For a given function, link up it's inputs
def _flow_block(block: nodes.Block, mark_dirty):
    meta = _BlockMeta.get(block)
    for slot_num, slot in meta.inputs.items():
        for src in meta.flow_in:
            src_meta = _BlockMeta.get(src)
            if slot_num in src_meta.outputs:
                slot.merge(src_meta.outputs[slot_num])
            else:
                src_meta.outputs[slot_num] = slot
                src_meta.inputs[slot_num] = slot
                mark_dirty(src)


# (see the SlotInfo Wrappers section in the markdown file)
# SlotNet is a wrapper around a SlotInfo. It's required because blocks input and output slots that
# need to be linked together. If we used raw SlotInfo objects, it'd require some slightly messy code
# to go through and update all of them.
class _SlotNet:
    class _Ctx:
        # Store the slots as weak references, otherwise we'd have cyclic references that
        # could keep this all alive.
        refs: List
        slot: SlotInfo

        def __init__(self, slot: SlotInfo):
            self.slot = slot
            self.refs = []

        def add(self, net: '_SlotNet'):
            self.refs.append(weakref.ref(net))

        # noinspection PyProtectedMember
        def merge(self, other: '_SlotNet._Ctx'):
            assert self.slot.function == other.slot.function
            self.slot.references += other.slot.references
            self.slot.assignments += other.slot.assignments
            self.refs += other.refs

    _ctx: _Ctx

    def __init__(self, slot):
        self._ctx = self._Ctx(slot)
        self._ctx.add(self)

    def get(self) -> SlotInfo:
        return self._ctx.slot

    def slot(self) -> int:
        return self.get().slot

    def merge(self, other: '_SlotNet'):
        assert other.slot() == self.slot()

        if other._ctx == self._ctx:
            return

        # Merge the contexts
        self._ctx.merge(other._ctx)

        # Migrate all the SlotNets to pointing to the same context
        for ref in other._ctx.refs:
            net: '_SlotNet' = ref()
            if not net:
                continue
            net._ctx = self._ctx
            self._ctx.refs.append(ref)

        assert other._ctx == self._ctx

    def __eq__(self, o):
        return isinstance(o, _SlotNet) and o._ctx == self._ctx

    def __hash__(self):
        return hash(self._ctx)


# A mapping between the VM slot numbers and their associated SlotInfo, wrapped by SlotNet
# Used quite a bit, hence the alias
_SlotDict = Dict[int, _SlotNet]


# Stores all the metadata about a single block, hence we don't use lots of fields on that
# block, and also conveniently get type inference for PyCharm's autocomplete.
class _BlockMeta:
    inputs: _SlotDict
    outputs: _SlotDict
    internals: List[SlotInfo]

    flow_in: List[nodes.Block]
    flow_out: List[nodes.Block]

    @staticmethod
    def get(block: nodes.Block) -> '_BlockMeta':
        # noinspection PyUnresolvedReferences,PyProtectedMember
        return block._block_slot_meta


# A visitor that scans through a the root function of the AST (calling process again to handle
# any nested functions) which identifies:
# The input, output and internal slots for each block
# The warps between blocks
class _SlotIdentifier(traverse.Visitor):
    _next_slot_id: int = 1000
    _path: List
    _func: nodes.FunctionDefinition = None

    _skip = False
    _block: Optional[nodes.Block] = None

    _current: _SlotDict
    _inputs: _SlotDict
    _internals: List[SlotInfo]

    # Used to track which VM slots we've already written to in this block. Something being in
    # current may mean it's already been written to, but it's also set when inputting something.
    # This distinction is important when adding something to the internals, since we have to be
    # careful not to put something in the inputs and the internals.
    _written: Set[int]

    def __init__(self):
        super().__init__()
        self._path = []

    # Create a new SlotInfo (and an associated SlotNet) for the given VM slot number
    def _new_slot(self, vm_slot_id) -> (SlotInfo, _SlotNet):
        info = SlotInfo(self._next_slot_id)
        info.function = self._func
        info.slot = vm_slot_id
        self._next_slot_id += 1
        return info, _SlotNet(info)

    # Called when a slot is assigned to, and shuffles around the output table and internals list appropriately
    def _slot_set(self, assign: nodes.Assignment, slot: nodes.Identifier):
        assert isinstance(slot, nodes.Identifier)

        # If we've already written to this slot, the previous value can't escape to later blocks.
        # Note it down so we can number it later.
        if slot.slot in self._written:
            self._internals.append(self._current[slot.slot].get())

        info, net = self._new_slot(slot.slot)
        info.assignment = assign
        info.assignments = [assign]
        self._current[slot.slot] = net
        self._written.add(slot.slot)

    # Called to mark that a given VM slot number has been read. Returns the SlotInfo representing that VM slot.
    def _slot_get(self, slot: nodes.Identifier) -> SlotInfo:
        assert isinstance(slot, nodes.Identifier)

        num = slot.slot
        net = self._current.get(num)
        if not net:
            info, net = self._new_slot(slot.slot)
            self._current[num] = net
            self._inputs[num] = net

        return net.get()

    def visit_assignment(self, node):
        self._visit(node.expressions)
        self._skip = True

        for slot in node.destinations.contents:
            self._slot_set(node, slot)

            # Since we've sets the skip flag, the identifiers won't be visited. Make sure we visit
            # each identifier to add a reference to it *after* we've set the slot, so this is a write
            # against the new SlotInfo and not the old one.
            self.visit_identifier(node)

    def leave_assignment(self, node):
        self._skip = False

    def visit_identifier(self, node: nodes.Identifier):
        # TODO handle locals, upvalues and builtins properly
        if node.type != nodes.Identifier.T_SLOT:
            return

        assert node.slot != -1

        info = self._slot_get(node)

        ref = SlotReference()
        ref.identifier = node
        ref.path = self._path[:]
        info.references.append(ref)

    def visit_block(self, node):
        self._current = dict()
        self._inputs = dict()
        self._internals = []
        self._written = set()
        self._block = node

    def leave_block(self, node):
        meta = _BlockMeta()
        meta.inputs = self._inputs
        meta.outputs = self._current
        meta.internals = self._internals

        # Take note of the blocks that could come after this block. Used to track back the sources of slots.
        warp = node.warp
        if isinstance(warp, nodes.ConditionalWarp):
            refs = [warp.true_target, warp.false_target]
        elif isinstance(warp, nodes.UnconditionalWarp):
            refs = [warp.target]
        elif isinstance(warp, nodes.NumericLoopWarp):
            refs = [warp.way_out]
        elif isinstance(warp, nodes.IteratorWarp):
            refs = [warp.way_out]
        else:
            assert isinstance(warp, nodes.EndWarp)
            refs = []

        meta.flow_in = []
        meta.flow_out = refs

        node._block_slot_meta = meta
        self._block = None

    def _visit_node(self, handler, node):
        self._path.append(node)
        traverse.Visitor._visit_node(self, handler, node)

    def _leave_node(self, handler, node):
        self._path.pop()
        traverse.Visitor._leave_node(self, handler, node)

    def _visit(self, node):
        # Skip is set while we visit the contents of a assignment. Since we're not interested in
        # those references (they're added manually to get the order correct), we skip them.
        if self._skip:
            return

        # In order to avoid storing a state stack between the different functions, recursively call
        # into process to repeat the whole thing for any nested functions.
        if isinstance(node, nodes.FunctionDefinition):
            if self._func is not None:
                process(node)
                return
            else:
                self._func = node

        traverse.Visitor._visit(self, node)
