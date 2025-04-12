"""Introduce extra functionalities in Classes.

A class that inherits from the Components will have new functionalities.

- Spectrum: Class will be able of storing spectral data (independently of format).
- Spectral_Modelling: Children will be able to model stellar spectra.
"""

from .SpectrumComponent import Spectrum
from .Spectral_Normalization import Spectral_Normalization
from .Modelling import Spectral_Modelling
