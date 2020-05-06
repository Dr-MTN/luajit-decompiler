-- This checks if slotworks is able to detect slot usage between different blocks in
-- a single function. If it's unable to, then it might inline the 1 into the print.
local myvar = 1
print(myvar)

if gbl then
	inblock(myvar)
end
