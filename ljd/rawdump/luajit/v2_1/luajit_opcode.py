#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import ljd.bytecode.instructions as instructions

_OPCODES = (
    # Comparison ops

    (0x00, instructions.ISLT),  # @UndefinedVariable
    (0x01, instructions.ISGE),  # @UndefinedVariable
    (0x02, instructions.ISLE),  # @UndefinedVariable
    (0x03, instructions.ISGT),  # @UndefinedVariable

    (0x04, instructions.ISEQV),  # @UndefinedVariable
    (0x05, instructions.ISNEV),  # @UndefinedVariable

    (0x06, instructions.ISEQS),  # @UndefinedVariable
    (0x07, instructions.ISNES),  # @UndefinedVariable

    (0x08, instructions.ISEQN),  # @UndefinedVariable
    (0x09, instructions.ISNEN),  # @UndefinedVariable

    (0x0A, instructions.ISEQP),  # @UndefinedVariable
    (0x0B, instructions.ISNEP),  # @UndefinedVariable

    # Unary test and copy ops

    (0x0C, instructions.ISTC),  # @UndefinedVariable
    (0x0D, instructions.ISFC),  # @UndefinedVariable

    (0x0E, instructions.IST),  # @UndefinedVariable
    (0x0F, instructions.ISF),  # @UndefinedVariable
    (0x10, instructions.ISTYPE),  # @UndefinedVariable
    (0x11, instructions.ISNUM),  # @UndefinedVariable

    # Unary ops

    (0x12, instructions.MOV),  # @UndefinedVariable
    (0x13, instructions.NOT),  # @UndefinedVariable
    (0x14, instructions.UNM),  # @UndefinedVariable
    (0x15, instructions.LEN),  # @UndefinedVariable

    # Binary ops

    (0x16, instructions.ADDVN),  # @UndefinedVariable
    (0x17, instructions.SUBVN),  # @UndefinedVariable
    (0x18, instructions.MULVN),  # @UndefinedVariable
    (0x19, instructions.DIVVN),  # @UndefinedVariable
    (0x1A, instructions.MODVN),  # @UndefinedVariable

    (0x1B, instructions.ADDNV),  # @UndefinedVariable
    (0x1C, instructions.SUBNV),  # @UndefinedVariable
    (0x1D, instructions.MULNV),  # @UndefinedVariable
    (0x1E, instructions.DIVNV),  # @UndefinedVariable
    (0x1F, instructions.MODNV),  # @UndefinedVariable

    (0x20, instructions.ADDVV),  # @UndefinedVariable
    (0x21, instructions.SUBVV),  # @UndefinedVariable
    (0x22, instructions.MULVV),  # @UndefinedVariable
    (0x23, instructions.DIVVV),  # @UndefinedVariable
    (0x24, instructions.MODVV),  # @UndefinedVariable

    (0x25, instructions.POW),  # @UndefinedVariable
    (0x26, instructions.CAT),  # @UndefinedVariable

    # Constant ops

    (0x27, instructions.KSTR),  # @UndefinedVariable
    (0x28, instructions.KCDATA),  # @UndefinedVariable
    (0x29, instructions.KSHORT),  # @UndefinedVariable
    (0x2A, instructions.KNUM),  # @UndefinedVariable
    (0x2B, instructions.KPRI),  # @UndefinedVariable

    (0x2C, instructions.KNIL),  # @UndefinedVariable

    # Upvalue and function ops

    (0x2D, instructions.UGET),  # @UndefinedVariable

    (0x2E, instructions.USETV),  # @UndefinedVariable
    (0x2F, instructions.USETS),  # @UndefinedVariable
    (0x30, instructions.USETN),  # @UndefinedVariable
    (0x31, instructions.USETP),  # @UndefinedVariable

    (0x32, instructions.UCLO),  # @UndefinedVariable

    (0x33, instructions.FNEW),  # @UndefinedVariable

    # Table ops

    (0x34, instructions.TNEW),  # @UndefinedVariable

    (0x35, instructions.TDUP),  # @UndefinedVariable

    (0x36, instructions.GGET),  # @UndefinedVariable
    (0x37, instructions.GSET),  # @UndefinedVariable

    (0x38, instructions.TGETV),  # @UndefinedVariable
    (0x39, instructions.TGETS),  # @UndefinedVariable
    (0x3A, instructions.TGETB),  # @UndefinedVariable
    (0x3B, instructions.TGETR),  # @UndefinedVariable

    (0x3C, instructions.TSETV),  # @UndefinedVariable
    (0x3D, instructions.TSETS),  # @UndefinedVariable
    (0x3E, instructions.TSETB),  # @UndefinedVariable

    (0x3F, instructions.TSETM),  # @UndefinedVariable
    (0x40, instructions.TSETR),  # @UndefinedVariable

    # Calls and vararg handling

    (0x41, instructions.CALLM),  # @UndefinedVariable
    (0x42, instructions.CALL),  # @UndefinedVariable
    (0x43, instructions.CALLMT),  # @UndefinedVariable
    (0x44, instructions.CALLT),  # @UndefinedVariable

    (0x45, instructions.ITERC),  # @UndefinedVariable
    (0x46, instructions.ITERN),  # @UndefinedVariable

    (0x47, instructions.VARG),  # @UndefinedVariable

    (0x48, instructions.ISNEXT),  # @UndefinedVariable

    # Returns

    (0x49, instructions.RETM),  # @UndefinedVariable
    (0x4A, instructions.RET),  # @UndefinedVariable
    (0x4B, instructions.RET0),  # @UndefinedVariable
    (0x4C, instructions.RET1),  # @UndefinedVariable

    # Loops and branches

    (0x4D, instructions.FORI),  # @UndefinedVariable
    (0x4E, instructions.JFORI),  # @UndefinedVariable

    (0x4F, instructions.FORL),  # @UndefinedVariable
    (0x50, instructions.IFORL),  # @UndefinedVariable
    (0x51, instructions.JFORL),  # @UndefinedVariable

    (0x52, instructions.ITERL),  # @UndefinedVariable
    (0x53, instructions.IITERL),  # @UndefinedVariable
    (0x54, instructions.JITERL),  # @UndefinedVariable

    (0x55, instructions.LOOP),  # @UndefinedVariable
    (0x56, instructions.ILOOP),  # @UndefinedVariable
    (0x57, instructions.JLOOP),  # @UndefinedVariable

    (0x58, instructions.JMP),  # @UndefinedVariable

    # Function headers

    (0x59, instructions.FUNCF),  # @UndefinedVariable
    (0x5A, instructions.IFUNCF),  # @UndefinedVariable
    (0x5B, instructions.JFUNCF),  # @UndefinedVariable

    (0x5C, instructions.FUNCV),  # @UndefinedVariable
    (0x5D, instructions.IFUNCV),  # @UndefinedVariable
    (0x5E, instructions.JFUNCV),  # @UndefinedVariable

    (0x5F, instructions.FUNCC),  # @UndefinedVariable
    (0x60, instructions.FUNCCW)  # @UndefinedVariable
)
