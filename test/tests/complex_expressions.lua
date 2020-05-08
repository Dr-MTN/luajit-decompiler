-- Have these little 'guards' at the top and bottom to generate a few blocks, to avoid the
-- possibility jumping to the first block and defeating some of the slotfinder assertions
-- involving linking inputs and outputs.
if gbl then
	f()
end

for i=1,(a and b) do
	func_in_body()
end

between()

for i=1,(a and b or c or d and e) do
	func_in_body()
end

if gbl then
	f()
end
