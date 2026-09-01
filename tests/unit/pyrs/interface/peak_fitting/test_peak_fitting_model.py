"""Unit tests for `PeakFittingModel` -- suffix-dispatched NXstress/.h5 save-load,
`PyRsCore.register_hidra_workspace`, and the `plot_diff_and_fitted_data` guard
against a None fitted spectrum after an NXstress load.
"""

from pathlib import Path
from typing import Callable

import pytest

from pyrs.core.pyrscore import PyRsCore
from pyrs.core.workspaces import HidraWorkspace
from pyrs.interface.peak_fitting.peak_fitting_crtl import PeakFittingCrtl
from pyrs.interface.peak_fitting.peak_fitting_model import PeakFittingModel
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.peaks.peak_fit_engine import FitResult


class _FakeFitSetupView:
    """Minimal stand-in for the Qt fit-setup view -- only the methods
    `plot_diff_and_fitted_data` actually calls, no real widget construction."""

    def __init__(self):
        self.experiment_calls = []
        self.fitted_calls = []

    def plot_experiment_data(self, diff_data_set, data_reference):
        self.experiment_calls.append((diff_data_set, data_reference))

    def plot_fitted_data(self, x_array, y_array):
        self.fitted_calls.append((x_array, y_array))

    def plot_fitting_diff_data(self, x_axis, y_axis):
        pass


@pytest.fixture
def peak_model() -> PeakFittingModel:
    return PeakFittingModel(PyRsCore())


class TestPeakFittingModelNXstressRoundtrip:
    def test_save_and_load_nxstress_roundtrip(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ):
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        n_subrun = len(ws.get_sub_runs())
        peak = minimal_PeakCollection(N_subrun=n_subrun)

        peak_model.hidra_workspace = ws
        peak_model._project_name = "test_project"

        peak_model.fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)

        out_path = tmp_path / "roundtrip.nxs"
        peak_model.save_fit_result(str(out_path))
        assert out_path.exists()

        reloaded = PeakFittingModel(PyRsCore())
        reloaded.load_hidra_project(str(out_path))

        assert reloaded.hidra_workspace is not None
        assert len(reloaded.hidra_workspace.get_sub_runs()) == n_subrun
        assert reloaded._curr_file_name == str(out_path)

        # Phase-1 scope: fitted/difference stay None (documented limitation) --
        # see the guard in PeakFittingCrtl.plot_diff_and_fitted_data below.
        assert reloaded.fit_result is not None
        assert reloaded.fit_result.fitted is None
        assert reloaded.fit_result.difference is None
        assert len(reloaded.fit_result.peakcollections) == 1

    def test_load_nxstress_rejects_multiple_files(self, peak_model: PeakFittingModel, tmp_path: Path):
        with pytest.raises(ValueError):
            peak_model.load_hidra_project([str(tmp_path / "a.nxs"), str(tmp_path / "b.nxs")])

    def test_load_nxstress_registers_workspace_for_plotting(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ):
        # Verifies the fix for the gap where an NXstress-loaded session left
        # PyRsCore's session registry empty -- get_diffraction_data (and therefore
        # any sub-run plotting) would otherwise raise immediately after a load.
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        n_subrun = len(ws.get_sub_runs())
        peak = minimal_PeakCollection(N_subrun=n_subrun)

        peak_model.hidra_workspace = ws

        peak_model.fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)
        peak_model._project_name = "test_project"

        out_path = tmp_path / "roundtrip.nxs"
        peak_model.save_fit_result(str(out_path))

        reloaded = PeakFittingModel(PyRsCore())
        reloaded.load_hidra_project(str(out_path))

        # Would raise (session not registered) before the register_hidra_workspace fix.
        diff_data_set = reloaded.get_diffraction_data(sub_run=1, mask=None)
        assert diff_data_set is not None

    def test_plot_diff_and_fitted_data_does_not_raise_when_fitted_is_none(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ):
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        n_subrun = len(ws.get_sub_runs())
        peak = minimal_PeakCollection(N_subrun=n_subrun)

        peak_model.hidra_workspace = ws

        peak_model.fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)
        peak_model._project_name = "test_project"

        out_path = tmp_path / "roundtrip.nxs"
        peak_model.save_fit_result(str(out_path))

        reloaded = PeakFittingModel(PyRsCore())
        reloaded.load_hidra_project(str(out_path))

        crtl = PeakFittingCrtl(reloaded)
        fake_view = _FakeFitSetupView()

        # Previously crashed unconditionally on fit_result.fitted.readX(...).
        crtl.plot_diff_and_fitted_data(fake_view, sub_run_number=1)

        assert len(fake_view.experiment_calls) == 1
        assert len(fake_view.fitted_calls) == 0


class TestPeakFittingModelSuffixRouting:
    def test_h5_suffix_still_routes_through_hidraprojectfile(
        self,
        peak_model: PeakFittingModel,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ):
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        project_path = write_minimal_h5_project(ws, filename="source.h5")

        peak_model.load_hidra_project([str(project_path)])
        assert peak_model._curr_file_name == str(project_path)
        # The .h5 load path never populates fit_result -- unaffected by the new
        # .nxs branch above.
        assert peak_model.fit_result is None

        peak = minimal_PeakCollection(N_subrun=len(ws.get_sub_runs()))

        peak_model.fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)

        out_path = tmp_path / "saved.h5"
        peak_model.save_fit_result(str(out_path))
        assert out_path.exists()
