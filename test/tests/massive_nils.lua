-- The following turns into the following assignment when decompiled:
-- slot0, slot1 = nil
-- ... which then (with the bug unpatched) becomes a massive ref in slotworks, and breaks everything
local some_local, important_padding

-- Note that assigning anything else doesn't exhibit this problem. This is probably due to the KNIL instruction.
-- local some_local, important_padding = false, false

my_gbl   = some_local
my_gbl_2 = some_local
