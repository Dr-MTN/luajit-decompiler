-- Test for the 'standard' massive refs in slotworks - varargs and functions.
-- Nils are special, and handled in massive_nils.lua

local a, b = f()
gbl1 = a
gbl2 = a

local c, d = ...
gbl3 = c
gbl4 = c
