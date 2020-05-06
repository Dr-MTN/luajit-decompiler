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
from optparse import OptionParser, OptionGroup
from shutil import copyfile

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
import ljd.ast.printast
import ljd.lua.writer

import ljd.ast.nodes as nodes


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
    def __init__(self):
        # Parser arguments
        parser = OptionParser()

        # Single file input target. Not to be used with -r
        parser.add_option("-f", "--file",
                          type="string", dest="file_name", default="",
                          help="input file name", metavar="FILE")

        # Directory in which to recurse and process all files. Not to be used with -f
        parser.add_option("-r", "--recursive",
                          type="string", dest="folder_name", default="",
                          help="recursively decompile lua files", metavar="FOLDER")

        # Single file output destination. Not to be used with -r
        parser.add_option("-o", "--output",
                          type="string", dest="output", default="",
                          help="output file for writing")

        # LEGACY OPTION. Directory to output processed files during recursion. Not to be used with -f
        parser.add_option("-d", "--dir_out",
                          type="string", dest="folder_output", default="",
                          help="LEGACY OPTION. directory to output decompiled lua scripts", metavar="FOLDER")

        # Allow overriding the default .lua file extension (e.g. when binary lua files are saved as .luac)
        parser.add_option("-e", "--file-extension",
                          type="string", dest="lua_ext", default=".lua",
                          help="file extension filter for recursive searches", metavar="EXT")

        # Prefer raw source files when available? The PAYDAY games sometimes come with .lua_source files.
        parser.add_option("--prefer_sources",
                          type="string", dest="lua_src_ext", default="",
                          help="use source files", metavar="EXT")

        # Prevent most integrity asserts from canceling decompilation
        parser.add_option("-c", "--catch_asserts",
                          action="store_true", dest="catch_asserts", default=False,
                          help="attempt inline error reporting without breaking decompilation")

        # Include line number comments for function definitions
        parser.add_option("--with-line-numbers",
                          action="store_true", dest="include_line_numbers", default=False,
                          help="add comments with line numbers for function definitions")

        # Single file linemap output
        parser.add_option("--line-map-output",
                          type="string", dest="line_map_output_file", default="",
                          help="line map output file for writing", metavar="FILE")

        # Some previous luajit compilers produced some unexpected instructions that are not handled by the regular
        # process. If we bypass some of the safety checks, we may be able to deal with them correctly. This works
        # for PAYDAY 2 and RAID, but may have unexpected side effects for other projects. On by default.
        parser.add_option("--unsafe", type="string", dest="unsafe_extra_pass", default="true",
                          help="unsafe extra pass to try to correct some leftover values")

        group = OptionGroup(parser, "Debug Options")

        # Output a log of exceptions and information during decompilation
        parser.add_option("-l", "--enable_logging",
                          action="store_true", dest="enable_logging", default=False,
                          help="log info and exceptions to external file while decompiling")

        group.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, help="verbose")

        # Skip some processing steps
        group.add_option("--no-unwarp", action="store_true", dest="no_unwarp", default=False,
                         help="do not run the unwarper")

        # Output the pseudoasm of the initial AST instead of decompiling the input
        group.add_option("--asm", action="store_true", dest="output_pseudoasm", default=False, help="Print pseudo asm")

        group.add_option("--dump", action="store_true", dest="dump_ast", default=False, help="Dump AST")

        (self.options, args) = parser.parse_args()

        # Allow the input argument to be either a folder or a file.
        if len(args) == 1:
            if self.options.file_name or self.options.folder_name:
                parser.error("Conflicting file arguments.")
                sys.exit(1)

            if os.path.isdir(args[0]):
                self.options.folder_name = args[0]
            else:
                self.options.file_name = args[0]
        elif len(args) > 1:
            parser.error("Too many arguments.")
            sys.exit(1)

        # Verify arguments
        if self.options.folder_name:
            pass
        elif not self.options.file_name:
            parser.error("Options -f or -r are required.")
            sys.exit(1)

        # Determine output folder/file
        if self.options.folder_output:
            if not self.options.output:
                self.options.output = self.options.folder_output
            self.options.folder_output = None

        if self.options.output:
            if self.options.folder_name:
                if os.path.isfile(self.options.output):
                    parser.error("Output folder is a file.")
                    sys.exit(0)

        # TODO merge into the module handling below
        if self.options.catch_asserts:
            ljd.ast.builder.handle_invalid_functions = True

        for mod in [ljd.ast.unwarper, ljd.ast.slotworks, ljd.ast.validator]:
            if self.options.dump_ast:
                mod.debug_dump = True
            if self.options.catch_asserts:
                mod.catch_asserts = True
            if self.options.verbose:
                mod.verbose = True

        if self.options.include_line_numbers:
            ljd.lua.writer.show_line_info = True

        self.options.unsafe_extra_pass = self.options.unsafe_extra_pass.lower() in ['true', '1', 't', 'y', 'yes']

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

        self.logger = logger

    def main(self):
        # Recursive batch processing
        if self.options.folder_name:
            self.options.folder_name = os.path.sep.join(os.path.normpath(self.options.folder_name).split('\\'))
            for path, _, file_names in os.walk(self.options.folder_name):
                for file in file_names:
                    # Skip files we're not interested in based on the extension
                    if not file.endswith(self.options.lua_ext):
                        continue

                    full_path = os.path.join(path, file)

                    # Copy raw source files?
                    if self.options.enable_logging:
                        self.logger.info(full_path)
                    try:
                        if self.options.lua_src_ext:
                            src_file = os.path.splitext(file)[0] + "." + self.options.lua_src_ext
                            full_src_path = os.path.join(path, src_file)
                            if os.path.exists(full_src_path) and os.path.getsize(full_src_path) > 0:
                                if self.options.enable_logging:
                                    self.logger.info("Skipping {0}: Source file available.".format(full_path))

                                new_path = os.path.join(self.options.output,
                                                        os.path.relpath(full_path, self.options.folder_name))
                                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                                if not file.endswith('.lua'):
                                    new_path = new_path[:-1]
                                copyfile(full_src_path, new_path)
                                if self.options.enable_logging:
                                    self.logger.info("Success")
                                continue
                    except (KeyboardInterrupt, SystemExit):
                        print("Interrupted")
                        sys.stdout.flush()
                        if self.options.enable_logging:
                            self.logger.info("Exit")
                        return 0
                    except OSError as exc:
                        print("\n--; Exception in %s" % full_path)
                        print("-- %s" % exc)
                        if self.options.enable_logging:
                            self.logger.info("OS Exception")
                            self.logger.debug('', exc_info=True)
                        continue

                    # Process current file
                    try:
                        self.process_file(file, full_path, self.logger)
                    except (KeyboardInterrupt, SystemExit):
                        print("Interrupted")
                        sys.stdout.flush()
                        if self.options.enable_logging:
                            self.logger.info("Exit")
                        return 0
                    except Exception as exc:
                        print("\n--; Exception in {0}".format(full_path))
                        print(exc)
                        if self.options.enable_logging:
                            self.logger.info("Exception")
                            self.logger.debug('', exc_info=True)
            return 0

        # Single file processing
        ast = self.decompile(self.options.file_name)

        if not ast:
            return 1

        generate_linemap = bool(self.options.line_map_output_file)

        if not self.options.output_pseudoasm:
            if self.options.output:
                output_file = self.options.output
                if os.path.isdir(output_file):
                    output_file = os.path.join(
                        output_file, os.path.splitext(os.path.basename(self.options.file_name))[0], ".lua"
                    )
                line_map = self.write_file(ast, output_file, generate_linemap=generate_linemap)
            else:
                line_map = ljd.lua.writer.write(sys.stdout, ast, generate_linemap=generate_linemap)

            if self.options.line_map_output_file:
                with open(self.options.line_map_output_file, "wb") as lm_out:
                    for from_line in sorted(line_map):
                        to_line = line_map[from_line]
                        lm_out.write(struct.pack("!II", from_line, to_line))

        return 0

    def process_file(self, file, full_path, logger):
        try:
            ast = self.decompile(full_path)

            if not self.options.output:
                print("\n--; Decompile of {0}".format(full_path))
                ljd.lua.writer.write(sys.stdout, ast)
                self.lock.release()
                return 0

            new_path = os.path.join(self.options.output, os.path.relpath(full_path, self.options.folder_name))
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            if not file.endswith('.lua'):
                new_path = new_path[:-1]
            self.write_file(ast, new_path)
            if self.options.enable_logging:
                logger.info("Success")
            return 0
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise
        return 1

    def write_file(self, ast, file_name, **kwargs):
        if self.options.enable_logging:
            self.logger.debug("Writing file {0}...".format(file_name))
        with open(file_name, "w", encoding="utf8") as out_file:
            return ljd.lua.writer.write(out_file, ast, **kwargs)

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

        if self.options.output_pseudoasm:
            ljd.pseudoasm.writer.write(sys.stdout, header, prototype)

        ast = ljd.ast.builder.build(header, prototype)

        assert ast is not None

        ljd.ast.validator.validate(ast, warped=True)

        ljd.ast.mutator.pre_pass(ast)

        ljd.ast.validator.validate(ast, warped=True)

        ljd.ast.locals.mark_locals(ast)

        if self.options.dump_ast:
            ljd.ast.printast.dump("AST [locals]", ast)
            return

        try:
            ljd.ast.slotworks.eliminate_temporary(ast, identify_slots=True)
        except AssertionError:
            if self.options.catch_asserts:
                print("-- Decompilation Error: ljd.ast.slotworks.eliminate_temporary(ast)\n", file=sys.stdout)
            else:
                raise

        # ljd.ast.validator.validate(ast, warped=True)

        if not self.options.no_unwarp:
            ljd.ast.unwarper.unwarp(ast, False)

            # ljd.ast.validator.validate(ast, warped=False)

            if True:
                ljd.ast.locals.mark_local_definitions(ast)

                # ljd.ast.validator.validate(ast, warped=False)

                ljd.ast.mutator.primary_pass(ast)

                try:
                    ljd.ast.validator.validate(ast, warped=False)
                except AssertionError:
                    if self.options.catch_asserts:
                        print("-- Decompilation Error: ljd.ast.validator.validate(ast, warped=False)\n",
                              file=sys.stdout)
                    else:
                        raise

                if True:
                    # Mark remaining (unused) locals in empty loops, before blocks and at the end of functions
                    ljd.ast.locals.mark_locals(ast, alt_mode=True)
                    ljd.ast.locals.mark_local_definitions(ast)

                    # Extra (unsafe) slot elimination pass (iff debug info is available) to deal with compiler issues
                    for ass in ast.statements.contents if self.options.unsafe_extra_pass else []:
                        if not isinstance(ass, nodes.Assignment):
                            continue

                        for node in ass.expressions.contents:
                            if not getattr(node, "_debuginfo", False) or not node._debuginfo.variable_info:
                                continue

                            contents = None
                            if isinstance(node, nodes.FunctionDefinition):
                                contents = [node.statements.contents]
                            elif isinstance(node, nodes.TableConstructor):
                                contents = [node.array.contents, node.records.contents]
                            else:
                                continue

                            # Check for any remaining slots
                            try:
                                for content_list in contents:
                                    for subnode in content_list:
                                        if isinstance(subnode, nodes.Assignment):
                                            for dst in subnode.destinations.contents:
                                                if isinstance(dst, nodes.Identifier) and dst.type == dst.T_SLOT:
                                                    raise StopIteration
                            except StopIteration:
                                ljd.ast.slotworks.eliminate_temporary(node, unwarped=True, safe_mode=False)

                                # Manual cleanup
                                for content_list in contents:
                                    j = len(content_list) - 1
                                    for i, subnode in enumerate(reversed(content_list)):
                                        if getattr(subnode, "_invalidated", False):
                                            del content_list[j - i]

        return ast


if __name__ == "__main__":
    main_obj = Main()
    retval = main_obj.main()
    sys.exit(retval)
