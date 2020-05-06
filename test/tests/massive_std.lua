-- Test for the 'standard' massive refs in slotworks - varargs and functions.
-- Nils are special, and handled in massive_nils.lua

-- Put print in a local to avoid cluttering the bytecode up with GGETs
local print = nil

local a, b = f()
print(a)
print(a)
print(b)

local c, d = ...
gbl3 = c
gbl4 = c
