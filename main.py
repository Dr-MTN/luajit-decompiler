#!/usr/bin/python3
#
# The MIT License (MIT)
#
# Copyright (c) 2013 Andrian Nord
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import logging
import os
import sys
import struct
from datetime import datetime
from optparse import OptionParser

import ljd.rawdump.parser
import ljd.rawdump.code
import ljd.pseudoasm.writer
import ljd.pseudoasm.instructions
import ljd.ast.builder
import ljd.ast.slotworks
import ljd.ast.validator
import ljd.ast.locals
import ljd.ast.unwarper
import ljd.ast.mutator
import ljd.lua.writer

import ljd.ast.nodes as nodes


def dump(name, obj, level=0):
    indent = level * '\t'

    if name is not None:
        prefix = indent + name + " = "
    else:
        prefix = indent

    if isinstance(obj, (int, float, str)):
        print(prefix + str(obj))
    elif isinstance(obj, list):
        print(prefix + "[")

        for value in obj:
            dump(None, value, level + 1)

        print(indent + "]")
    elif isinstance(obj, dict):
        print(prefix + "{")

        for key, value in obj.items():
            dump(key, value, level + 1)

        print(indent + "}")
    else:
        print(prefix + obj.__class__.__name__)

        for key in dir(obj):
            if key.startswith("__"):
                continue

            val = getattr(obj, key)
            dump(key, val, level + 1)


class MakeFileHandler(logging.FileHandler):
    def __init__(self, filename, *args, **kwargs):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        logging.FileHandler.__init__(self, filename, *args, **kwargs)


def set_luajit_version(bc_version):
    # If we're already on this version, skip resetting everything
    if ljd.CURRENT_VERSION == bc_version:
        return

    ljd.CURRENT_VERSION = bc_version
    # Now we know the LuaJIT version, initialise the opcodes
    if bc_version == 2.0:
        from ljd.rawdump.luajit.v2_0.luajit_opcode import _OPCODES as opcodes
    elif bc_version == 2.1:
        from ljd.rawdump.luajit.v2_1.luajit_opcode import _OPCODES as opcodes
    else:
        raise Exception("Unknown LuaJIT opcode module name for version " + str(bc_version))

    ljd.rawdump.code.init(opcodes)
    ljd.ast.builder.init()
    ljd.pseudoasm.instructions.init()


