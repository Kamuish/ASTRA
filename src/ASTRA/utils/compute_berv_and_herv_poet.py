"""
Compute BERV (Barycentric-Earth RV) and HERV (HEliocentric RV) correction.
"""

import astropy.constants as ac
from astropy.io import fits
from astropy.time import Time
import barycorrpy
from glob import glob
import matplotlib.pyplot as plt
import numpy as np

from ASTRA.utils.units import kilometer_second
from ASTRA.utils.ASTRAtypes import RV_measurement
from ASTRA.utils import custom_exceptions


# Compute BERV and HERV
def compute_berv_and_herv_POET(header) -> tuple[RV_measurement, RV_measurement]:
    """Compute barycentric and heliocentric correction for Paranal Observatory"""

    obsname = "Paranal Observatory"
    # Loop observations
    date_obs = header["DATE-OBS"]
    exp_time = header["EXPTIME"]
    photocen = header["HIERARCH ESO QC TMMEAN USED"]
    time_jdb = header["HIERARCH ESO QC BJD"]

    # Compute gravitational redshift of the Sun
    gr_sun = (ac.G.value * ac.M_sun.value) / (ac.R_sun.value * ac.c.value)

    # Compute BERV and HERV
    jd_utc_cen = Time(date_obs, format="isot").jd + exp_time * photocen / (60 * 60 * 24)
    berv_val = barycorrpy.get_BC_vel(
        JDUTC=jd_utc_cen, obsname=obsname, SolSystemTarget="Sun"
    )[0][0]

    herv_val = (
        barycorrpy.get_BC_vel(
            JDUTC=jd_utc_cen,
            obsname=obsname,
            SolSystemTarget="Sun",
            predictive=True,
        )[0][0]
        * (-1)
        - berv_val
        + gr_sun
    )

    # Convert from m/s to km/s
    berv_val *= 1e-3
    herv_val *= 1e-3

    if not np.isfinite((berv_val + herv_val)):
        raise custom_exceptions.InternalError(
            f"Got non-finite values for the BERV calculation ({berv_val=}; {herv_val=})"
        )

    return berv_val * kilometer_second, herv_val * kilometer_second
