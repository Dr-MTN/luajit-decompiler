from test.testunit import Mode, Test

tests = [
    # Very trivial testcases, more for testing the test framework than the decompiler
    Test("simple", Mode.MATCHES),
    Test("loops", Mode.MATCHES),
    Test("massive_nils", Mode.MATCHES),
    Test("massive_std", Mode.MATCHES),
    Test("illegal_type_eliminations", Mode.MATCHES),
    Test("slot_local_declarations", Mode.MATCHES),
    Test("slot_block_gathering", Mode.MATCHES),
    Test("arguments", Mode.MATCHES),
    Test("complex_expressions", Mode.MATCHES),
    Test("upvalues", Mode.MATCHES),
    Test("weird_bytecode_expression", Mode.MATCHES),  # It's probably okay to bump this down to DECOMPILES temporarily

    # The old (pre test framework) tests
    Test("old/breaks", Mode.MATCHES),
    Test("old/expression", Mode.MATCHES),
    Test("old/ifs", Mode.MATCHES),
    Test("old/loop", Mode.MATCHES),
    Test("old/operations", Mode.MATCHES),
    Test("old/primitive", Mode.MATCHES),
]