class Main:
    def main(self):
        # Parser arguments
        parser = OptionParser()

        # Single file input target. Not to be used with -r
        parser.add_option("-f", "--file",
                          type="string", dest="file_name", default="",
                          help="input file name", metavar="FILE")

        # Single file output destination. Not to be used with -r
        parser.add_option("-o", "--output",
                          type="string", dest="output_file", default="",
                          help="output file for writing", metavar="FILE")

        # Directory in which to recurse and process all files. Not to be used with -f
        parser.add_option("-r", "--recursive",
                          type="string", dest="folder_name", default="",
                          help="recursively decompile lua files", metavar="FOLDER")

        # Directory to output processed files during recursion. Not to be used with -f
        parser.add_option("-d", "--dir_out",
                          type="string", dest="folder_output", default="",
                          help="directory to output decompiled lua scripts", metavar="FOLDER")

        # Prevent most integrity asserts from canceling decompilation
        parser.add_option("-c", "--catch_asserts",
                          action="store_true", dest="catch_asserts", default=False,
                          help="attempt inline error reporting without breaking decompilation")

        # Output a log of exceptions and information during decompilation
        parser.add_option("-l", "--enable_logging",
                          action="store_true", dest="enable_logging", default=False,
                          help="log info and exceptions to external file while decompiling")

        # Single file linemap output
        parser.add_option("--line-map-output",
                          type="string", dest="line_map_output_file", default="",
                          help="line map output file for writing", metavar="FILE")

        # Output the pseudoasm of the initial AST instead of decompiling the input
        parser.add_option("--asm", action = "store_true", dest="write_pseudoasm", default=False, help="Print pseudo asm")

        (self.options, args) = parser.parse_args()

        # Send assert catch argument to modules
        if self.options.catch_asserts:
            ljd.ast.unwarper.catch_asserts = True
            ljd.ast.slotworks.catch_asserts = True
            ljd.ast.validator.catch_asserts = True

        # Start logging if required
        if self.options.enable_logging:
            logger = logging.getLogger('LJD')
            logger.setLevel(logging.INFO)

            fh = MakeFileHandler(f'logs/{datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}.log')
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)

            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
            console.setFormatter(formatter)
            logger.addHandler(console)
        else:
            logger = None

        # Recursive batch processing
        if self.options.folder_name:
            for path, _, filenames in os.walk(self.options.folder_name):
                for file in filenames:
                    if file.endswith('.lua'):
                        full_path = os.path.join(path, file)

                        if self.options.enable_logging:
                            logger.info(full_path)
                        try:
                            self.decompile(full_path)
                            new_path = os.path.join(self.options.folder_output,
                                                    os.path.relpath(full_path, self.options.folder_name))
                            os.makedirs(os.path.dirname(new_path), exist_ok=True)
                            self.write_file(new_path)
                            if self.options.enable_logging:
                                logger.info("Success")
                        except KeyboardInterrupt:
                            if self.options.enable_logging:
                                logger.info("Exit")
                            return 0
                        except:
                            if self.options.enable_logging:
                                logger.info("Exception")
                                logger.debug('', exc_info=True)

            return 0

        # Single file processing
        if self.options.file_name == "":
            print(self.options)
            parser.error("Options -f or -r are required.")
            return 0

        self.decompile(self.options.file_name)

        generate_linemap = bool(self.options.line_map_output_file)

        if not self.options.write_pseudoasm:
            if self.options.output_file:
                line_map = self.write_file(self.options.output_file, generate_linemap=generate_linemap)
            else:
                line_map = ljd.lua.writer.write(sys.stdout, self.ast, generate_linemap=generate_linemap)

        if self.options.line_map_output_file:
            with open(self.options.line_map_output_file, "wb") as lm_out:
                for from_line in sorted(line_map):
                    to_line = line_map[from_line]
                    lm_out.write(struct.pack("!II", from_line, to_line))

        return 0

    def write_file(self, file_name, **kwargs):
        with open(file_name, "w", encoding="utf8") as out_file:
            return ljd.lua.writer.write(out_file, self.ast, **kwargs)

    def decompile(self, file_in):
        def on_parse_header(preheader):
            # Identify the version of LuaJIT used to compile the file
            bc_version = None
            if preheader.version == 1:
                bc_version = 2.0
            elif preheader.version == 2:
                bc_version = 2.1
            else:
                raise Exception("Unsupported bytecode version: " + str(bc_version))

            set_luajit_version(bc_version)

        header, prototype = ljd.rawdump.parser.parse(file_in, on_parse_header)

        if not prototype:
            return 1

        if self.options.write_pseudoasm:
            ljd.pseudoasm.writer.write(sys.stdout, header, prototype)

        self.ast = ljd.ast.builder.build(header, prototype)

        assert self.ast is not None

        ljd.ast.validator.validate(self.ast, warped=True)

        ljd.ast.mutator.pre_pass(self.ast)

        # ljd.ast.validator.validate(self.ast, warped=True)

        ljd.ast.locals.mark_locals(self.ast)

        # ljd.ast.validator.validate(self.ast, warped=True)

        try:
            ljd.ast.slotworks.eliminate_temporary(self.ast, ignore_ambiguous=True, identify_slots=True)
        except:
            if self.options.catch_asserts:
                print("-- Decompilation Error: ljd.ast.slotworks.eliminate_temporary(self.ast)\n", file=sys.stdout)
            else:
                raise

        try:
            ljd.ast.slotworks.simplify_ast(self.ast, dirty_callback=ljd.ast.slotworks.eliminate_temporary)
        except:
            if self.options.catch_asserts:
                print("-- Decompilation Error: ljd.ast.slotworks.simplify_ast(self.ast)\n", file=sys.stdout)
            else:
                raise

        # ljd.ast.validator.validate(self.ast, warped=True)

        if True:
            ljd.ast.unwarper.unwarp(self.ast, False)

            # ljd.ast.validator.validate(self.ast, warped=False)

            if True:
                ljd.ast.locals.mark_local_definitions(self.ast)

                # ljd.ast.validator.validate(self.ast, warped=False)

                ljd.ast.mutator.primary_pass(self.ast)

                try:
                    ljd.ast.validator.validate(self.ast, warped=False)
                except:
                    if self.options.catch_asserts:
                        print("-- Decompilation Error: ljd.ast.validator.validate(self.ast, warped=False)\n",
                              file=sys.stdout)
                    else:
                        raise

                ljd.ast.locals.mark_locals(self.ast, alt_mode=True)
                ljd.ast.locals.mark_local_definitions(self.ast)


if __name__ == "__main__":
    main_obj = Main()
    retval = main_obj.main()
    sys.exit(retval)
