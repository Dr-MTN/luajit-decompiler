#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.bytecode.instructions as instructions
from ljd.util.log import errprint

_MAP = [None] * 256


def read(parser):
    global _MAP

    codeword = parser.stream.read_uint(4)

    opcode = codeword & 0xFF

    instruction_class = _MAP[opcode]

    if instruction_class is None:
        errprint("Warning: unknown opcode {0:08x}", opcode)
        instruction_class = instructions.UNKNW  # @UndefinedVariable

    instruction = instruction_class()

    if instruction_class.opcode != opcode:
        instruction.opcode = opcode

    _set_instruction_operands(parser, codeword, instruction)

    return instruction


def _set_instruction_operands(parser, codeword, instruction):
    if instruction.args_count == 3:
        A = (codeword >> 8) & 0xFF
        CD = (codeword >> 16) & 0xFF
        B = (codeword >> 24) & 0xFF
    else:
        A = (codeword >> 8) & 0xFF
        CD = (codeword >> 16) & 0xFFFF

    if instruction.A_type is not None:
        instruction.A = _process_operand(parser, instruction.A_type, A)

    if instruction.B_type is not None:
        instruction.B = _process_operand(parser, instruction.B_type, B)

    if instruction.CD_type is not None:
        instruction.CD = _process_operand(parser, instruction.CD_type, CD)


def _process_operand(parser, operand_type, operand):
    if operand_type == instructions.T_STR \
            or operand_type == instructions.T_TAB \
            or operand_type == instructions.T_FUN \
            or operand_type == instructions.T_CDT:
        return parser.complex_constants_count - operand - 1
    elif operand_type == instructions.T_JMP:
        return operand - 0x8000
    else:
        return operand


def _init():
    global _MAP

    # from opcode import _OPCODES
    from luajit_opcode import _OPCODES

    for opcode, instruction in sorted(_OPCODES, key=lambda x: x[0]):
        _MAP[opcode] = instruction

    del globals()["_init"]
    del _OPCODES


_init()
