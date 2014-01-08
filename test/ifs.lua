--[[

--]]

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
