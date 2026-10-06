"""
Tests for pyrs/utilities/NXstress/_sample.py
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
from nexusformat.nexus import NXcollection, NXentry, NXsample, nxopen
import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.dataobjects.constants import HidraConstants
from pyrs.utilities.NXstress._sample import _Sample
from pyrs.utilities.NXstress._definitions import FIELD_DTYPE


class TestSample:
    """Test suite for _sample.py"""

    def test_Sample_scan_point_and_coordinates(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify scan_point matches subruns and vx,vy,vz have correct shape/dtype"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        sample = _Sample.init_group([ws._sample_logs])

        assert isinstance(sample, NXsample)
        assert "scan_point" in sample
        assert "vx" in sample
        assert "vy" in sample
        assert "vz" in sample

        # Verify scan_point matches subruns
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)

        np.testing.assert_array_equal(sample["scan_point"].nxdata, subruns.astype(FIELD_DTYPE.INT_DATA.value))

        # Verify coordinate arrays have correct shape and dtype
        for coord in ["vx", "vy", "vz"]:
            assert sample[coord].shape == (N_scan,)
            assert sample[coord].dtype == FIELD_DTYPE.FLOAT_DATA.value

    def test_Sample_chemical_formula_present(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify chemical_formula field when CHEMICAL_FORMULA log is present"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Add chemical formula to logs - must match number of subruns
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        ws._sample_logs[HidraConstants.CHEMICAL_FORMULA] = ["Fe3O4"] * N_scan

        sample = _Sample.init_group([ws._sample_logs])

        assert "chemical_formula" in sample
        # _Sample takes the first value from the log
        assert sample["chemical_formula"] == "Fe3O4"

    def test_Sample_chemical_formula_absent(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify chemical_formula defaults to 'unknown' when not in logs"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Ensure chemical formula is not in logs
        if HidraConstants.CHEMICAL_FORMULA in ws._sample_logs:
            del ws._sample_logs[HidraConstants.CHEMICAL_FORMULA]

        sample = _Sample.init_group([ws._sample_logs])

        assert "chemical_formula" in sample
        assert sample["chemical_formula"] == "unknown"

    def test_Sample_temperature_present(self, minimal_HidraWorkspace: Callable[..., HidraWorkspace]):
        """Verify temperature field and units when TEMPERATURE log is present"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Add temperature data to logs with units using tuple syntax
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        temp_values = np.linspace(300, 400, N_scan)

        # Use tuple (key, units) to set value with units
        ws._sample_logs[(HidraConstants.TEMPERATURE, "K")] = temp_values

        sample = _Sample.init_group([ws._sample_logs])

        assert "temperature" in sample
        assert sample["temperature"].shape == (N_scan,)
        assert sample["temperature"].dtype == FIELD_DTYPE.FLOAT_DATA.value
        assert sample["temperature"].attrs["units"] == "K"

    def test_Sample_temperature_absent(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify no temperature field when TEMPERATURE log is absent"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Ensure temperature is not in logs
        if HidraConstants.TEMPERATURE in ws._sample_logs:
            del ws._sample_logs[HidraConstants.TEMPERATURE]

        sample = _Sample.init_group([ws._sample_logs])

        assert "temperature" not in sample

    def test_Sample_stress_field_present(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify stress_field field, shape, and direction attr when present"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Add stress field data to logs
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        # Local, freshly-seeded generator -- not the implicit global numpy RNG state, which is
        # shared process-wide and would couple this test's values to unrelated tests' draws.
        stress_values = np.random.default_rng(seed=0).standard_normal((N_scan, 3))

        ws._sample_logs[HidraConstants.STRESS_FIELD] = stress_values
        # Direction is stored as array with same value for each subrun
        ws._sample_logs[HidraConstants.STRESS_FIELD_DIRECTION] = np.array(["z"] * N_scan)

        sample = _Sample.init_group([ws._sample_logs])

        assert "stress_field" in sample
        assert sample["stress_field"].shape[0] == N_scan
        assert sample["stress_field"].dtype == FIELD_DTYPE.FLOAT_DATA.value
        # The direction attribute gets the array value
        direction_val = sample["stress_field"].attrs["direction"]
        # Using `nexusformat`, for a string attribute it will return a list, check first element
        if isinstance(direction_val, list):
            assert direction_val[0] == "z"
        else:
            assert direction_val == "z"

    def test_Sample_stress_field_shape_mismatch(self, minimal_HidraWorkspace: Callable[..., HidraWorkspace]):
        """Verify RuntimeError when stress_field first axis != N_scan"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Add stress field with wrong shape
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        # Local, freshly-seeded generator -- see test_Sample_stress_field_present for why.
        wrong_shape_stress = np.random.default_rng(seed=0).standard_normal((N_scan + 5, 3))  # Wrong first dimension

        # Set `_data` dict directly, otherwise `SampleLogs.__setitem__` itself will raise an exception.
        ws._sample_logs._data[HidraConstants.STRESS_FIELD] = wrong_shape_stress

        with pytest.raises(RuntimeError, match=r".*unexpected shape.*"):
            _Sample.init_group([ws._sample_logs])

    def test_Sample_coordinate_shape_mismatch(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify RuntimeError when coordinate array axis != N_scan"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Corrupt vx to have wrong size by directly manipulating the logs
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)

        # Create bad coordinate data with wrong length
        # Set `_data` dict directly, otherwise `SampleLogs.__setitem__` itself will raise an exception.
        ws._sample_logs._data["vx"] = np.zeros(N_scan + 5)  # Wrong size
        ws._sample_logs._data["vy"] = np.zeros(N_scan + 5)
        ws._sample_logs._data["vz"] = np.zeros(N_scan + 5)

        with pytest.raises(RuntimeError, match=r".*unexpected shape.*"):
            _Sample.init_group([ws._sample_logs])

    def test_Sample_extra_logs(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify logs not in NXstress_logs go to logs NXcollection with local_name"""
        ws = minimal_HidraWorkspace(with_instrument=False)

        # Add a custom log with ':' in the name and units using tuple syntax
        custom_log_name = "HB2B:CS:CustomValue"
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        custom_log_value = np.full(N_scan, 42.0)
        ws._sample_logs[(custom_log_name, "mm")] = custom_log_value

        sample = _Sample.init_group([ws._sample_logs])

        assert "logs" in sample
        assert isinstance(sample["logs"], NXcollection)

        # ':' is escaped as '__3A'. The literal is spelled out rather than computed
        # from allowed_identifier, so this test fails if the encoding changes rather
        # than silently tracking it. (It previously expected 'HB2B_CS_CustomValue',
        # from a conversion that collided distinct log names onto one.)
        expected_field_name = "HB2B__3ACS__3ACustomValue"
        assert expected_field_name in sample["logs"]

        # Verify attributes: local_name still recovers the original PV name
        assert sample["logs"][expected_field_name].attrs["local_name"] == custom_log_name
        assert sample["logs"][expected_field_name].attrs["units"] == "mm"


class TestSampleTailAppend:
    """`init_group(logss, data=...)` grows an existing SAMPLE_DESCRIPTION group.

    Per-family coverage, independent of the end-to-end round trip in
    `test_append.py`.
    """

    def test_append_grows_every_per_scan_point_field_by_the_same_count(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        # Arrange
        first = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([1, 2, 3]))
        second = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([4, 5]))
        sd = _Sample.init_group([first._sample_logs])
        before = np.asarray(sd["vx"].nxdata).copy()

        # Act
        returned = _Sample.init_group([second._sample_logs], data=sd)

        # Assert
        assert returned is sd
        assert sd["scan_point"].nxdata.tolist() == [1, 2, 3, 4, 5]
        for axis in ("vx", "vy", "vz"):
            assert sd[axis].shape[0] == 5, axis
        for name in sd["logs"]:
            assert sd["logs"][name].shape[0] == 5, name
        assert np.array_equal(np.asarray(sd["vx"].nxdata)[:3], before)

    def test_append_with_a_different_retained_log_set_raises(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Existing rows would have no value for a log the appended batch introduces."""
        # Arrange
        first = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([1, 2, 3]))
        second = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([4, 5]))
        second.set_sample_log("an_extra_log", np.array([4, 5]), np.zeros(2))
        sd = _Sample.init_group([first._sample_logs])

        # Act / Assert
        with pytest.raises(RuntimeError, match=r"retained sample logs do not match"):
            _Sample.init_group([second._sample_logs], data=sd)

    def test_append_of_a_longer_string_log_is_not_truncated(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        tmp_path: Path,
    ):
        """A fixed-width `|S` column would silently truncate; `_writable` prevents it.

        `Filename` is a bytes log, and a fixed-width HDF5 string column is sized by
        the longest value present when it is created. Appending a longer one raises
        nothing and lands a prefix -- which is why `_writable` coerces `|S` to the
        variable-length dtype. Round-tripped through a real file, because the
        truncation only happens on the h5py write path.
        """
        # Arrange
        first = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([1, 2, 3]), name="s")
        longer = "a_considerably_longer_filename"
        second = minimal_HidraWorkspace(with_instrument=False, sub_runs=np.array([4, 5]), name=longer)
        sd = _Sample.init_group([first._sample_logs])
        _Sample.init_group([second._sample_logs], data=sd)

        path = tmp_path / "logs.nxs"
        with nxopen(path, "w") as root:
            root["entry"] = NXentry()
            root["entry"]["sample"] = sd

        # Act
        with nxopen(path, "r") as root:
            values = [
                v.decode("utf-8") if isinstance(v, bytes) else str(v)
                for v in root["entry"]["sample"]["logs"]["Filename"].nxdata
            ]

        # Assert
        assert values[-1] == f"{longer}.h5"
