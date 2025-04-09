"""Represent state within ASTRA.

The Flag class is the most fundamental state within ASTRA, that will represent:

1) Fatal errors that reject data
2) Warnings in the data that do not translate in their rejection
3) Everything is good with the data

By default, a large number of Flags is pre-defined
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class Flag:
    """Used to represent a "state" of operation. The majority of them represents failures and/or warnings."""

    __slots__ = (
        "name",
        "code",
        "description",
        "extra_info",
        "is_fatal",
        "is_warning",
        "is_good_flag",
    )

    def __init__(
        self,
        name: str,
        value: int | str,
        description: Optional[str] = None,
        fatal_flag: bool = True,
        is_warning: bool = False,
        is_good_flag: bool = False,
        extra_info: Optional[str] = None,
    ):
        """Instantiate a new flag.

        Args:
            name (str): Name of the flag
            value (int): Default (numerical) value of the flag
            description (Optional[str], optional): Description of the flag, used for disk outputs. Defaults to None.
            fatal_flag (bool, optional): if True, the flag rejects something. Defaults to True.
            is_warning (bool, optional): if True, the flag represents a non-rejection-worthy state. Defaults to False.
            is_good_flag (bool, optional): if True, it is a good flag. Defaults to False.
            extra_info (Optional[str], optional): Extra info of the flag. Defaults to None.

        """
        self.name = name
        self.code = value
        self.description = description
        self.extra_info = "" if extra_info is None else extra_info
        self.is_fatal = fatal_flag
        self.is_warning = is_warning
        self.is_good_flag = is_good_flag

    def __eq__(self, flag_2: Any) -> bool:
        """Check for equality between two flags (compares names, code and extra_info)."""
        if not isinstance(flag_2, Flag):
            return False
        return (self.name == flag_2.name) and (self.code == flag_2.code) and (self.extra_info == flag_2.extra_info)

    def add_extra_info(self, extra_info: str) -> None:
        """Overwrite the extra_info value with the new one."""
        self.extra_info = extra_info

    def __str__(self) -> str:  # noqa: D105
        return f"{self.name}" + min(1, len(self.extra_info)) * f": {self.extra_info}"

    def __repr__(self) -> str:  # noqa: D105
        return (
            f"Flag(name = {self.name}, "
            f"\n\tvalue = {self.code},"
            f"\n\tdescription= {self.description},"
            f"\n\tfatal_flag= {self.is_fatal},"
            f"\n\tis_warning = {self.is_warning},"
            f"\n\tis_good_flag = {self.is_good_flag}"
            f"\n\textra_info={self.extra_info}"
        )

    def __hash__(self) -> int:  # noqa: D105
        # Allow the Flag class to be hashable
        return hash(tuple((self.name, self.code, self.extra_info)))

    def __call__(self, message: str) -> Flag:
        """Construct a new flag with a new message passed as extra_info."""
        new_flag = Flag(
            name=self.name,
            value=self.code,
            description=self.description,
            fatal_flag=self.is_fatal,
            is_warning=self.is_warning,
            is_good_flag=self.is_good_flag,
        )
        new_flag.add_extra_info(message)
        return new_flag

    def to_json(self) -> Dict[str, Any]:
        """Convert the Flag to a json-compatible dict."""
        return dict(
            name=self.name,
            value=self.code,
            description=self.description,
            fatal_flag=self.is_fatal,
            is_warning=self.is_warning,
            is_good_flag=self.is_good_flag,
            extra_info=self.extra_info,
        )

    @classmethod
    def create_from_json(cls, json_info: Dict[str, Any]) -> Flag:
        """Create a new Flag object from a json representation.

        Parameters
        ----------
        json_info
            Json representation of the flag

        Returns
        -------
        flag:
            The new flag

        """
        return Flag(**json_info)


###########################################################
#
# General codes
#
###########################################################

INTERNAL_ERROR = Flag("INTERNAL_ERROR", "D")
SUCCESS = Flag("SUCCESS", 0, fatal_flag=False, is_good_flag=True)
DISK_LOADED_DATA = Flag("LOADED", 0, fatal_flag=False, is_good_flag=True)
SHUTDOWN = Flag("SHUTDOWN", "S")

MANDATORY_KW_FLAG = Flag("Mandatory KW", "MKW")
###########################################################
#
# Codes for the Frames
#
###########################################################

VALID = Flag("VALID", value="V", fatal_flag=False, is_good_flag=True)
WARNING = Flag("WARNING", value="W", fatal_flag=False, is_good_flag=False, is_warning=True)

SIGMA_CLIP_REJECTION = Flag("SIGMA CLIP", value="SC")
USER_BLOCKED = Flag("USER_BLOCKED", value="U")
FATAL_KW = Flag("FATAL_KW", value="F")
KW_WARNING = Flag("KW_WARNING", value="KW_W", is_warning=True, fatal_flag=False)

MISSING_FILE = Flag("MISS_FILE", value="M")
NO_VALID_ORDERS = Flag("NO_VALID_ORDERS", value="NO")

MISSING_EXTERNAL_DATA = Flag("MISS_EXTERNAL_LOAD", value="S")
MISSING_SHAQ_RVS = Flag("MISS_SHAQ_RV", value="S")
LOADING_EXTERNAL_DATA = Flag("LOADING_EXTERNAL", value="LS", fatal_flag=False)

CREATING_MODEL = Flag("CREATING MODEL", value="CM", fatal_flag=False)
FAILED_MODEL_CREATION = Flag("FAILED MODEL CREATION", value="FCM", fatal_flag=True)
###########################################################
#
# Codes for the RV routines to use
#
###########################################################

WORKER_OFF = Flag("WORKER_OFF", "O")
IDLE_WORKER = Flag("SUCCESS", "I")
ACTIVE_WORKER = Flag("SUCCESS", "A")

# Positive codes for problems with the orders
LOW_SNR = Flag("LOW_SNR", 5, "SNR under the user-set threshold")
MASSIVE_RV_PRIOR = Flag("MASSIVE_RV_PRIOR", 4, "Too little spectra left after accountinf for RV window")
BAD_TEMPLATE = Flag("BAD_TEMPLATE", 3, "Could not create stellar template for given order")
HIGH_CONTAMINATION = Flag("HIGH_CONTAMINATION", 2, "Too many points removed due to masks + tellurics")
ORDER_SKIP = Flag("ORDER_SKIP", 1, "Order was skipped")

# negative values for errors in the RV
WORKER_ERROR = Flag("WORKER_ERROR", -1)
CONVERGENCE_FAIL = Flag("CONVERGENCE_FAIL", -2)
MAX_ITER = Flag("MAX ITERATIONS", -3)

###########################################################
#
# Codes for removal of points from the masks  -> uint16 is the max size for the status codes !!!!!!!!!
#
###########################################################

QUAL_DATA = Flag("QUAL_DATA", 1, " Qual data different than zero")  # qual data different than zero
ERROR_THRESHOLD = Flag(
    "ERROR_THRESHOLD",
    2,
    "Error over specified threshold",
)  # error threshold over the selected threshold
INTERPOLATION = Flag("INTERPOLATION", 4, "Removed due to interpolation")  # removed due to interpolation constraints
TELLURIC = Flag("TELLURIC", 8, "Telluric feature")  # classified as telluric feature,
MISSING_DATA = Flag("MISSING_DATA", 16, "Missing spectral data in the pixel")  # data is missing in the given points,
SPECTRAL_MISMATCH = Flag(
    "SPECTRAL_MISMATCH",
    32,
    "Removed due to outlier routine",
)  # mismatch between the template and the spectra
SATURATION = Flag("SATURATION", 64, "Saturated Pixel")  # Saturation of the detector; Only used by HARPS
NAN_DATA = Flag("NaN_Pixel", 128, "Nan Value")
ACTIVITY_LINE = Flag("ACTIVITY_INDICATOR", 256)  # this spectral regions belongs to a marked line

NON_COMMON_WAVELENGTH = Flag("NON_COMMON_WAVELENGTH", 512)  # this spectral regions belongs to a marked line
MULTIPLE_REASONS = Flag("MULTIPLE", 100)  # flagged by more than one reason
