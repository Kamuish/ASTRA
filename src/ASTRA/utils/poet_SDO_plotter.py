import math
from datetime import datetime
from pathlib import Path
from typing import Any

import astropy.units as u
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.io import fits
from astropy.time import Time, TimeDelta

from ASTRA import astra_logger as logger
from ASTRA.data_objects import DataClass
from ASTRA.utils import custom_exceptions

SUNPY_available = False
try:
    import sunpy
    from sunpy.coordinates import frames

    from ASTRA.utils.handle_SDO_image import (
        _JSOC_get_OBS_list_from_SDO,
        download_from_SDO,
        plot_sdo_with_multiple_crosses,
    )

    SUNPY_available = True
except ImportError:
    ...


def plot_SDO_image(
    d: DataClass,
    include_fine_point_offset: bool,
    storage_location: Path,
    JSOC_EMAIL_ADDRESS: str,
    zoom_in=False,
    label_map: dict[str, str] | None = None,
    legend_options: dict[str, Any] | None = None,
):
    """Make plot of the pointing positions on SDO image

    Parameters
    ----------
    d : DataClass
        DataClass object
    include_fine_point_offset : bool
        Include into the final coordinates the fine-pointing offsets (from the MCS)
    storage_location : Path
        Folder to store the image (pointing_locations.png)
    zoom_in : bool, optional
        If True, zooms the plot to a region close to the pointing position, by default False
    label_map: dict[str,str], optional
        If not None, dictionary to connect PoET OB names to a legend label

    Raises
    ------
    custom_exceptions.InternalError
        If Sunpy is not installed
    """
    if not SUNPY_available:
        raise custom_exceptions.InternalError("Missing SUNPY imports")

    poet_loc = EarthLocation.from_geodetic(-70.404375, -24.627672222222223, 2635.43)
    ob_times = []
    Tx, Ty = [], []
    coord_locs = {}

    for subInst in d.get_subInstruments_with_valid_frames():
        logger.debug("Processing subInstrument: " + subInst)
        coord_locs[subInst] = {"Tx": [], "Ty": []}
        frameIDs = d.get_frameIDs_from_subInst(subInst)
        ref_frame = d.get_frame_by_ID(frameIDs[0])

        delay_in_secs = 7.08  # Add or subtract a time delay in seconds
        DateTime = ref_frame.get_KW_value("ISO-DATE")
        hr = DateTime[11:13]
        minu = DateTime[14:16]
        secs = DateTime[17:]
        time_decimal = (
            float(hr)
            + float(minu) / 60.0
            + float(secs) / 3600.0
            + delay_in_secs / 3600.0
        )
        nhr = math.floor(time_decimal)
        nmin = math.floor(((time_decimal - nhr) * 60.0))
        nsecs = (time_decimal - nhr) * 3600.0 - nmin * 60.0
        ob_time = Time(DateTime[:11] + str(nhr) + ":" + str(nmin) + ":" + str(nsecs))

        ob_times.append(ob_time)

        # Altitude delta from fine pointing
        Alt_offset = ref_frame.get_KW_value("ALT_OFF")
        Az_offset = ref_frame.get_KW_value("AZ_OFF")

        # Tx of target before fine pointing
        Tx_target = ref_frame.get_KW_value("TX")
        # Ty of target before fine pointing
        Ty_target = ref_frame.get_KW_value("TY")

        # Convert Tx and Ty to actual ALT/Az
        pointing_coords = SkyCoord(
            Tx_target,
            Ty_target,
            observer="earth",
            obstime=ob_time,
            frame=frames.Helioprojective,
        )

        local_frame = AltAz(
            obstime=ob_time,
            location=poet_loc,
        )

        # Compute distance between observer and Sun
        sun_altaz = pointing_coords.transform_to(local_frame)

        # Add dynamic offsets
        point_alt = sun_altaz.alt
        point_az = sun_altaz.az

        if include_fine_point_offset:
            # This will include the fine-pointing offsets in the final coordinates
            # This will not give the true pointing coordinates for dates between XX and YY
            logger.debug(
                f"Add fine point offsets to the pointing coordinates {Alt_offset}, {Az_offset}"
            )

            point_alt = point_alt + float(Alt_offset) * u.deg
            point_az = point_az + float(Az_offset) * u.deg

        skycoord = SkyCoord(
            az=point_az,
            alt=point_alt,
            distance=sunpy.coordinates.sun.earth_distance(ob_time),
            frame=AltAz(
                obstime=ob_time,
                location=poet_loc,
            ),
        )

        hpc = skycoord.transform_to(
            frames.Helioprojective(
                observer="earth",
            )
        )

        coord_locs[subInst]["Tx"].append(hpc.Tx.to(u.arcsec).value)
        coord_locs[subInst]["Ty"].append(hpc.Ty.to(u.arcsec).value)

    date_to_get_image = min(ob_times)

    hmi_files = list(storage_location.glob("hmi.ic_no*"))
    if not hmi_files:
        filenames, export = _JSOC_get_OBS_list_from_SDO(
            since=date_to_get_image - TimeDelta(1000, format="sec"),
            up_to=(date_to_get_image + TimeDelta(1000, format="sec")),
            JSOC_EMAIL_ADDRESS=JSOC_EMAIL_ADDRESS,
        )

        SDO_fname = download_from_SDO(
            export_request=export,
            image_name=filenames.iloc[-1],
            storage_location=storage_location,
        )
    else:
        SDO_fname = hmi_files[0]

    zoom_map = None
    fig = None
    ax = None

    found = False

    for key in coord_locs:
        if "_umbra" in key:
            center_tx = coord_locs[key]["Tx"][0]
            center_ty = coord_locs[key]["Ty"][0]
            found = True
    all_Tx = list(i["Tx"] for i in coord_locs.values())
    all_Ty = list(i["Ty"] for i in coord_locs.values())

    if not found:
        center_tx = np.median(all_Tx)
        center_ty = np.median(all_Ty)

    cmap = plt.get_cmap("Set1")
    if zoom_in:
        width = max(1.5 * (np.max(all_Tx) - np.min(all_Tx)), 210)
        height = max(1.5 * (np.max(all_Ty) - np.min(all_Ty)), 210)
    else:
        center_tx = 0
        center_ty = 0
        width = 40 * 60
        height = 40 * 60

    for index, stem in enumerate(coord_locs):

        label = label_map.get(stem, stem) if label_map is not None else stem
        zoom_map, fig, ax = plot_sdo_with_multiple_crosses(
            fits_file=SDO_fname,
            tx_arcsec_list=coord_locs[stem]["Tx"],
            ty_arcsec_list=coord_locs[stem]["Ty"],
            zoom_center_tx=center_tx,
            zoom_center_ty=center_ty,
            zoom_width=width * u.arcsec,
            zoom_height=height * u.arcsec,
            plot_options={
                "label": label,
                "marker": "x",
                "color": cmap(index / len(coord_locs)),
                "markersize": 6,
                "markeredgewidth": 2.2,
                "linestyle": "None",
            },
            zoom_map=zoom_map,
            fig=fig,
            ax=ax,
        )

    from matplotlib.lines import Line2D

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.2)
    if legend_options is None:
        legend_options = {
        "ncol": 2,
        "loc": 4,
        "bbox_to_anchor": (1.05, -0.27),
        }

    ax.legend(**legend_options)

    fig.savefig(storage_location / "pointing_locations.png")
