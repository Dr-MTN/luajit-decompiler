# Slot finder

This was developed against the issue [#32](https://gitlab.com/znixian/luajit-decompiler/-/issues/32),
which contains some more information about this.

The slot function traverses the AST early on in the decompilation process, tagging
slots that refer to the same variable.

*Note on terminology*: I'm using 'VM Slot' to refer to a given slot number (eg, `slot1`) which does
not map to a single SlotInfo.

## Problem

Before slotworks can start cleaning up the AST by eliminating redundant slots, it
first has to know which slots are related; `slot0` in two different parts of the
same function may very well refer to completely unrelated variables.

The old slot discovery system mostly (DorentuZ made some changes to this I'm (ZNix)
not completely familiar with) works as follows:

Go through each block and look for variable assignments. The code after the assignment
but before the next assignment to the same slot is treated as using that slot, and
that is fed into the slotworks cleanup system.

However, this has some major problems. Take the following Lua (the
`slot_block_gathering` test case):

```lua
local i = 1
print(i)

if gbl then
    print(i)
end
```

Gets split into (for the purposes of this document) two blocks: one for the start
of the function, and one for the contents of the if block. Since slot discovery
functions within it's own block, it can't find that `i` was used inside the `if` block.

Thus, it decompiles to:

```lua
print(1)

if gbl then
    print(slot)
end
```

## Identification

The slotfinder comprises of two stages run for each function early on, before any
unwarping has occurred.

The first of these identifies for each function, which:

* Slots are **inputs** to the block; these slots are used before they are set
within the block, and thus are reliant on the values left there by the previous
block.
* Slots which are **outputs** from the block; these are slots that are set inside
the block and not overwritten before the block ends.
* The **internals**: these are slots which are set in the block, but later overwritten
inside the same block. Note these are not wrapped, unlike the other two - see below.

Note that the above doesn't refer to numeric/VM slots (eg, `slot0`) as such; instead, they
refer to wrapped `SlotInfo`s (which contain the assignments and references to that
slot). The same VM slots can be used in each of the above roles, and what's output is
the use of that slot as a variable.

Each `SlotInfo` is later assigned an ID; this isn't actually stored in the SlotInfo, but
is stored in `Identifier.id` for each identifier referencing that slot (including those
in the destinations of assignments). This can be expressed as `slot#id`, so `1#1002` would
refer to VM slot 1 in the third set of slots (currently, they are numbered from 1000 to
make identification easier).

For example, in the following block (assuming `i` is in VM slot 1):

```lua
print(slot) -- refers to 1#1000 - input
slot = 2    -- 1#1001 - internal
print(slot) -- 1#1001 - internal
slot = 3    -- 1#1002 - internal
print(slot) -- 1#1002 - internal
slot = 4    -- 1#1003 - output
print(slot) -- 1#1003 - output
```

So in the above, there is only one VM slot, but it's used in four different `SlotInfo`s.

## Flowing

After the slots are analysed for each block, the inputs and outputs are linked together.

If, for example, a block outputs `slot0#1001` and the next block inputs the same slot, then
we would like to link them together (so there is one `SlotInfo` object that references both
of them). This is called *merging*.

Basically, the process of flowing is as follows: keep track of which blocks are marked as 'dirty'
and start by inserting all blocks to that set.

Then go through each dirty block, and check it's inputs. Make sure each `input` is linked
to the `output` of *every block that warps to it*. If any given block warping to it outputs
that VM slot, link the two `SlotInfo`s (the one in the input table of the current block,
and in the output table of the predecessor block) together.

If a given predecessor block does *not* contain the given `SlotInfo`, then insert that slot
to both it's `input` and `output` table and mark it as dirty. That block will then chase down
the input to it's source.

## Finalisation

Since the `SlotInfo`s are discarded (since they reference each `Identifier`, and many of those
will be eliminated later on, so it would be quite hard to keep them), we instead save a number
representing each `SlotInfo` into the `Identifier`s. These can later be scanned to easily and
accurately recover what references are left to each slot.

For each `SlotInfo`, the slot's references have their `id`s set.

Finally, the metadata (stored in `_BlockMeta` instances referenced by each block) is removed
from each `Block` since it's no longer needed.

## SlotInfo wrappers

The input and exports (but not internals) for each block are not directly stored
as `SlotInfo`s, since it would be unnecessarily complicated merging them, since all
the blocks referencing them would have to be updated.

Instead, these reference `_SlotNet` objects, which internally wrap another object which
wraps the `SlotInfo`. This internal object has (weak) references to the `_SlotNet`
instances, so two `_SlotNet`s can be merged without requiring any interaction with
the blocks.
