"""Integration round-trip tests for spec 02 (NXstress I/O for PeakFitting & Texture
viewers): write via NXstress, read back, assert HidraWorkspace/PeakCollection
equality; and confirm the .h5 suffix still routes through HidraProjectFile
(no regression to the pre-existing path). And the strain/stress viewer: every
loaded direction saved to one `.nxs` file and loaded back.

Model-level only (no QWidget construction) -- see tests/ui/test_peak_fitting.py /
test_texture_fitting.py / test_nxstress_roundtrip.py for the GUI-level
enablement-wiring coverage.
"""

from pathlib import Path
from typing import Callable

import h5py
import numpy as np
import pytest

from pyrs.core.pyrscore import PyRsCore
from pyrs.core.workspaces import HidraWorkspace
from pyrs.interface.combine_runs.combine_runs_model import CombineRunsModel
from pyrs.interface.peak_fitting.peak_fitting_model import PeakFittingModel
from pyrs.interface.strainstressviewer.model import Model as StrainStressModel
from pyrs.interface.texture_fitting.texture_fitting_model import TextureFittingModel
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.peaks.peak_fit_engine import FitResult
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode
from pyrs.utilities.NXstress.NXstress import NXstress

pytestmark = pytest.mark.integration


class TestPeakFittingViewerRoundtrip:
    def test_save_fit_result_nxstress_roundtrip_matches_workspace_and_peaks(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        n_subrun = len(ws.get_sub_runs())
        peaks = [
            minimal_PeakCollection(N_subrun=n_subrun, peak_tag="Fe110", runnumber=1),
            minimal_PeakCollection(N_subrun=n_subrun, peak_tag="Ni200", runnumber=1),
        ]

        model = PeakFittingModel(PyRsCore())
        model.hidra_workspace = ws
        model.fit_result = FitResult(peakcollections=peaks, fitted=None, difference=None)
        model._project_name = "test_project"

        out_path = tmp_path / "roundtrip.nxs"
        model.save_fit_result(str(out_path))
        assert out_path.exists()

        reloaded = PeakFittingModel(PyRsCore())
        reloaded.load_hidra_project(str(out_path))

        assert len(reloaded.hidra_workspace.get_sub_runs()) == n_subrun
        assert len(reloaded.fit_result.peakcollections) == len(peaks)
        reloaded_tags = sorted(p.peak_tag for p in reloaded.fit_result.peakcollections)
        assert reloaded_tags == sorted(p.peak_tag for p in peaks)

    def test_save_fit_result_h5_suffix_routes_through_hidraprojectfile(
        self,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
        ws = minimal_HidraWorkspace(with_instrument=True)
        project_path = write_minimal_h5_project(ws, filename="source.h5", with_instrument=True)

        model = PeakFittingModel(PyRsCore())
        model.load_hidra_project([str(project_path)])
        assert model._curr_file_name == str(project_path)
        # The .h5 load path never populates fit_result -- confirms the new .nxs
        # branch above didn't change this pre-existing behavior.
        assert model.fit_result is None

        peak = minimal_PeakCollection(N_subrun=len(ws.get_sub_runs()))
        model.fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)

        out_path = tmp_path / "saved.h5"
        model.save_fit_result(str(out_path))
        assert out_path.exists()


class TestTextureFittingViewerRoundtrip:
    def test_save_fit_result_nxstress_roundtrip_matches_workspace_and_peaks(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        n_subrun = len(ws.get_sub_runs())
        peaks = [
            minimal_PeakCollection(N_subrun=n_subrun, peak_tag="Fe110", runnumber=1),
            minimal_PeakCollection(N_subrun=n_subrun, peak_tag="Ni200", runnumber=1),
        ]

        model = TextureFittingModel(None)
        model.ws = ws
        fit_result = FitResult(peakcollections=peaks, fitted=None, difference=None)

        out_path = tmp_path / "roundtrip.nxs"
        model.save_fit_result(str(out_path), fit_result=fit_result)
        assert out_path.exists()

        reloaded = TextureFittingModel(None)
        reloaded.load_hidra_project_file(str(out_path))

        assert reloaded.ws is not None
        assert reloaded.fit_result is not None
        assert len(reloaded.ws.get_sub_runs()) == n_subrun
        assert len(reloaded.fit_result.peakcollections) == len(peaks)
        reloaded_tags = sorted(p.peak_tag for p in reloaded.fit_result.peakcollections)
        assert reloaded_tags == sorted(p.peak_tag for p in peaks)

    def test_save_fit_result_h5_suffix_routes_through_hidraprojectfile(
        self,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection: Callable[..., PeakCollection],
        tmp_path: Path,
    ) -> None:
        ws = minimal_HidraWorkspace(with_instrument=True)
        project_path = write_minimal_h5_project(ws, filename="source.h5", with_instrument=True)

        model = TextureFittingModel(None)
        model.load_hidra_project_file(str(project_path))
        assert model._curr_file_name == str(project_path)

        peak = minimal_PeakCollection(N_subrun=len(ws.get_sub_runs()))
        fit_result = FitResult(peakcollections=[peak], fitted=None, difference=None)

        out_path = tmp_path / "saved.h5"
        model.save_fit_result(str(out_path), fit_result=fit_result)
        assert out_path.exists()


class TestCombineRunsViewerRoundtrip:
    def test_export_project_files_nxstress_roundtrip_matches_merged_workspace(
        self,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        tmp_path: Path,
    ) -> None:
        # combine_project_files merges with load_raw_counts=False, so the merged
        # workspace never carries raw counts -- the .nxs export never populates
        # the optional input_data group. This test's scope is deliberately
        # narrowed to sub-run counts and sample-log arrays as a direct
        # consequence, not an arbitrary choice -- see
        # open-questions/03-combine-runs-nxstress.md Q1.
        ws1 = minimal_HidraWorkspace(name="run1", with_masks=True)
        ws2 = minimal_HidraWorkspace(name="run2", with_masks=True)
        project_path_1 = write_minimal_h5_project(ws1, filename="run1.h5", with_instrument=True, with_masks=True)
        project_path_2 = write_minimal_h5_project(ws2, filename="run2.h5", with_instrument=True, with_masks=True)

        model = CombineRunsModel()
        model.combine_project_files([str(project_path_1), str(project_path_2)])

        merged_n_subrun = len(model._hidra_ws.get_sub_runs())
        merged_vx = model._hidra_ws.get_sample_log_values("vx")

        out_path = tmp_path / "combined.nxs"
        model.export_project_files(str(out_path))
        assert out_path.exists()

        with NXstress(out_path, "r") as nx:
            # CombineRuns pre-merges its N runs into one workspace before
            # exporting, so the entry holds exactly one -- per the resolved Q3.
            (ws_read,), (peaks_read,) = nx.read()

        assert peaks_read == []
        assert len(ws_read.get_sub_runs()) == merged_n_subrun
        np.testing.assert_allclose(ws_read.get_sample_log_values("vx"), merged_vx)

    def test_export_project_files_wraps_the_merged_workspace_in_a_length_one_list(
        self,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        tmp_path: Path,
    ) -> None:
        """The 04b call-site change for CombineRuns is a wrap, not a restructuring.

        `NXstress.write` now takes N workspaces, but per the resolved Q3
        CombineRuns keeps its in-PyRS pre-merge -- `append_hidra_project`
        discards per-run boundaries, which NXstress does not do (Decisions Log
        row 45), and the unaffected `.h5` export path needs the single merged
        workspace regardless. So the export still
        passes one workspace and no peak collections, now spelled
        `write([ws], [[]])`, and the entry it produces holds exactly one
        workspace no matter how many runs went in.
        """
        # Arrange -- count the sub-runs going IN, so the assertion below is against
        # the inputs rather than against the model that produced the output. Comparing
        # the read-back count to `model._hidra_ws` would hold just as well if
        # `combine_project_files` had silently dropped two of the three runs.
        runs = [minimal_HidraWorkspace(name=f"run{n}", with_masks=True) for n in (1, 2, 3)]
        expected_subruns = sum(len(ws.get_sub_runs()) for ws in runs)
        paths = [
            write_minimal_h5_project(
                ws,
                filename=f"run{n}.h5",
                with_instrument=True,
                with_masks=True,
            )
            for n, ws in enumerate(runs, start=1)
        ]

        # Act
        model = CombineRunsModel()
        model.combine_project_files([str(p) for p in paths])
        out_path = tmp_path / "three-runs.nxs"
        model.export_project_files(str(out_path))

        with NXstress(out_path, "r") as nx:
            workspaces, peakss = nx.read()

        # Assert
        assert len(workspaces) == 1, "three runs pre-merged into one workspace, not three"
        assert peakss == [[]]
        assert len(workspaces[0].get_sub_runs()) == expected_subruns, (
            "the single workspace must carry every run's scan points -- one workspace "
            "out is also what dropping two of the three runs would produce"
        )

    def test_export_project_files_h5_suffix_routes_through_hidraprojectfile(
        self,
        write_minimal_h5_project: Callable[..., Path],
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        tmp_path: Path,
    ) -> None:
        ws1 = minimal_HidraWorkspace(name="run1")
        project_path_1 = write_minimal_h5_project(ws1, filename="run1.h5", with_instrument=True)

        model = CombineRunsModel()
        model.combine_project_files([str(project_path_1)])

        out_path = tmp_path / "combined.h5"
        model.export_project_files(str(out_path))
        assert out_path.exists()


class TestStrainStressViewerRoundtrip:
    """The strain/stress viewer: every loaded direction in one `.nxs` file, and back.

    The inputs have the shape real strain/stress data has: every run numbers its
    scan points from 1, a direction may be loaded from two runs, and each run
    records its `run_number`. Before NXstress keyed scan points by
    `(run, scan point)`, none of this could be written into one entry.
    """

    PEAK = "Fe110"
    RUNS = {"11": (1327, 1328), "22": (1331,), "33": (1332,)}

    @staticmethod
    def project(
        write_minimal_h5_project, minimal_HidraWorkspace, minimal_PeakCollection, *, run: int, n_subruns: int = 4
    ) -> Path:
        """A fitted project file for one run: scan points 1..n, a `run_number` log, one peak."""
        ws = minimal_HidraWorkspace(name=f"HB2B_{run}", with_instrument=True, with_masks=True, n_subruns=n_subruns)
        points = ws.get_sub_runs().raw_copy()
        ws.set_sample_log("run_number", points, np.full(len(points), run))
        path = write_minimal_h5_project(ws, filename=f"HB2B_{run}.h5", with_instrument=True, with_masks=True)
        peaks = minimal_PeakCollection(
            N_subrun=len(points), sub_runs=points, peak_tag=TestStrainStressViewerRoundtrip.PEAK, runnumber=run
        )
        # A fitted file carries a reference spacing; without one every strain error is
        # NaN, and fusing two runs of one direction refuses NaN costs. Varying per
        # scan point, so the round trip has to keep every row's value.
        peaks.set_d_reference(values=1.0 + 0.01 * np.arange(len(points)), errors=0.0001)
        project = HidraProjectFile(str(path), mode=HidraProjectFileMode.READWRITE)
        project.write_peak_parameters(peaks)
        project.save()
        project.close()
        return path

    @pytest.fixture
    def loaded(self, write_minimal_h5_project, minimal_HidraWorkspace, minimal_PeakCollection):
        """A model with all three directions loaded from project files, and stress calculated."""
        model = StrainStressModel()
        for direction, runs in self.RUNS.items():
            setattr(
                model,
                f"e{direction}",
                [
                    str(
                        self.project(write_minimal_h5_project, minimal_HidraWorkspace, minimal_PeakCollection, run=run)
                    )
                    for run in runs
                ],
            )
        model.selectedPeak = self.PEAK
        model.calculate_stress("diagonal", 200.0, 0.3, (1.0, 0.0001))
        return model

    def test_every_direction_is_recovered(self, loaded, tmp_path):
        # Arrange
        path = tmp_path / "stress.nxs"

        # Act
        loaded.save_as_nxstress(str(path))
        reloaded = StrainStressModel()
        assert reloaded.load_nxstress(str(path))

        # Assert
        for direction, runs in self.RUNS.items():
            workspaces = getattr(reloaded, f"e{direction}")
            assert [ws.direction for ws in workspaces] == [direction] * len(runs)
            peaks = getattr(reloaded, f"e{direction}_peaks")
            assert [int(collections[self.PEAK].runnumber) for collections in peaks] == list(runs)
            assert [ws.get_sub_runs().raw_copy().tolist() for ws in workspaces] == [[1, 2, 3, 4]] * len(runs)
            # Each collection records the file it was loaded from -- the `.nxs` now.
            assert all(collections[self.PEAK].projectfilename == path.name for collections in peaks)

    def test_the_stress_summary_is_reproduced(self, loaded, tmp_path):
        """The reconstructed stress field writes the same CSV summary as the original."""
        # Arrange
        path = tmp_path / "stress.nxs"
        loaded.save_as_nxstress(str(path))
        reloaded = StrainStressModel()
        reloaded.load_nxstress(str(path))
        reloaded.selectedPeak = self.PEAK
        reloaded.calculate_stress("diagonal", 200.0, 0.3, (1.0, 0.0001))
        original_csv, reloaded_csv = tmp_path / "original.csv", tmp_path / "reloaded.csv"

        # Act
        loaded.write_stress_to_csv(str(original_csv), False)
        reloaded.write_stress_to_csv(str(reloaded_csv), False)

        # Assert -- the header names the runs per direction, so it must match too
        assert "nan" not in original_csv.read_text().lower(), "the comparison would be NaN against NaN"
        assert original_csv.read_text() == reloaded_csv.read_text()
        assert "# Direction 11: 1327, 1328" in reloaded_csv.read_text()

    def test_each_direction_is_one_contiguous_block_on_disk(self, loaded, tmp_path):
        """Read through h5py, not `NXstress.read`: the on-disk order is the claim."""
        # Arrange
        path = tmp_path / "stress.nxs"

        # Act
        loaded.save_as_nxstress(str(path))

        # Assert
        with h5py.File(path, "r") as f:
            directions = [value.decode() for value in f["entry/peaks/direction"][()]]
        blocks = [d for n, d in enumerate(directions) if n == 0 or d != directions[n - 1]]
        assert blocks == ["11", "22", "33"], f"each direction must be one run of rows, got {blocks}"

    def test_save_without_direction_configured_refused(self, loaded, config_override, tmp_path):
        # Arrange
        config_override({"nxstress": {"discriminator_fields": []}})
        path = tmp_path / "stress.nxs"

        # Act / Assert
        with pytest.raises(RuntimeError, match=r"'direction'.*'nxstress.discriminator_fields'"):
            loaded.save_as_nxstress(str(path))
        assert not path.exists()

    def test_with_nxstress_switched_off_save_is_refused(self, loaded, config_override, tmp_path):
        """`nxstress.enable` switches the whole NXstress feature set, saving included."""
        # Arrange
        config_override({"nxstress": {"enable": False}})
        path = tmp_path / "stress.nxs"

        # Act / Assert
        with pytest.raises(RuntimeError, match=r"'nxstress.enable'"):
            loaded.save_as_nxstress(str(path))
        assert not path.exists()

    def test_with_nxstress_switched_off_load_is_refused(self, loaded, config_override, tmp_path):
        """... and loading too."""
        # Arrange
        path = tmp_path / "stress.nxs"
        loaded.save_as_nxstress(str(path))
        config_override({"nxstress": {"enable": False}})
        reloaded = StrainStressModel()
        failures: list = []
        reloaded.failureMsg.connect(lambda *args: failures.append(args))

        # Act
        result = reloaded.load_nxstress(str(path))

        # Assert
        assert result is False
        assert failures and "'nxstress.enable'" in " ".join(map(str, failures[0]))

    def test_a_file_the_viewer_did_not_write_is_reported(
        self, write_minimal_h5_project, minimal_HidraWorkspace, minimal_PeakCollection, tmp_path
    ):
        """A PeakFitting save records no direction, so there is no slot to put it in."""
        # Arrange
        model = PeakFittingModel(PyRsCore())
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        model.hidra_workspace = ws
        n_subrun = len(ws.get_sub_runs())
        model.fit_result = FitResult(
            peakcollections=[minimal_PeakCollection(N_subrun=n_subrun, peak_tag=self.PEAK)],
            fitted=None,
            difference=None,
        )
        path = tmp_path / "peak_fitting.nxs"
        model.save_fit_result(str(path))
        viewer = StrainStressModel()
        failures: list = []
        viewer.failureMsg.connect(lambda *args: failures.append(args))

        # Act
        result = viewer.load_nxstress(str(path))

        # Assert
        assert result is False
        assert failures and "direction" in " ".join(map(str, failures[0]))
        assert viewer.e11 == viewer.e22 == viewer.e33 == []
