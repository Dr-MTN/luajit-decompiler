LuaJIT Raw-Bytecode Decompiler (LJD)
===

The original name was _ljwthgnd_, as in _LuaJIT 'What The Hell is Going On'
Decompiler_; named under the LuaJIT C sources variable-naming convention.


__WARNING!__ This code is not finished or tested! There is not even
the slightest warranty that the resulting code is even close to the original.
Use the decompiled code at your own risk.

__SECOND WARNING!__ This is all a huge prototype. The "release" version
should be written in Lua itself, because it's cool to
decompile the decompiler — a great test too!


Requirements:
---

Python __3.0+__ from Python.org


How To Use:
---

Typical usage (no version configuration list, all files in a directory):
```
python ./ljd/main.py --recursive ./<input directory> --dir_out ./<output directory> --catch_asserts
```


Arguments:
---

"-f", "--file" : Single file input target. Not to be used with "-r"

"-o", "--output" : Single file output destination. Not to be used with "-r"

"-r", "--recursive" : Directory in which to recurse and process all files. Not to be used with "-f"

"-d", "--dir_out" : Directory to output processed files during recursion. Not to be used with "-f"

"-j", "--jit_version" : Global override of LuaJIT version, ignores -j, currently supports 2.1b3, 2.0

"-v", "--version_config_list" : 'Profiles' that hardcode LuaJIT versions per file, ljd.config.version_config.py

"-c", "--catch_asserts" : Prevent most integrity asserts from canceling decompilation

"-l", "--enable_logging" : Output a log of exceptions and information during decompilation


IRC:
---

```#ljd at freenode```


TODO:
---

There is a lot of work to do. In order of priority:

0. Logical subexpressions in while statements:
	```lua
		while x < (xi and 2 or 3) do
			print ("Hello crazy world!")
		end
	```

	Logical subexpressions (the subexpressions used as operands in
	ariphmetic or comparison operations inside other expressions) are
	currently supported only for ifs. To support them for whiles and
	repeat-untils, the expression unwarping logic should be moved to the
	very beginning. This won't work without all the fixes in
	the loop unwarping logic, so we need to split that and move the fixes
	before expressions, before loops, before ifs. That's not that easy...

1. AST Mutations:
	1. Use the line information (or common sense if there is no line
	   information) to squash similar expressions into single expressions.

2. Formatting improvements (partially-implemented):
	1. Use the line information (or common sense) to preserve empty lines
	   and break long statements like in the original code.
	   
	   This is mostly done, but only in the "common sense" part.

3. Features not supported:
	1. GOTO statement (from Lua 5.2). All the required functionality is
		now in place, but that's a rather low-priority task right now.

	2. Local sub-blocks:
	```lua
	do
		...
	end
	```
	   These subblocks are not directly reflected in the bytecode.
	   The only way to guess their presence is to watch local variable scopes.
	   Simple enough in case of non-stripped bytecode, but a bit
	   harder otherwise.

