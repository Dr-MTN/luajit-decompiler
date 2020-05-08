local l = 123

pre()

local sub = function(x)
	l = x
end
sub(123)

l_should_be_123()

function sub_global(x)
	l = x
end
sub_global(321)

l_should_be_321()
