"""This sub-package implements the different methods that can be used to normalize stellar spectra"""

from ASTRA.utils.choices import NORMALIZATION_SOURCES

from .polynomial_normalization import Polynomial_normalization
from .RASSINE_normalization import RASSINE_normalization
from .SNT_normalization import SNT_normalization

available_normalization_interfaces = {
    NORMALIZATION_SOURCES.POLY_FIT: Polynomial_normalization,
    NORMALIZATION_SOURCES.RASSINE: RASSINE_normalization,
    NORMALIZATION_SOURCES.SNT: SNT_normalization,
}
