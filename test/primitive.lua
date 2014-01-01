function assignment()
	function generator()
		return 1, 2, 3
	end

	a = 1
	b, c, d = nil
	e, f, g = 1, 2, 3
	local i, k, l = 3, 2, g + 1
	
	local m, n, o, p = 1, generator()

	print (a, b, c, d, e, f, g, i, k, l)
end

function vararg(...)
	a = ...
	c, d = ...
	t = {...}
	s = {1, 2, 3, ...}

	local f, g, h = ...

	t.x = ...

	assignment(...)

	if t.x == 3 then
		return a, t, s, ...
	else
		return a, t, s, ...
	end
end

function tables()
	function generator(x, y, z)
		return x, y, z
	end

	t = {
		[123.322] = 3,
		[3] = {
			"a", "b", "c"
		},
		generator("a", "b", "c"),
		generator("d", "e", "f")
	}

	t.var = 1
	t.str = "Nope"

	function t:foo(var)
		self.var = var;
		self.str = "!!!" .. var 
	end 

	t:foo(123)

	print(t)
end

function logical()
	x = 3

	print ("No then, only else")

	if x == 1 then
	else
		print ("Not one!")
	end

	print ("elseifs")

	if x == 3 then
		print("is three!")
	elseif x == 5 then
		print("is five!")
	elseif x == 8 then
		print("is eight!")
	else
		print("is something else!")
	end

	print ("ordinary if")

	if x == 6 then
		print("Is six!")
	else
		print("Whatever else!")
	end

	y = 4

	print ("normal logical expression")

	b = (x and y) or ((y > 3) and (((x/2) < 1) or (y > 100))) and (x ~= 2)

	print ("precalculated true expression")

	c = true or (x and y) or true

	print ("precalculated false expression")

	d = false and ((x and y) or true)

	print ("precalculated false expression with function")

	e = error() and false and ((x and y) or true)

	print ("precalculated? false expression with variable")

	local z = false

	f = z and ((x and y) or true)

	print ("precalculated false expression with nil")

	f = nil and ((x and y) or true)

	print(x, y, b, c, d, e, f)
end

function functions()
	function func1(x, y)
		function sub(z)
			return z
		end

		return x, y, sub
	end

	x, y, z = func1(1, 2)
	print(z(4))

	x = func1(1, 2)

	func1(1, 2)

	function func2(x)
		print (x)
	end

	function func3(x)
		return x*2
	end

	func2(func3(3))

	function func4(x, y, z)
		print (x, y, z)
	end

	func4(1, 2, func2(3))
end

function locals(x, y, ...)
	local a, b, c = ...

	function generator()
		return 1, 2, 3
	end

	local d, e, f  = generator()

	local g, h, i, k = 4, generator()

	local l, m, n = f, e
end


function loops()
	function iterate_over(table)
		function iterator(table, index)
			key, value = next(table, index)

			return key, value, 1, 2, 3
		end

		return iterator, table, nil
	end

	t = {1, 2, 3}

	print ("numeric for without step")

	for i=1, 100 do
		print(i)
	end

	print ("numeric for with step")

	for i=1, 100, 2 do
		print(i)
	end

	print ("iterator for")

	for key, value in pairs(t) do
		print(key, value)
	end

	print("iterator for with another iterator")

	local z = false
	for key, value in ipairs(t) do
		print(key, value)
	end

	print("iterator for with crazy custom iterator")

	for key, value, x, y, z in iterate_over(t) do
		print(key, value, x, y, z)
	end

	print("iterator for with dissected iterator")

	a, b, c = pairs(t)

	for key, value in a, b, c do
		print(key, value)
	end

	print ("while")

	x = 3

	while x > 0 do
		x = x - 1
	end
	
	print ("while with copy check")

	y = 0
	x = y

	while x do
		x = y
	end

	print ("repeat until")

	repeat
		x = x + 1
	until x > 5

	print ("repeat until with copy check")

	repeat
		x = y
	until not x

	print ("While with break")

	while x > 5 do
		break
	end

	print ("Repeat until with break")

	repeat
		break
	until x < 3

	print ("Numeric for with break")

	for i=0,1,2 do
		break
	end

	print ("Iterator for with break")

	for key,value in pairs(t) do
		break
	end

	print ("Loop with break and function inside")

	t = {}

	for i=0,100 do
		y = 3
		t[i] = function ()
			return i + y
		end

		if i == 5 then
			print ("then")
			break
		else
			print ("else")
		end
	end
end

function upvalues()
	test = 0

	function sub(x)
		test = test + 1
		test = 3
		test = "asd"
		test = 4.0
		return test + x
	end

	print(sub(3))
end


function subblock()
	x = 3

	do
		local a = 2

		print(a + x)
	end

	y = 4
end
