import subprocess
import sys
from enum import Enum
from pathlib import Path

from test.utils import Colour


class Mode(Enum):
    """The levels to which a test must pass"""

    PARTIAL_FAILURE = 1
    """The file decompiles with --catch_asserts - should only be used to test error handling"""

    DECOMPILES = 2
    """The file decompiles successfully, but no checks are made against the input"""

    MATCHES = 3
    """The file decompiles, and it's re-compiled output matches the original bytecode"""


class TestResult(Enum):
    PASS = 1
    FAIL = 2
    ERROR = 3


class Test:
    def __init__(self, name, level):
        self.name = name
        self.level = level
        self.src = Path("tests/%s.lua" % name)

        self.bc_out = None
        self.src_out = None
        self.bc_out_recompiled = None

        assert self.src.is_file()

    def test(self, config, tmpdir):
        # noinspection PyBroadException
        try:
            self._test_unsafe(config, tmpdir)
            return TestResult.PASS
        except subprocess.CalledProcessError:
            return TestResult.FAIL
        except Exception:
            if config.verbose:
                raise
            return TestResult.ERROR

    def _test_unsafe(self, config, tmpdir):
        # TODO handle Mode.PARTIAL_FAILURE
        self.compile(config, False, tmpdir)
        self.decompile(config)

        if self.level != Mode.MATCHES:
            return

        self.recompile(config)

        with open(self.bc_out, "rb") as fi:
            bc1 = fi.read()

        with open(self.bc_out_recompiled, "rb") as fi:
            bc2 = fi.read()

        assert bc1 == bc2

    def compile(self, config, symbols, tmpdir):
        self.bc_out = Path(tmpdir, self.name + ".bc")
        self.src_out = Path(tmpdir, self.name + ".lua")
        self.bc_out_recompiled = Path(tmpdir, self.name + "-rc.bc")
        config.log("Compiling " + self.name + " to " + str(self.bc_out))
        lj_compile(config, self.src, self.bc_out, symbols)

    def decompile(self, config):
        assert self.bc_out
        config.log("Decompiling " + self.name)
        lj_decompile(config, self.bc_out, self.src_out)

    def recompile(self, config):
        assert self.bc_out
        config.log("Recompiling " + self.name)
        lj_compile(config, self.src_out, self.bc_out_recompiled, False)


def lj_compile(config, input, output, symbols):
    args = ["luajit", "-b", "-t", "raw", str(input.resolve()), str(output.resolve())]
    if symbols:
        args[-1:-1] += ["-g"]
    cfg_run(config, args)


def lj_decompile(config, input, output):
    main_file = Path(sys.argv[0]).resolve().parent / "main.py"
    args = ["python3", str(main_file), "-f", str(input), "-o", str(output)]
    cfg_run(config, args)


def cfg_run(config, args):
    kwargs = {
        "args": args,
        "check": True,
    }

    if config.verbose:
        Colour.BLUE.set_fg()
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    subprocess.run(**kwargs)

    if config.verbose:
        Colour.reset()