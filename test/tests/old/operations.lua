local tenth_a = 1 / 10
local ten_a = 1 * 10
local negative_nine_a = 1 - 10
local eleven_a = 1 + 10

print("tenth_a: " .. tostring(tenth_a))
print("ten_a: " .. tostring(ten_a))
print("negative_nine_a: " .. tostring(negative_nine_a))
print("eleven_a: " .. tostring(eleven_a))

local tenth_b = 1 / ten_a
local ten_b = 1 * ten_a
local negative_nine_b = 1 - ten_a
local eleven_b = 1 + ten_a

print("tenth_b: " .. tostring(tenth_b))
print("ten_b: " .. tostring(ten_b))
print("negative_nine_b: " .. tostring(negative_nine_b))
print("eleven_b: " .. tostring(eleven_b))

local tenth_c = 1 / ten_a / tenth_a
local ten_c = 1 * ten_a * tenth_a
local negative_nine_c = 1 - ten_a - tenth_a
local eleven_c = 1 + ten_a + tenth_a

print("tenth_c: " .. tostring(tenth_c))
print("ten_c: " .. tostring(ten_c))
print("negative_nine_c: " .. tostring(negative_nine_c))
print("eleven_c: " .. tostring(eleven_c))

local tenth_d = (1 / ten_a) / tenth_a
local ten_d = (1 * ten_a) * tenth_a
local negative_nine_d = (1 - ten_a) - tenth_a
local eleven_d = (1 + ten_a) + tenth_a

print("tenth_d: " .. tostring(tenth_d))
print("ten_d: " .. tostring(ten_d))
print("negative_nine_d: " .. tostring(negative_nine_d))
print("eleven_d: " .. tostring(eleven_d))

local tenth_e = 1 / (ten_a / tenth_a)
local ten_e = 1 * (ten_a * tenth_a)
local negative_nine_e = 1 - (ten_a - tenth_a)
local eleven_e = 1 + (ten_a + tenth_a)

print("tenth_e: " .. tostring(tenth_e))
print("ten_e: " .. tostring(ten_e))
print("negative_nine_e: " .. tostring(negative_nine_e))
print("eleven_e: " .. tostring(eleven_e))

local tenth_f = 1 / ten_a / tenth_a / 1.0
local ten_f = 1 * ten_a * tenth_a * 1.0
local negative_nine_f = 1 - ten_a - tenth_a - 1.0
local eleven_f = 1 + ten_a + tenth_a + 1.0

print("tenth_f: " .. tostring(tenth_f))
print("ten_f: " .. tostring(ten_f))
print("negative_nine_f: " .. tostring(negative_nine_f))
print("eleven_f: " .. tostring(eleven_f))

local tenth_g = (1 / ten_a) / tenth_a / 1.0
local ten_g = (1 * ten_a) * tenth_a * 1.0
local negative_nine_g = (1 - ten_a) - tenth_a - 1.0
local eleven_g = (1 + ten_a) + tenth_a + 1.0

print("tenth_g: " .. tostring(tenth_g))
print("ten_g: " .. tostring(ten_g))
print("negative_nine_g: " .. tostring(negative_nine_g))
print("eleven_g: " .. tostring(eleven_g))

local tenth_h = 1 / (ten_a / tenth_a) / 1.0
local ten_h = 1 * (ten_a * tenth_a) * 1.0
local negative_nine_h = 1 - (ten_a - tenth_a) / 1.0
local eleven_h = 1 + (ten_a + tenth_a) + 1.0

print("tenth_h: " .. tostring(tenth_h))
print("ten_h: " .. tostring(ten_h))
print("negative_nine_h: " .. tostring(negative_nine_h))
print("eleven_h: " .. tostring(eleven_h))

local tenth_i = (1 / ten_a) / (tenth_a / 1.0)
local ten_i = (1 * ten_a) * (tenth_a * 1.0)
local negative_nine_i = (1 - ten_a) - (tenth_a / 1.0)
local eleven_i = (1 + ten_a) + (tenth_a + 1.0)

print("tenth_i: " .. tostring(tenth_i))
print("ten_i: " .. tostring(ten_i))
print("negative_nine_i: " .. tostring(negative_nine_i))
print("eleven_i: " .. tostring(eleven_i))

local point_nine = 0.9
local two = 2
local three = 3

local a = {}
local b = {}

