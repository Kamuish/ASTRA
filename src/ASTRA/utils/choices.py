"""Defines that availabe choices of ASTRA."""

from enum import Enum


class WORKING_MODE(Enum):
    """Enumerator to represent the working mode of the ASRA object.

    ONE_SHOT - All observations are processed at the same time

    """

    ONE_SHOT = "ONE_SHOT"


class DISK_SAVE_MODE(Enum):
    """Enumerator to represent the DISK save mode of a given ASTRA object."""

    DISABLED = 1

    BASIC = 2

    EXTREME = 3


class TELLURIC_EXTENSION(Enum):
    """Method for the extension of telluric template."""

    LINES = "LINES"
    WINDOW = "WINDOW"


class TELLURIC_CREATION_MODE(Enum):
    """Method for the construction of telluric template."""

    tapas = "tapas"
    telfit = "telfit"
    OHemission = "OHemission"


class STELLAR_CREATION_MODE(Enum):
    """Method for the construction of stellar template."""

    Sum = "Sum"
    OBSERVATION = "OBSERVATION"
    Median = "Median"
    PHOENIX = "PHOENIX"


class TELLURIC_APPLICATION_MODE(Enum):
    """Approach to handle telluric features."""

    removal = "removal"
    correction = "correction"


class SPECTRA_INTERPOL_MODE(Enum):
    """Enumerator to represent the DISK save mode of a given ASTRA object."""

    SPLINES = 1
    GP = 2


class SPLINE_INTERPOL_MODE(Enum):
    """Enumerator to represent the interpolation mode of a given ASTRA object.

    Possible values:
        CUBIC_SPLINE
        QUADRATIC_SPLINE
        PCHIP
        NEAREST
        RBF
        SMOOTH_CUBIC_SPLINE
        AKIMA
        BARYCENTRIC_INTERPOL
    """

    CUBIC_SPLINE = 1
    QUADRATIC_SPLINE = 2
    PCHIP = 3
    NEAREST = 4
    RBF = 5
    SMOOTH_CUBIC_SPLINE = 6
    AKIMA = 7
    BARYCENTRIC_INTERPOL = 8


class FLUX_SMOOTH_CONFIGS(Enum):
    """Enumerator to flux smoothing applied at template construction."""

    NONE = 1
    SAVGOL = 2


class FLUX_SMOOTH_ORDER(Enum):
    """The order in which the smooth is applied."""

    BEFORE = 1
    AFTER = 2
    BOTH = 3


class INTERPOLATION_ERR_PROP(Enum):
    """how should we propagate uncertainties."""

    interpolation = 1
    propagation = 2
    none = 3


class NORMALIZATION_SOURCES(Enum):
    """how should we propagate uncertainties."""

    RASSINE = "RASSINE"
    SNT = "SNT"
    POLY_FIT = "POLY_FIT"
