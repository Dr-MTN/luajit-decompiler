if x < 100 then
	print ("then")
else
	print ("else")
end


if x < 100 and y < 100 then
	print ("semi-nested then")
else
	print ("else")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	end
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	end

	print ("Enclosure")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	else
		print ("Nested else")
	end

	print ("Enclosure")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	end

	print ("Enclosure")
else
	print ("Else")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	end
else
	print ("Else")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	else
		print ("Nested else")
	end
else
	print ("Else")
end

if x < 100 or z > 100 then
	if y < 100 or x > 100 then
		print ("Nested then")
	else
		print ("Nested else")
	end
else
	if y < 100 or x > 100 then
		print ("Nested else then")
	else
		print ("Nested else else")
	end
end

if x < 100 or y < 100 then
	print ("x or y with comparisons")
end

if x < 100 and y < 100 then
	print ("x and y with comparisons")
end

if x < 100 or y < 100 then
	print ("x or y with comparisons")
else
	print ("ELSE x or y with comparisons")
end

if x < 100 and y < 100 then
	print ("x and y with comparisons")
else
	print ("ELSE x and y with comparisons")
end

if (x < 100 and y < 100) or z < 100 then
	print ("(and) or with comparisons")
else
	print ("ELSE (and) or with comparisons")
end

if x < 300 and y < 300 then
	print ("True terminator!")

	if x < 300  and z < 300 then
		print("Nested if")
	end
else
	print ("False terminator!")

	if x < 300 and z < 300 then
		print("Enclosed nested if")
	end

	print ("Enclosure")
end

if x or y then
	print ("x or y")
end

if x and y then
	print ("x and y")
end

if x or y then
	print ("x or y")
else
	print ("ELSE x or y")
end

if x and y then
	print ("x and y")
else
	print ("ELSE x and y")
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	print ("True terminator!")
else
	print ("False terminator!")
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	print ("True terminator!")

	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end

		print ("Enclosed")
	else
		print ("False terminator!")
	end

	print ("Enclosed")
else
	print ("False terminator!")
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	print ("True terminator!")

	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end

		print ("Enclosed")
	else
		print ("False terminator!")
	end
else
	print ("False terminator!")
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	print ("True terminator!")

	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end
else
	print ("False terminator!")
end

if (y < 300 or z > 300) then
	print ("True terminator!")

	if (x < 300 and z < 300) then
		print ("True terminator!")

		if x < 300  or z < 300 then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end

	print ("Enclosed")
else
	print ("False terminator!")
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	print ("True terminator!")

	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end
else
	print ("False terminator!")

	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end
end

if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end
else
	if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
		print ("True terminator!")

		if (x < 300 and (y < 300 or z > 300)) or z < 300 and error() then
			print ("True terminator!")
		else
			print ("False terminator!")
		end
	else
		print ("False terminator!")
	end
end

local a = 0

if x % 2 == 0 then
	a = 1
end

local a = "test"
local b = "result"
if a == "test" then
	b = "test"
elseif a == "1234" then
	b = "1234"
elseif a == "asd" then
	b = "asd"
elseif a == "fadasd" then
	b = "fadasd"
else
	b = "Otherwise"
end

print (a, b)

local a = "test"
if a == "test" then
	b = "test"
	if  a == "1234" then
		b = "1234"

		if a == "asd" then
			a = "asd"

			if a == "fadasd" then
				b = "fadasd"
			end
		end
	end
end

if a == "test" then
	b = "test"
	if a == "test" then
		b = "test"
	elseif a == "1234" then
		b = "1234"
	elseif a == "asd" then
		b = "asd"
	elseif a == "fadasd" then
		b = "fadasd"
	else
		b = "Otherwise"
	end
elseif a == "1234" then
	b = "1234"
elseif a == "asd" then
	b = "asd"
elseif a == "fadasd" then
	b = "fadasd"
else
	b = "Otherwise"
end

print (a, b)
local slot1, slot2 = nil

if componentInfo.details ~= nil then
	layout = componentInfo.details.layout

	if layout == "table" then
		mainFrame = "tableFrame"
	else
		if layout == "header" then
			mainFrame = "headerFrame"
		else
			if layout == "long" then
				mainFrame = "fullFrame"
			else
				if layout == "short" then
					mainFrame = "topFrame"
				end
			end

		end
	end
end

print ("asd")
