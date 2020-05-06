-- Make sure that slots are declared 'local' at only the appropriate time, once we implement marking
-- slots as locals (without debug symbols).
local a = "hello"

if f() then
	a = "world"
end

print(a)
