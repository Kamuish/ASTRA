"""Test the construction of the stellar template."""

import os
from pathlib import Path

import pytest

from ASTRA.data_objects import DataClassManager
from ASTRA.Instruments import instrument_dict as instrument_name_map
from ASTRA.Quality_Control.activity_indicators import Indicators
from ASTRA.template_creation.StellarModel import StellarModel
from ASTRA.template_creation.TelluricModel import TelluricModel
from ASTRA.utils.create_logger import setup_ASTRA_logger
from ASTRA.utils.custom_exceptions import InvalidConfiguration
from ASTRA.utils.spectral_conditions import Empty_condition


@pytest.mark.slow
def test_template_construction() -> None:
    """Test construction of stellar template."""
    user_conf = {"STELLAR_TEMPLATE_CONFIGS": {"OVERSAMPLE_TEMPLATE": 1}}
    input_fpath = list(Path("/home/amiguel/spectra_collection/ESPRESSO/proxima").glob("*S2D_A.fits"))
    instrument_name = "ESPRESSO"
    user_configs = user_conf
    storage_path = Path(__file__).parent.parent / "tmp"
    skip_telluric_mask = True

    instrument = instrument_name_map[instrument_name]

    instrument_configs = user_configs.get("INSTRUMENT_CONFIGS", {})
    log_path = os.path.join(storage_path, "logs")

    setup_ASTRA_logger(storage_path=log_path, log_to_terminal=True)

    manager = DataClassManager()
    manager.start()

    data = manager.DataClass(
        input_fpath,
        storage_path=storage_path,
        instrument=instrument,
        instrument_options=instrument_configs,
        sigma_clip_RVs=user_configs.get("SIGMA_CLIP_RV", None),
    )

    if "REJECT_OBS" in user_configs:
        data.reject_observations(user_configs["REJECT_OBS"])

    data.generate_root_path(storage_path)

    interpol_properties = user_configs.get("INTERPOL_CONFIG_TEMPLATE", {})
    data.update_interpol_properties_of_all_frames(interpol_properties)

    inds = Indicators()
    data.remove_activity_lines(inds)

    telluric_model_configs = user_configs.get("TELLURIC_MODEL_CONFIGS", {})
    telluric_template_configs = user_configs.get("TELLURIC_TEMPLATE_CONFIGS", {})

    if not skip_telluric_mask:
        ModelTell = TelluricModel(
            usage_mode="individual",
            user_configs=telluric_model_configs,
            root_folder_path=storage_path,
        )

        ModelTell.Generate_Model(
            dataClass=data,
            telluric_configs=telluric_template_configs,
            force_computation=True,
            store_templates=True,
        )
        data.remove_telluric_features(ModelTell)

    stellar_model_configs = user_configs.get("STELLAR_MODEL_CONFIGS", {})
    stellar_template_configs = user_configs.get("STELLAR_TEMPLATE_CONFIGS", {})

    ModelStell = StellarModel(
        user_configs=stellar_model_configs,
        root_folder_path=storage_path,
    )
    try:
        StellarTemplateConditions = user_configs["StellarTemplateConditions"]
    except KeyError:
        StellarTemplateConditions = Empty_condition()

    try:
        ModelStell.Generate_Model(
            data,
            stellar_template_configs,
            StellarTemplateConditions,
            force_computation=True,
        )
        ModelStell.store_templates_to_disk()
    except InvalidConfiguration:
        return
    data.ingest_StellarModel(ModelStell)

    # Ensure that we can properly load them from disk
    ModelStell = StellarModel(
        user_configs=stellar_model_configs,
        root_folder_path=storage_path,
    )
    ModelStell.Generate_Model(
        data,
        stellar_template_configs,
        StellarTemplateConditions,
        force_computation=False,
    )
