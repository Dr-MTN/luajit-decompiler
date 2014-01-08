print ("true or true")

b = true or true

print ("false and false")

b = false and false

print ("false and or")

b = false and (x or y)

print ("false and ((and) or)")

b = false and ((x and z) or y)

print ("precalculated true expression")

c = true or (x and y) or true

print ("precalculated false expression")

d = false and ((x and y) or true)

print ("precalculated false expression with function")

e = error() and false and ((x and y) or true)

print ("precalculated true expression with function")

e = error() and true and ((x and y) or true)

print ("precalculated? false expression with variable")

local z = false

f = z and ((x and y) or true)

print ("precalculated false expression with nil")

f = nil and ((x and y) or true)

print ("simple or expression")

b = x or y

print ("simple or not expression")

b = not x or y

print ("simple and expression")

b = x and y

print ("simple or expression with binary comparison")

b = (x < 100) or y

print ("simple and expression with binary comparison")

b = (x < 100) and y

print ("simple and expression with binary comparison and function call")

b = (x < 100) and print(y)

print ("simple and expression with double binary comparison")

b = (x < 100) and (y > 100)

print ("(and) or expression")

b = (x and y) or z

print ("(or) and expression")

b = (x or y) and z

print ("(and) and expression")

b = (x and y) and z

print ("(or) or expression")
b = (x or y) or z

print ("or (and) expression")

b = x or (y and x)
b = x < 100 or (y < 100 and x < 100)

print ("and (or) expression")

b = x and (y or x)

print ("and (and) expression")

b = x and (y and x)

print ("or (or) expression")

b = x or (y or x)

print ("ond (or) and expression")

b = x and (y or x) and z

print ("or (and) or expression")

b = x or (y and x) or z

print ("and of two ors")

b = (x or z) and (y or z)
print ("or of two ands")

b = (x and z) or (y and z)

print ("and (or) and (or) expression with comparisons")

b = x < 100 and (y < 100 or x < 100) and (z < 100 or x < 100)

print ("and (or) and or or expression with comparisons")

b = x < 100 and (y < 100 or x < 100) and z < 100 or x < 100 or y < 100

print ("and (or) and and and expression with comparisons")

b = x < 100 and (y < 100 or x < 100) and z < 100 and x < 100 and y < 100

print ("or (and) or (and) expression with comparisons")

b = x < 100 or (y < 100 and x < 100) or (z < 100 and x < 100)

print ("and (and) and (and) expression with comparisons")

b = x < 100 and (y < 100 and x < 100) and (z < 100 and x < 100)

print ("or (or) or (or) expression with comparisons")

b = x < 100 or (y < 100 or x < 100) or (z < 100 or x < 100)

print ("4 and expression with comparisons")

b = x < 100 and y < 100 and x < 100 and z < 100 and x < 100

print ("4 or expression with comparisons")

b = x < 100 or y < 100 or x < 100 or z < 100 or x < 100

print ("and (or or) and (or or) expression with comparisons")

b = x < 100 and (y < 100 or x < 100 or z < 100)
		and (y < 100 or x < 100 or z < 100)
print ("and (or and or) and (or and or) expression with comparisons")

b = x < 100 and (y < 100 or (x < 100 and x > 100) or z < 100)
		and (y < 100 or (x < 100 and x > 100) or z < 100)

print ("or (and or and) or (and or and) expression with comparisons")

b = x < 100 or (y < 100 and (x < 100 or x > 100) and z < 100)
			or (y < 100 and (x < 100 or x > 100) and z < 100)

print ("(((or) and) or)")
a = (((x < 100 or y < 100) and x < 100) or z < 100)

print ("(((or or) and) or)")
a = ((x < 100 or y < 100 or z < 100) and x < 100 or z < 100)

print ("(((or and) and) or)")
a = (x < 100 or y < 100 and z < 100) and x < 100 or z < 100

print ("(((or and) and) or) and error()")
a = (((x < 100 or y < 100 and z < 100) and x < 100) or z < 100) and error()

print ("(or (and (or)))")
a = x < 100 or (y < 100 and (x < 100 or z < 100))

print ("(not or (and (or)))")
a = (not (x < 100)) or (y < 100 and (x < 100 or z < 100))
