from pathlib import Path

import pytest

from ASTRA.data_objects.DataClass import DataClass
from ASTRA.Instruments import ESPRESSO
from ASTRA.Quality_Control.activity_indicators import Indicators
from ASTRA.template_creation.StellarModel import StellarModel


@pytest.mark.slow
def teste_core(tmp_path):
    """Ensure that we can create the stellar template."""
    test_dir = Path(__file__).parent
    mock_file = test_dir / "mock_data"

    d = DataClass(
        list(mock_file.glob("*.fits")),
        storage_path=tmp_path,
        instrument=ESPRESSO,
    )

    inds = Indicators()
    d.remove_activity_lines(inds)

    stell = StellarModel(
        tmp_path,
        user_configs={},
    )
    stell.Generate_Model(
        dataClass=d,
        template_configs={},
    )
