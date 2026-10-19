from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from astropy.time import Time
import time
import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
import astropy.units as u
from astropy.time import Time, TimeDelta

try:
    import drms
    import sunpy
    import sunpy.map
    from sunpy.coordinates import frames

    SUNPY_available = True
except ImportError:
    SUNPY_available = False
import math
import matplotlib.pyplot as plt
from ASTRA.utils import custom_exceptions

configs = {
    "SDO_DOWNLOAD_REPEAT_INTEVAL": 5,
    "SDO_FITS_NAME": "hmi.ic_nolimbdark_720s_nrt.{}_TAI.3.continuum.fits",
    "SDO_FITS_QUERY": "hmi.ic_nolimbdark_720s_nrt[{}_TAI/{}]{{continuum}}",
    "SDO_SERVER_NAME": "JSOC",
    "JSOC_EMAIL_ADDRESS": "Andre.Silva@astro.up.pt",
    "SDO_NUMBER_DOWNLOAD_REPEATS": 50,
}
plt.style.use("default")
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.size"] = 12  # Slightly smaller font for A&A
plt.rcParams["axes.labelsize"] = 10
plt.rcParams["axes.titlesize"] = 11
plt.rcParams["xtick.labelsize"] = 10
plt.rcParams["ytick.labelsize"] = 10
plt.rcParams["legend.fontsize"] = 10
plt.rcParams["figure.titlesize"] = 12
plt.rcParams["lines.linewidth"] = 1  # Thinner lines for A&A
plt.rcParams["axes.linewidth"] = 1  # Thinner axes lines

single_column_width = 85 / 25.4  # ~3.35 inches
double_column_width = 175 / 25.4  # ~6.89 inches
height = single_column_width * 0.8  # Adjust height for a reasonable aspect ratio


def download_from_SDO(  # pylint: disable=invalid-name
    export_request: "drms.ExportRequest",
    image_name: str,
    storage_location: Path,
) -> bool:
    """Base interface to download an image from SDO.

    Creates an export request on JSOC servers, and downloads the latest image that was returned.
    If the image already exists on disk, the download does not proceed

    Args:
        export_request (drms.ExportRequest): export request to use for the download
        image_index (int): index of the desired file in the request
        configs (ConfigHolder): _description_
        storage_location (Path): Disk location of the stored images

    Returns:
        bool: returns true if it succeeds or false otherwise

    Notes/References:
        - Documentation for the drms download can be found in
         [here](https://docs.sunpy.org/projects/drms/en/stable/tutorial.html#url-quick-as-is)

        - Description of the SDO data products: http://jsoc.stanford.edu/HMI/Continuum.html

        - The email must be registered in [JSOC](http://jsoc.stanford.edu/ajax/register_email.html)

        - This functions will retrieve the information from the SDO_SERVER_NAME that
    is specified in the configs.

    """

    if not SUNPY_available:
        raise custom_exceptions.InternalError("Sunpy is not installed")

    server_name = configs["SDO_SERVER_NAME"]
    if server_name == "JSOC":
        return _JSOC_download_from_SDO(
            export_request=export_request,
            image_name=image_name,
            storage_location=storage_location,
        )
    logger.critical("Can't recognize the server name (%s)", server_name)
    return False


def construct_JSOC_SDO_query_string(  # pylint: disable=invalid-name
    date: Time,
    time_range: timedelta,
) -> str:
    """Construct the SDO query for a given date, image identifier and time range

    Args:
        date (Time): Date at which we want to start our "search"
        image_identifier (str): SDO image idenfitifer.
        time_range (timedelta): Time range for the search (will search all
            available fits between date and date + time_range)

    Returns:
        str: Query string to pass into SDO functions
    """
    image_identifier: str = configs.get("SDO_FITS_QUERY", "")
    return image_identifier.format(
        date.strftime("%Y.%m.%d_%H:%M:%S"), str(time_range.seconds) + "s"
    )


def _JSOC_get_OBS_list_from_SDO(  # pylint: disable=invalid-name
    since: datetime,
    up_to: datetime = datetime.now(tz=ZoneInfo("UTC")),
    JSOC_EMAIL_ADDRESS: str = None,
) -> tuple[Optional[list[str]], Optional[drms.ExportRequest]]:
    """Get the observations list from JSOC servers"""

    jsoc_email = JSOC_EMAIL_ADDRESS

    client = drms.Client(email=jsoc_email)
    time_range = up_to - since
    query_string = construct_JSOC_SDO_query_string(since, time_range.to_datetime())
    export_request = client.export(query_string, method="url", protocol="fits")
    # This is is blocking call....
    iterations = 0
    MAX_ITERATIONS = configs.get("SDO_NUMBER_DOWNLOAD_REPEATS", "")
    while iterations <= MAX_ITERATIONS:
        try:
            # THis might be taking a wee bit too long... we might need to find a better wayº
            # to check if we have a new nrt image available on the server...
            export_request.wait(sleep=configs.get("SDO_DOWNLOAD_REPEAT_INTEVAL", 1))
            break
        except drms.exceptions.DrmsExportError as e:
            msg = f"DRMs export failed, retrying ({iterations} / {MAX_ITERATIONS})"
            print(msg)
            time.sleep(configs.get("SDO_DOWNLOAD_REPEAT_INTEVAL", ""))
            iterations += 1
    else:
        msg = "Multiple calls to the DRMS export whilst first is yet to be processed"
        logger.critical(msg)
        return None, None

    return export_request.data["filename"], export_request


