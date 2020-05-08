-- Make sure the basics of arguments are working
function f(x)
	return x
end

-- Make sure they work with blocks properly
function f(x)
	if gbl then
		x = 123
	end
	return x
end
