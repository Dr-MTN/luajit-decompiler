import sys
from enum import Enum


class Colour(Enum):
    BLACK = 0
    RED = 1
    HARD_RED = 9
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    WHITE = 7

    def set_fg(self):
        Colour._sgr("38;5;%d" % self.value)

    def set_bg(self):
        Colour._sgr("48;5;%d" % self.value)

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
        sys.stdout.write("\x1b[%sm" % code)
