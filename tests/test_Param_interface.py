import numpy as np
import pytest

from ASTRA.ModelParameters import Model, ModelComponent
from ASTRA.utils import custom_exceptions


def test_Model_component_init():
    comp = ModelComponent(
        name="teste",
        default_enabled=False,
    )

    assert comp.is_enabled is False
    assert comp.is_locked is False

    comp.enable_param()
    comp.lock_param()

    assert comp.is_enabled is True
    assert comp.is_locked is True

    for bounds_values in [[1, 2, 3], "a"]:
        with pytest.raises(custom_exceptions.InvalidConfiguration):
            _ = ModelComponent(name="teste", bounds=bounds_values)

    for bounds_values in [[1, 2], (2, 3), np.array([2, 2])]:
        _ = ModelComponent(name="teste", bounds=bounds_values)


def test_Model_component_prior_genesis():
    """
    Can't test the RV genesis on the RVparameter as we need to pass it a dataclass object to load info
    """
    comp = ModelComponent(name="teste", default_enabled=True, bounds=[1, 2])

    with pytest.raises(custom_exceptions.InvalidConfiguration):
        comp.generate_prior_from_frameID(0)

    comp = ModelComponent(name="teste", default_enabled=True, bounds=[1, 2], initial_guess=1)

    comp.generate_prior_from_frameID(1)

    for bad_val in [0, 3]:
        with pytest.raises(custom_exceptions.InvalidConfiguration):
            _ = ModelComponent(
                name="teste", default_enabled=True, bounds=[1, 2], initial_guess=bad_val
            ).generate_prior_from_frameID(0)


def test_Model_component_lock(): ...


def test_Model_grouping():
    comp_map = {"group_A": 2, "group_B": 3}
    param_list = []
    for name, number in comp_map.items():
        for i in range(number):
            param_list.append(ModelComponent(name=f"{name}_{i}", param_type=name))
    param_list.append(ModelComponent(name="teste"))

    mod = Model(param_list)

    for name, number in comp_map.items():
        assert len(mod.get_components_of_type(name, only_enabled=False)) == number

    mod.enable_param("group_A_0")
    assert len(mod.get_components_of_type("group_A", only_enabled=True)) == 1
