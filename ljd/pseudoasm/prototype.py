#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.pseudoasm.constants
import ljd.pseudoasm.instructions


def write(writer, prototype):
    _write_header(writer, prototype)
    write_body(writer, prototype)

    writer.stream.close_block("")


def _write_header(writer, prototype):
    writer.stream.open_block("main {0}", format_header(writer, prototype))


def format_header(writer, prototype):
    return "{s}:{start}-{end}: {argn}{varg} args," \
           " {uvs} upvalues, {slots} slots".format(
            s=writer.source,
            start=prototype.first_line_number,
            end=prototype.first_line_number + prototype.lines_count,
            argn=prototype.arguments_count,
            varg="+" if prototype.flags.is_variadic else "",
            uvs=len(prototype.constants.upvalue_references),
            slots=prototype.framesize
        )


def write_debug_info(writer, prototype):
    if prototype.lines_count == 0:
        return

    debuginfo = prototype.debuginfo
    upvalue_name = debuginfo.upvalue_variable_names
    writer.stream.write_line(";;;; upvalue names ;;;;")
    for slot, name in enumerate(upvalue_name):
        writer.stream.write_line("  {0}:\t{1}".format(slot, name))

    writer.stream.write_line(";;;; variable info ;;;;")
    variable_info = debuginfo.variable_info
    for var in variable_info:
        writer.stream.write_line("  {start}-{end}:\t{name}".format(
            start=max(0, var.start_addr - 1),
            end=var.end_addr - 1,
            name=var.name,
        ));


def write_body(writer, prototype):
    writer.stream.write_line(";;;; constant tables ;;;;")
    ljd.pseudoasm.constants.write_tables(writer, prototype)

    write_debug_info(writer, prototype)

    writer.stream.write_line(";;;; instructions ;;;;")
    ljd.pseudoasm.instructions.write(writer, prototype)
