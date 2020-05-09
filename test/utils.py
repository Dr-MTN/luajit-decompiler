import sys
from enum import Enum


def sgr(code: str) -> str:
    return "\x1b[%sm" % code


class Colour(Enum):
    BLACK = 0
    RED = 1
    HARD_RED = 9
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    WHITE = 7

    def fg(self):
        return "38;5;%d" % self.value

    def bg(self):
        return "48;5;%d" % self.value

    def set_fg(self):
        Colour._sgr(self.fg())

    def set_bg(self):
        Colour._sgr(self.bg())

    def print(self, text):
        self.write(text + "\n")

    def write(self, text):
        self.set_fg()
        sys.stdout.write(text)
        Colour.reset()

    @staticmethod
    def reset():
        Colour._sgr("")

    @staticmethod
    def _sgr(code):
        sys.stdout.write(sgr(code))
