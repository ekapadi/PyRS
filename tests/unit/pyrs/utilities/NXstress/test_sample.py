"""
Tests for pyrs/utilities/NXstress/_sample.py
"""
import numpy as np
from nexusformat.nexus import NXsample, NXcollection
import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.dataobjects.constants import HidraConstants
from pyrs.utilities.NXstress._sample import _Sample
from pyrs.utilities.NXstress._definitions import FIELD_DTYPE


class TestSample:
    """Test suite for _sample.py"""

    PROJECT_FILE_A = "HB2B_1017.h5"  # instrument, input data, reduced data, no mask
    PROJECT_FILE_B = "HB2B_1628.h5"  # instrument, mask, reduced data, but no input data
    PROJECT_FILE_C = "HB2B_1017_w_mask.h5"  # instrument, mask, input data, reduced data

    def test_Sample_scan_point_and_coordinates(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify scan_point matches subruns and vx,vy,vz have correct shape/dtype"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert isinstance(sample, NXsample)
        assert 'scan_point' in sample
        assert 'vx' in sample
        assert 'vy' in sample
        assert 'vz' in sample
        
        # Verify scan_point matches subruns
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        
        np.testing.assert_array_equal(
            sample['scan_point'].nxdata,
            subruns.astype(FIELD_DTYPE.INT_DATA.value)
        )
        
        # Verify coordinate arrays have correct shape and dtype
        for coord in ['vx', 'vy', 'vz']:
            assert sample[coord].shape == (N_scan,)
            assert sample[coord].dtype == FIELD_DTYPE.FLOAT_DATA.value

    def test_Sample_chemical_formula_present(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify chemical_formula field when CHEMICAL_FORMULA log is present"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Add chemical formula to logs
        ws._sample_logs._logs[HidraConstants.CHEMICAL_FORMULA] = ['Fe3O4']
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'chemical_formula' in sample
        assert sample['chemical_formula'] == 'Fe3O4'

    def test_Sample_chemical_formula_absent(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify chemical_formula defaults to 'unknown' when not in logs"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Ensure chemical formula is not in logs
        if HidraConstants.CHEMICAL_FORMULA in ws._sample_logs._logs:
            del ws._sample_logs._logs[HidraConstants.CHEMICAL_FORMULA]
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'chemical_formula' in sample
        assert sample['chemical_formula'] == 'unknown'

    def test_Sample_temperature_present(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify temperature field and units when TEMPERATURE log is present"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Add temperature data to logs
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        temp_values = np.linspace(300, 400, N_scan)
        
        ws._sample_logs._logs[HidraConstants.TEMPERATURE] = temp_values
        ws._sample_logs._units[HidraConstants.TEMPERATURE] = 'K'
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'temperature' in sample
        assert sample['temperature'].shape == (N_scan,)
        assert sample['temperature'].dtype == FIELD_DTYPE.FLOAT_DATA.value
        assert sample['temperature'].attrs['units'] == 'K'

    def test_Sample_temperature_absent(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify no temperature field when TEMPERATURE log is absent"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Ensure temperature is not in logs
        if HidraConstants.TEMPERATURE in ws._sample_logs._logs:
            del ws._sample_logs._logs[HidraConstants.TEMPERATURE]
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'temperature' not in sample

    def test_Sample_stress_field_present(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify stress_field field, shape, and direction attr when present"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Add stress field data to logs
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        stress_values = np.random.randn(N_scan, 3)
        
        ws._sample_logs._logs[HidraConstants.STRESS_FIELD] = stress_values
        ws._sample_logs._logs[HidraConstants.STRESS_FIELD_DIRECTION] = 'z'
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'stress_field' in sample
        assert sample['stress_field'].shape[0] == N_scan
        assert sample['stress_field'].dtype == FIELD_DTYPE.FLOAT_DATA.value
        assert sample['stress_field'].attrs['direction'] == 'z'

    def test_Sample_stress_field_shape_mismatch(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify RuntimeError when stress_field first axis != N_scan"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Add stress field with wrong shape
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        wrong_shape_stress = np.random.randn(N_scan + 5, 3)  # Wrong first dimension
        
        ws._sample_logs._logs[HidraConstants.STRESS_FIELD] = wrong_shape_stress
        
        with pytest.raises(RuntimeError, match=r".*unexpected shape.*"):
            _Sample.init_group(ws._sample_logs)

    def test_Sample_coordinate_shape_mismatch(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify RuntimeError when coordinate array axis != N_scan"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Corrupt vx to have wrong size by directly manipulating the logs
        subruns = ws._sample_logs.subruns.raw_copy()
        N_scan = len(subruns)
        
        # Create bad coordinate data with wrong length
        ws._sample_logs._logs['vx'] = np.zeros(N_scan + 5)  # Wrong size
        
        with pytest.raises(RuntimeError, match=r".*unexpected shape.*"):
            _Sample.init_group(ws._sample_logs)

    def test_Sample_extra_logs(
        self,
        load_HidraWorkspace: HidraWorkspace,
    ):
        """Verify logs not in NXstress_logs go to logs NXcollection with local_name"""
        ws = load_HidraWorkspace(
            file_name=self.PROJECT_FILE_B,
            name='test_workspace',
            load_raw_counts=False,
            load_reduced_diffraction=True
        )
        
        # Add a custom log with ':' in the name
        custom_log_name = 'HB2B:CS:CustomValue'
        custom_log_value = [42.0]
        ws._sample_logs._logs[custom_log_name] = custom_log_value
        ws._sample_logs._units[custom_log_name] = 'mm'
        
        sample = _Sample.init_group(ws._sample_logs)
        
        assert 'logs' in sample
        assert isinstance(sample['logs'], NXcollection)
        
        # The ':' should be replaced by '_'
        expected_field_name = 'HB2B_CS_CustomValue'
        assert expected_field_name in sample['logs']
        
        # Verify attributes
        assert sample['logs'][expected_field_name].attrs['local_name'] == custom_log_name
        assert sample['logs'][expected_field_name].attrs['units'] == 'mm'
