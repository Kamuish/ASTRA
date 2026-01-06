"""ASTRA - interface for spectra."""

version = "1.2.5"

__version__ = version.replace(".", "-")
__version_info__ = (int(i) for i in __version__.split("-"))

import multiprocessing as mp

from ASTRA.utils.create_logger import astra_logger, setup_ASTRA_logger

mp.set_start_method("spawn", force=True)
