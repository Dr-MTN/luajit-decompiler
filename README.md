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

Python __3.7+__ from Python.org


How To Use:
---

Typical usage (no version configuration list, all files in a directory):
```
python3 ./main.py --recursive ./<input directory> --dir_out ./<output directory> --catch_asserts
```

Note About Bytecode Versions:
---

Different versions of LuaJIT produce different versions of the bytecode. Currently revision
`1` (corresponding to LuaJIT 2.0.x) and revision `2` (corresponding to LuaJIT 2.1.x) are supported.

These are the only two versions officially used in LuaJIT. From time to time I've seen files
with a revision code of `3` pop up. This appears to be from RaptorJIT, but more investigation
in that area is needed.

In previous versions of the decompiler, you had to manually specify the version of the files
you are decompiling. This is now done automatically, although there may be bugs when using
the `-r` option with files coming from multiple versions of LuaJIT.

Arguments:
---

"-f", "--file" : Single file input target. Not to be used with "-r"

"-o", "--output" : Single file output destination. Not to be used with "-r"

"-r", "--recursive" : Directory in which to recurse and process all files. Not to be used with "-f"

"-d", "--dir_out" : Directory to output processed files during recursion. Not to be used with "-f"

"-c", "--catch_asserts" : Prevent most integrity asserts from canceling decompilation

"-l", "--enable_logging" : Output a log of exceptions and information during decompilation


IRC:
---

```#ljd at freenode```


TODO:
---

There is a lot of work to do. In order of priority:

0. Logical subexpressions in while statements:
	This is done! As far as I'm aware, this is the only available LuaJIT decompiler
	that can decompile stuff like the following:

	```lua
		while x < (xi and 2 or 3) do
			print ("Hello crazy world!")
		end
	```

	If you're having many failures while decompiling files via other forks of LJD, this
	is quite likely going to solve 90% of your problems.

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

Licence:
---

The original LJD (and Aussiemon's modifications) are distributed under the MIT licence, and a
copy of this is included as `LICENSE-upstream`. However, all changes made by myself
(Campbell "ZNixian" Suter) are licenced under the GNU General Public Licence, version 3 or any later
version of your choice (a copy of which is available in the `LICENSE` file supplied with the source code).

I've chosen this license due to certain dynamics of the videogame modding scene for which these changes
were made. If you have a use for this outside of games, and need a less restrictive licence, please let me know
and I'll most likely be fine to relicence the project either to MIT or (preferrably) LGPL.

Also note that while this licence did not appear as my first modification to this project, I did not
distribute the source before making this change, and never offered those changes under the original licence
(even if the licence file supplied in those revisions was the original one).
