-- These make sure the decompiler doesn't eliminate a slot when that
-- would produce invalid (compile error) output.
local myf1 = nil
myf1()

local myf2 = true
myf2()

local myf3 = 123
myf3()

local myf4 = ""
myf4()

local tbl1 = nil
if tbl1.a then f() end

local tbl2 = true
if tbl2.a then f() end

local tbl3 = 123
if tbl3.a then f() end

-- Note that strings as tables are allowed, so this shouldn't be split
if ("").a then f() end
