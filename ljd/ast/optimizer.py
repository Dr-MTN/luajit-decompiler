#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.ast.nodes as nodes


def eliminate_slots(ast):
	assert isinstance(ast, nodes.CodeBlock)

	_traverse_code_block(ast.statements.contents)


def _traverse_code_block():
	pass
