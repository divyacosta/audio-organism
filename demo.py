"""The audio source of VIS_SILENT=1: the program hears nothing, like a computer with no music playing. For tests and pictures of the first screen."""
import numpy as np


class Silence:
    def chunk(self, n):
        return np.zeros(n, dtype=np.float32)
