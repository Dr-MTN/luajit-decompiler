LuaJIT raw-bytecode decompiler (LJD)
===

The original name was _ljwthgnd_ as in _LuaJIT 'What The Hell is Going On'
Decompiler_ named under the LuaJIT C sources variable naming convention.


__WARNING!__ This code is nor finished, nor tested yet! There is no even
slightest warranty that resulting code is even near to the original. Use it at
your own risk of the wasted time.

__SECOND WARNING!__ And, BTW, this all is a one huge prototype. Because the
"release" version should be written into lua itself. Because it's cool to
decompile the decompiler - a great test too!

How to use it
---

There is not argument parsing right now, so comment out things in the ```main.py```
script and launch it as in ```main.py path/to/file.luac```

TODO
---

There is a lot of work to do, in the order of priority

1. AST Optimizations - currently the resulting code is not even compilable.
	1. Slots elimination - in case of debug information present it should
	   be possible to eliminate all the slots in the resulting code,
	   drastically reducing it's size and improving readability.

	   (and after that this will be really _decompiler_ and not a just
	   and improved disassembler).

	   In case of debug information NOT present (which is not supported
	   right now) some slots for local variables may remain.

	2. MULTRES elimination - pretty much straightforward after the slots
	   elimination. The last thing to be done before the resulting code
	   will be compilable.

	3. If statements recomposition
	   ```lua
	   if something then
	   	...
	   elseif something_else then
		...
	   end
	   ```

	   is now translated into
	   ```lua
	   if something then
	   	...
	   else
	   	if something_else then
			...
		end
	   end
	   ```

	   *This should be fixed for code readability*

	4. Logical expressions recomposition - logical expressions are not
	   broken into dozen small if's. *This should be fixed for code
	   readability*
	
	5. Use the line information (or common sense if there is no line
	   information) to squash similar expressions into a single expression.
	
	6. Function names as _function name ()_ instead of _name = function()_

2. Formatting improvements
	1. Use operator priority information for arithmetic expressions to omit
	   redundant parentheses.

	2. Use the line information (or common sense) to preserve empty lines
	   and break long statements like in the original code.
	   *this should be done for code readability*

	3. Use method-style calls and definitions for tables.

3. Features not supported:
	1. GOTO statement (from lua 5.2) - it isn't hard to add the goto
	   statement support into the AST builder, but this will require random
	   look-aheads to distinguish between GOTO and loop statements. And
	   that's not cool, so I guess I'll wait until 5.2 will be released and
	   fully supported by LuaJIT.

	2. Local sub-blocks:
	```lua
	do
		...
	end
	```
	   These subblocks are not reflected anyhow directly in the bytecode.
	   The only way to guess them is to watch local variable scopes, which
	   is simple enough in case of non-stripped bytecode and a bit
	   harder otherwise.
