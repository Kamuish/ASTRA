from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from astropy.io import fits

from ASTRA.utils import choices, custom_exceptions
from ASTRA.utils.parameter_validators import ValueFromDtype
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)

from .Telluric_Template import TelluricTemplate

if TYPE_CHECKING:
    from ASTRA.data_objects.DataClass import DataClass
    from ASTRA.utils.ASTRAtypes import UI_DICT

RESOURCES_PATH = Path(__file__).parent.parent.parent / "resources"


class OHemissionTelluric(TelluricTemplate):
    """Telluric mask for OH emission lines."""

    _default_params = TelluricTemplate._default_params + DefaultValues(
        SKYcalcPath=UserParam(
            default_value=None,
            constraint=ValueFromDtype((str, Path, type(None))),
            description=("Path to a fits file provided from ESO's skycalc tool for the correct MJD"),
        ),
    )

    method_name = choices.TELLURIC_CREATION_MODE.OHemission.value

    def __init__(
        self,
        subInst: str,
        user_configs: Optional[UI_DICT] = None,
        extension_mode: str = "lines",
        application_mode: str = "removal",
        loaded: bool = False,
    ):
        super().__init__(
            subInst=subInst,
            extension_mode=extension_mode,
            user_configs=user_configs,
            loaded=loaded,
            application_mode=application_mode,
        )

    @custom_exceptions.ensure_invalid_template
    def create_telluric_template(self, dataClass: DataClass, custom_frameID: Optional[int] = None) -> None:
        """Create model for OH emission."""
        try:
            super().create_telluric_template(dataClass, custom_frameID=custom_frameID)
        except custom_exceptions.StopComputationError:
            return

        with fits.open(self._internal_configs["SKYcalcPath"]) as hdu:
            datable = hdu[1].data

        wavelengths, tell_spectra = datable["lam"], datable["flux"]

        template = np.zeros_like(tell_spectra)
        template[np.where(tell_spectra != 0)] = 1
        self.template = template

        # ! no median filtering (might still be needed in the future)
        self._continuum_level = 1.0
        self.wavelengths = wavelengths * 10  # convert to the prevalent wavelength units

        self.transmittance_wavelengths, self.transmittance_spectra = (
            wavelengths,
            tell_spectra,
        )

        self.build_blocks()
        self._compute_wave_blocks()
        self._finish_template_creation()

    def store_metrics(self):
        super().store_metrics()
