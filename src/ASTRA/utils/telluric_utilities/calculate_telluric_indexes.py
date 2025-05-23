"""Compute telluric indexes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ASTRA.utils.create_spectral_blocks import build_blocks

if TYPE_CHECKING:
    from ASTRA.data_objects.DataClass import DataClass
    from ASTRA.template_creation.telluric_templates.Telluric_Template import TelluricTemplate


def calculate_telluric_mask(data_class: DataClass, telluric_temp: TelluricTemplate) -> np.ndarray:
    """Construct the telluric mask."""
    if telluric_temp is None:
        return None
    tell_template = telluric_temp.template
    tell_waves = telluric_temp.wavelengths

    spectra_wavelengths, _ = data_class.wavelengths

    new_mask = np.zeros(spectra_wavelengths.shape, dtype=bool)
    for epoch in range(data_class.number_of_epochs):
        for order in range(data_class.mat_size[0]):
            spectra_wave_order = spectra_wavelengths[epoch][order]
            temp_order = tell_template[order]
            ratios = np.zeros(temp_order.shape)

            telluric_blocks = build_blocks(np.where(temp_order == 1))

            for block in telluric_blocks:
                lower_wave = tell_waves[order][block[0]]
                higher_wave = tell_waves[order][block[-1]]

                ratios[
                    np.where(
                        np.logical_and(
                            spectra_wave_order >= lower_wave,
                            spectra_wave_order <= higher_wave,
                        ),
                    )
                ] = 1

            new_mask[epoch][order][np.where(ratios >= 0.5)] = True

    return new_mask
