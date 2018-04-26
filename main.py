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
from datetime import datetime
from optparse import OptionParser


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

        # Global override of LuaJIT version, ignores -j
        parser.add_option("-j", "--jit_version",
                          type="string", dest="luajit_version", default="",
                          help="override LuaJIT version, default 2.1, now supports 2.0, 2.1")

        # 'Profiles' that hardcode LuaJIT versions per file
        parser.add_option("-v", "--version_config_list",
                          type="string", dest="version_config_list", default="version_default",
                          help="LuaJIT version config list to use")

        # Prevent most integrity asserts from canceling decompilation
        parser.add_option("-c", "--catch_asserts",
                          action="store_true", dest="catch_asserts", default=False,
                          help="attempt inline error reporting without breaking decompilation")

        # Output a log of exceptions and information during decompilation
        parser.add_option("-l", "--enable_logging",
                          action="store_true", dest="enable_logging", default=False,
                          help="log info and exceptions to external file while decompiling")

        (self.options, args) = parser.parse_args()

        # Initialize opcode set for required LuaJIT version
        basepath = os.path.dirname(sys.argv[0])
        if basepath == "":
            basepath = "."
        if self.options.luajit_version == "":
            version_required = self.check_for_version_config(self.options.file_name)
            sys.path.append(basepath + "/ljd/rawdump/luajit/" + str(version_required) + "/")
        else:
            self.set_version_config(float(self.options.luajit_version))
            sys.path.append(basepath + "/ljd/rawdump/luajit/" + self.options.luajit_version + "/")

        # LuaJIT version is known after the argument is parsed, so delay module import.
        import ljd.rawdump.parser
        import ljd.pseudoasm.writer
        import ljd.ast.builder
        import ljd.ast.validator
        import ljd.ast.locals
        import ljd.ast.slotworks
        import ljd.ast.unwarper
        import ljd.ast.mutator
        import ljd.lua.writer

        # Send assert catch argument to modules
        if self.options.catch_asserts:
            ljd.ast.unwarper.catch_asserts = True
            ljd.ast.slotworks.catch_asserts = True
            ljd.ast.validator.catch_asserts = True

        self.ljd = ljd

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
            if self.options.version_config_list != "version_default":
                print(self.options)
                print("Version config lists are not supported in recursive directory mode.")
                if self.options.enable_logging:
                    logger.info("Exit")
                return 0

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

        if self.options.output_file:
            self.write_file(self.options.output_file)
        else:
            self.ljd.lua.writer.write(sys.stdout, self.ast)

        return 0

    def write_file(self, file_name):
        with open(file_name, "w", encoding="utf8") as out_file:
            self.ljd.lua.writer.write(out_file, self.ast)

    def decompile(self, file_in):
        header, prototype = self.ljd.rawdump.parser.parse(file_in)

        if not prototype:
            return 1

        # self.ljd.pseudoasm.writer.write(sys.stdout, header, prototype)

        self.ast = self.ljd.ast.builder.build(prototype)

        assert self.ast is not None

        self.ljd.ast.validator.validate(self.ast, warped=True)

        self.ljd.ast.mutator.pre_pass(self.ast)

        # self.ljd.ast.validator.validate(self.ast, warped=True)

        self.ljd.ast.locals.mark_locals(self.ast)

        # self.ljd.ast.validator.validate(self.ast, warped=True)

        try:
            self.ljd.ast.slotworks.eliminate_temporary(self.ast)
        except:
            if self.options.catch_asserts:
                print("-- Decompilation Error: self.ljd.ast.slotworks.eliminate_temporary(self.ast)\n", file=sys.stdout)
            else:
                raise

        # self.ljd.ast.validator.validate(self.ast, warped=True)

        if True:
            self.ljd.ast.unwarper.unwarp(self.ast)

            # self.ljd.ast.validator.validate(self.ast, warped=False)

            if True:
                self.ljd.ast.locals.mark_local_definitions(self.ast)

                # self.ljd.ast.validator.validate(self.ast, warped=False)

                self.ljd.ast.mutator.primary_pass(self.ast)

                try:
                    self.ljd.ast.validator.validate(self.ast, warped=False)
                except:
                    if self.options.catch_asserts:
                        print("-- Decompilation Error: self.ljd.ast.validator.validate(self.ast, warped=False)\n",
                              file=sys.stdout)
                    else:
                        raise

    def check_for_version_config(self, file_name):
        import ljd.config.version_config as version_config_file

        # Transform file_name with present working directory
        if len(file_name) > 0 and file_name[0] == ".":
            file_name = file_name.replace(".", "", 1)
        file_name = os.getcwd() + "/" + file_name
        file_name = file_name.replace("\\", "/")
        file_name = file_name.replace("//", "/")

        # Get version config list or default
        try:
            version_list = version_config_file._LUA_FILE_VERSIONS[self.options.version_config_list]
        except KeyError:
            version_list = version_config_file._LUA_FILE_VERSIONS["version_default"]

        # Search for a matching entry
        for config_entry_name in version_list:
            if config_entry_name in file_name:
                self.set_version_config(version_list[config_entry_name])
                break

        return version_config_file.use_version

    @staticmethod
    def set_version_config(version_number):
        import ljd.config.version_config
        ljd.config.version_config.use_version = version_number


if __name__ == "__main__":
    main_obj = Main()
    retval = main_obj.main()
    sys.exit(retval)
