"""Unit tests for `PeakFittingModel` -- `fit_diff_peaks` failure reporting,
suffix-dispatched NXstress/.h5 save-load, `PyRsCore.register_hidra_workspace`,
and the `plot_diff_and_fitted_data` guard against a None fitted spectrum after
an NXstress load.
"""

from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from pyrs.core.pyrscore import PyRsCore
from pyrs.core.workspaces import HidraWorkspace
from pyrs.interface.peak_fitting.peak_fitting_crtl import PeakFittingCrtl
from pyrs.interface.peak_fitting.peak_fitting_model import PeakFittingModel
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.peaks.peak_fit_engine import FitResult

# Every test here drives PeakFittingModel together with a separate library
# (NXstress or HidraProjectFile) and PyRsCore's session registry -- a
# multi-component workflow, not just one component's own internals -- even
# though the data involved is synthetic (see CLAUDE.md's Pytest markers policy).
pytestmark = pytest.mark.integration


class _FakeFitSetupView:
    """Minimal stand-in for the Qt fit-setup view -- only the methods
    `plot_diff_and_fitted_data` actually calls, no real widget construction."""

    def __init__(self) -> None:
        self.experiment_calls: list = []
        self.fitted_calls: list = []

    def plot_experiment_data(self, diff_data_set: Any, data_reference: str) -> None:
        self.experiment_calls.append((diff_data_set, data_reference))

    def plot_fitted_data(self, x_array: Any, y_array: Any) -> None:
        self.fitted_calls.append((x_array, y_array))

    def plot_fitting_diff_data(self, x_axis: Any, y_axis: Any) -> None:
        pass


@pytest.fixture
def peak_model() -> PeakFittingModel:
    return PeakFittingModel(PyRsCore())


@pytest.fixture
def model(qapp):  # noqa: ARG001 (qapp needed for QObject/Signal machinery)
    peak_fit_model = PeakFittingModel(peak_fit_core=MagicMock())
    peak_fit_model.hidra_workspace = MagicMock()
    return peak_fit_model


def test_fit_diff_peaks_normal_case_returns_result(model, monkeypatch):
    """A successful fit returns the fit result and stores it on the model."""
    # Arrange
    fake_result = MagicMock()
    fake_engine = MagicMock()
    fake_engine.fit_multiple_peaks.return_value = fake_result
    monkeypatch.setattr(
        "pyrs.interface.peak_fitting.peak_fitting_model.PeakFitEngineFactory.getInstance",
        MagicMock(return_value=fake_engine),
    )
    emitted = []
    model.failureMsg.connect(lambda *args: emitted.append(args))

    # Act
    result = model.fit_diff_peaks(["peak0"], [1.0], [2.0], "PseudoVoigt", "Linear")

    # Assert
    assert result is fake_result
    assert model.fit_result is fake_result
    assert emitted == []


def test_fit_diff_peaks_error_case_emits_failure_and_returns_none(model, monkeypatch):
    """When the fit engine raises, failureMsg is emitted instead of the exception propagating."""
    # Arrange
    monkeypatch.setattr(
        "pyrs.interface.peak_fitting.peak_fitting_model.PeakFitEngineFactory.getInstance",
        MagicMock(side_effect=RuntimeError("fit did not converge")),
    )
    emitted = []
    model.failureMsg.connect(lambda *args: emitted.append(args))

    # Act
    result = model.fit_diff_peaks(["peak0"], [1.0], [2.0], "PseudoVoigt", "Linear")

    # Assert
    assert result is None
    assert model.fit_result is None
    assert len(emitted) == 1
    title, message, detail = emitted[0]
    assert "fit did not converge" in message
    assert "RuntimeError" in detail


class TestPeakFittingModelNXstressRoundtrip:
    def test_save_fit_result_nxstress_roundtrip_matches_workspace_and_peaks(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
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

    def test_load_hidra_project_multiple_nxstress_files_raises_value_error(
        self, peak_model: PeakFittingModel, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError):
            peak_model.load_hidra_project([str(tmp_path / "a.nxs"), str(tmp_path / "b.nxs")])

    def test_load_hidra_project_nxstress_get_diffraction_data_succeeds(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
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

    def test_plot_diff_and_fitted_data_fitted_none_does_not_raise(
        self,
        peak_model: PeakFittingModel,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
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
        # _FakeFitSetupView is a duck-typed stub, not a PeakFitSetupView subclass.
        crtl.plot_diff_and_fitted_data(fake_view, sub_run_number=1)  # type: ignore[arg-type]

        assert len(fake_view.experiment_calls) == 1
        assert len(fake_view.fitted_calls) == 0


class TestPeakFittingModelSuffixRouting:
    def test_save_fit_result_h5_suffix_routes_through_hidraprojectfile(
        self,
        peak_model: PeakFittingModel,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
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
