from test.utils import Colour
from typing import List


class Config:
    # Extra arguments that should be passed to the decompiler
    ljd_args: List[str]

    def __init__(self):
        self.verbose = False
        self.ljd_args = []

    def log(self, text):
        if self.verbose:
            Colour.YELLOW.print(text)