a[#a + 1] = 1 + two + three
a[#a + 1] = 1 + two - three
a[#a + 1] = 1 + two * three
a[#a + 1] = 1 + two / three
a[#a + 1] = 1 + two^three

b[#b + 1] = 1 + (two + three)
b[#b + 1] = 1 + (two - three)
b[#b + 1] = 1 + (two * three)
b[#b + 1] = 1 + (two / three)
b[#b + 1] = 1 + (two^three)

a[#a + 1] = 1 - two + three
a[#a + 1] = 1 - two - three
a[#a + 1] = 1 - two * three
a[#a + 1] = 1 - two / three
a[#a + 1] = 1 - two^three

b[#b + 1] = 1 - (two + three)
b[#b + 1] = 1 - (two - three)
b[#b + 1] = 1 - (two * three)
b[#b + 1] = 1 - (two / three)
b[#b + 1] = 1 - (two^three)

a[#a + 1] = 1 * two + three
a[#a + 1] = 1 * two - three
a[#a + 1] = 1 * two * three
a[#a + 1] = 1 * two / three
a[#a + 1] = 1 * two^three

b[#b + 1] = 1 * (two + three)
b[#b + 1] = 1 * (two - three)
b[#b + 1] = 1 * (two * three)
b[#b + 1] = 1 * (two / three)
b[#b + 1] = 1 * (two^three)

a[#a + 1] = 1 / two + three
a[#a + 1] = 1 / two - three
a[#a + 1] = 1 / two * three
a[#a + 1] = 1 / two / three
a[#a + 1] = 1 / two^three

b[#b + 1] = 1 / (two + three)
b[#b + 1] = 1 / (two - three)
b[#b + 1] = 1 / (two * three)
b[#b + 1] = 1 / (two / three)
b[#b + 1] = 1 / (two^three)

a[#a + 1] = 2^two + three
a[#a + 1] = 2^two - three
a[#a + 1] = 2^two * three
a[#a + 1] = 2^two / three
a[#a + 1] = 2^two^three

b[#b + 1] = (2^two) + three
b[#b + 1] = (2^two) - three
b[#b + 1] = (2^two) * three
b[#b + 1] = (2^two) / three
b[#b + 1] = (2^two)^three

for i = 1, #a do
	print("a[" .. tostring(i) .. "]: " .. tostring(a[i]))
end

for j = 1, #b do
	print("b[" .. tostring(j) .. "]: " .. tostring(b[j]))
end

local powers_a = point_nine^two^two^three
local powers_b = point_nine^(two^(two^three))
local powers_c = ((point_nine^two)^two)^three
local powers_d = (point_nine^(two^two)^three)

print("powers_a: " .. tostring(powers_a))
print("powers_b: " .. tostring(powers_b))
print("powers_c: " .. tostring(powers_c))
print("powers_d: " .. tostring(powers_d))

local concatenation_a = "string" .. "string_2" .. "string_3"
local concatenation_b = "string" .. ("string_2" .. "string_3")
local concatenation_c = ("string" .. "string_2") .. "string_3"

print("concatenation_a: " .. tostring(concatenation_a))
print("concatenation_b: " .. tostring(concatenation_b))
print("concatenation_c: " .. tostring(concatenation_c))

local test_a = ten_a / 1 / negative_nine_a
local test_b = ten_a / (1 / negative_nine_a)

print("test_a: " .. tostring(test_a))
print("test_b: " .. tostring(test_b))

local test_c = math.floor(ten_a / 1 / negative_nine_a)
local test_d = math.floor(ten_a / (1 / negative_nine_a))

print("test_c: " .. tostring(test_c))
print("test_d: " .. tostring(test_d))

local test_e = ten_b / 1 / negative_nine_b
local test_f = ten_b / (1 / negative_nine_b)

print("test_e: " .. tostring(test_e))
print("test_f: " .. tostring(test_f))

local test_g = math.floor(ten_b / 1 / negative_nine_b)
local test_h = math.floor(ten_b / (1 / negative_nine_b))

print("test_g: " .. tostring(test_g))
print("test_h: " .. tostring(test_h))

local test_i = ten_b / negative_nine_b / 1
local test_j = ten_b / (negative_nine_b / 1)

print("test_i: " .. tostring(test_i))
print("test_j: " .. tostring(test_j))

local test_k = math.floor(ten_b / negative_nine_b / 1)
local test_l = math.floor(ten_b / (negative_nine_b / 1))

print("test_k: " .. tostring(test_k))
print("test_l: " .. tostring(test_l))

local test_i = ten_b / negative_nine_b / 1
local test_j = ten_b / (negative_nine_b / 1)

print("test_i: " .. tostring(test_i))
print("test_j: " .. tostring(test_j))

local test_k = math.floor(ten_b / negative_nine_b / 1)
local test_l = math.floor(ten_b / (negative_nine_b / 1))

print("test_k: " .. tostring(test_k))
print("test_l: " .. tostring(test_l))

local long_division_a = tenth_b / 1 / 1 / eleven_b / 1 / eleven_b / 1 / 1 / tenth_b / negative_nine_b / tenth_b / 1 / 1
local long_division_b = tenth_b / (1 / (1 / ((eleven_b / (1 / ((eleven_b / (1 / (1 / ((tenth_b / negative_nine_b) / tenth_b)))) / 1))) / 1)))

print("long_division_a: " .. tostring(long_division_a))
print("long_division_b: " .. tostring(long_division_b))

local long_division_c = tenth_b / eleven_b^negative_nine_b * 1 / eleven_b * 1 / eleven_b / 1 / eleven_b / 1 / ten_b + 1 / tenth_b / ten_b + negative_nine_b / tenth_b / ten_b + 1 - ten_b / 1
local long_division_d = tenth_b / eleven_b^negative_nine_b * (1 / eleven_b * (1 / ((eleven_b / (1 / ((eleven_b / (1 / ten_b + (1 / ((tenth_b / ten_b + negative_nine_b) / tenth_b)))) / ten_b + 1))) - ten_b / 1)))

print("long_division_c: " .. tostring(long_division_c))
print("long_division_d: " .. tostring(long_division_d))