from typing import Union

import numpy as np

from ASTRA import astra_logger as logger
from ASTRA.status.Mask_class import Mask
from ASTRA.utils import custom_exceptions
from ASTRA.utils.parameter_validators import NumericValue, ValueFromIterable
from ASTRA.utils.UserConfigs import DefaultValues, UserParam

from .Stellar_Template import StellarTemplate


class OBS_Stellar(StellarTemplate):
    """Stellar template from the observation with the highest SNR (computed as a sum over all spectral orders)."""

    method_name = "OBSERVATION"
    _default_params = StellarTemplate._default_params + DefaultValues(
        ALIGNEMENT_RV_SOURCE=UserParam("DRS", constraint=ValueFromIterable(["DRS", "SBART"])),
    )

    _default_params.update(
        "MINIMUM_NUMBER_OBS",
        UserParam(1, constraint=NumericValue, mandatory=False),
    )

    def __init__(self, subInst: str, user_configs: Union[None, dict] = None, loaded: bool = False):
        super().__init__(subInst=subInst, user_configs=user_configs, loaded=loaded)
        self._selected_frameID = None
        self._found_error = False

    @custom_exceptions.ensure_invalid_template
    def create_stellar_template(self, dataClass, conditions=None) -> None:
        """Create the stellar template."""
        # removal may change the first common wavelength; make sure

        try:
            super().create_stellar_template(dataClass, conditions)
        except custom_exceptions.StopComputationError:
            return

        logger.info("Searching for frameID with highest sum of orderwise SNRs")
        total_SNR = []
        for frameID in self.frameIDs_to_use:
            total_SNR.append(np.nansum(dataClass.get_KW_from_frameID(KW="orderwise_SNRs", frameID=frameID)))

        self._selected_frameID = self.frameIDs_to_use[np.argmax(total_SNR)]
        logger.info("Selected frameID={}", self._selected_frameID)
        wavelenghts, spectra, uncertainties, mask = dataClass.get_frame_arrays_by_ID(self._selected_frameID)

        if self._internal_configs["OVERSAMPLE_TEMPLATE"] > 1:
            raise custom_exceptions.InternalError("OBS stellar does not yet support oversampling")
            # new_wave = np.linspace(
            #     wave_order[0],
            #     wave_order[-1],
            #     wavelenghts.shape[1] * self._internal_configs["OVERSAMPLE_TEMPLATE"],
            # )
            # self.wavelengths[order_index] = new_wave

        else:
            self.wavelengths = wavelenghts
            self.spectra = spectra
            self.uncertainties = uncertainties

        self.spectral_mask = Mask(mask, mask_type="binary")

        instrument_information = dataClass.get_instrument_information()
        epoch_shape = instrument_information["array_size"]
        self.rejection_array = np.zeros((1, epoch_shape[0]))

        self._finish_template_creation()
