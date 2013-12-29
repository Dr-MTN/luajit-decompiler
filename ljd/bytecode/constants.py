#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

T_NIL = 0
T_FALSE = 1
T_TRUE = 2


class Table():
	def __init__(self):
		self.array = []
		self.dictionary = {}


class Constants():
	def __init__(self):
		self.upvalue_references = []
		self.numeric_constants = []
		self.complex_constants = []
