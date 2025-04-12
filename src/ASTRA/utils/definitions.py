"""Enums that are used to define different properties."""

from enum import Enum, auto


class DETECTOR_DEFINITION(Enum):
    """Represent the cromatic intervals (full spectra, red and blue det.)."""

    WHITE_LIGHT = auto()
    RED_DET = auto()
    BLUE_DET = auto()
