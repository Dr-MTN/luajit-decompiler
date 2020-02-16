from test.testunit import Mode, Test

tests = [
    # Very trivial testcases, more for testing the test framework than the decompiler
    Test("simple", Mode.MATCHES),
    Test("loops", Mode.MATCHES),

    # The old (pre test framework) tests
    Test("old/breaks", Mode.MATCHES),
    Test("old/expression", Mode.MATCHES),
    Test("old/ifs", Mode.MATCHES),
    Test("old/loop", Mode.MATCHES),
    Test("old/operations", Mode.MATCHES),
    Test("old/primitive", Mode.MATCHES),
]