def _JSOC_download_from_SDO(  # pylint: disable=invalid-name
    export_request: "drms.ExportRequest",
    image_name: str,
    storage_location: Path,
) -> bool:
    """Access the SDO images from JSOC servers"""

    image_index = list(export_request.data["filename"]).index(image_name)

    if image_index == -1:
        # Convert to an index that the drms library recognizes
        n_obs = export_request.data.shape[0] - 1
    else:
        n_obs = image_index

    desired_filename = export_request.data["filename"].iloc[n_obs]

    if not desired_filename:
        msg = "No data found on the SDO export"
        logger.critical(msg)
        return False

    final_filename = storage_location / desired_filename
    if final_filename.exists():
        return final_filename

    # TODO: check if we can avoid download to disk
    iterations = 0
    MAX_ITERATIONS = configs.get("SDO_NUMBER_DOWNLOAD_REPEATS", "")
    while iterations <= MAX_ITERATIONS:
        try:
            download_results = export_request.download(
                storage_location, fname_from_rec=False, index=n_obs
            )
            break
        except drms.exceptions.DrmsExportError:
            msg = f"DRMs export failed, retrying ({iterations} / {MAX_ITERATIONS})"
            print(msg)

        # Wait a bit before retrying the download
        time.sleep(configs.get("SDO_DOWNLOAD_REPEAT_INTEVAL"))
        iterations += 1
    else:
        # We couldn't break the loop before the maximum number of iterations was reached
        msg = "The download of SDO image has failed"
        print(msg)
        return False

    if download_results["download"].size == 0:
        msg = "The download of SDO image has failed"
        print(msg)
    else:
        final_filename = Path(download_results["download"].iloc[0])

        filestem = final_filename.stem

        if "hmi.ic_nolimbdark_720s_nrt" not in filestem or "TAI" not in filestem:
            msg = (
                "The SDO image does not seem to have the expected filename."
                "Not adding it to the database"
            )
            print(msg)
        return final_filename


def plot_sdo_with_multiple_crosses(
    fits_file: str | Path,
    tx_arcsec_list: list[float],
    ty_arcsec_list: list[float],
    zoom_center_tx: float,
    zoom_center_ty: float,
    plot_options: dict[str, str],
    zoom_width: u.Quantity = 300 * u.arcsec,
    zoom_height: u.Quantity = 300 * u.arcsec,
    zoom_map=None,
    fig=None,
    ax=None,
):
    sdo_map = sunpy.map.Map(fits_file)

    zoom_center = SkyCoord(
        Tx=zoom_center_tx * u.arcsec,
        Ty=zoom_center_ty * u.arcsec,
        frame=sdo_map.coordinate_frame,
    )

    bottom_left = SkyCoord(
        Tx=zoom_center.Tx - zoom_width / 2,
        Ty=zoom_center.Ty - zoom_height / 2,
        frame=sdo_map.coordinate_frame,
    )

    top_right = SkyCoord(
        Tx=zoom_center.Tx + zoom_width / 2,
        Ty=zoom_center.Ty + zoom_height / 2,
        frame=sdo_map.coordinate_frame,
    )

    if zoom_map is None:
        zoom_map = sdo_map.submap(bottom_left, top_right=top_right)

        fig = plt.figure(figsize=(1.4 * single_column_width, 1.6 * height))
        ax = fig.add_subplot(projection=zoom_map)

        zoom_map.plot(
            axes=ax,
            cmap="copper",
            # clip_interval=(1, 99.8) * u.percent,
        )
        if zoom_center_ty < 0:
            ax.invert_yaxis()
        if zoom_center_tx > 0:
            ax.invert_xaxis()

    for tx, ty in zip(tx_arcsec_list, ty_arcsec_list):
        coord = SkyCoord(
            Tx=tx * u.arcsec,
            Ty=ty * u.arcsec,
            frame=sdo_map.coordinate_frame,
        ).transform_to(zoom_map.coordinate_frame)

        ax.plot_coord(coord, **plot_options)

    return zoom_map, fig, ax
