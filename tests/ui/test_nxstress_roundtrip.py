"""
The strain/stress viewer's NXstress actions: enabled by configuration and content, never hidden.

**Save as NXstress...** is enabled only when `nxstress.enable` is set and every
loaded workspace can be written -- it must carry instrument geometry, which
`NXstress.write` requires and which project files with an incomplete
`geometry setup` do not provide. When it cannot be used it is greyed out, not
removed: a hidden action gives no hint that the feature exists. **Load NXstress...**
follows `nxstress.enable` alone, which switches the whole NXstress feature set.

GUI tier: these drive a real `QMainWindow` and its `QAction`s.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.interface.strainstressviewer.controller import Controller
from pyrs.interface.strainstressviewer.model import Model
from pyrs.interface.strainstressviewer.strain_stress_view import StrainStressViewer
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode
from tests.util.project_file_helpers import write_minimal_h5_project  # noqa: F401

pytestmark = [pytest.mark.gui, pytest.mark.integration]


@pytest.fixture
def window(qtbot):
    model = Model()
    viewer = StrainStressViewer(model, Controller(model))
    qtbot.addWidget(viewer)
    return viewer


@pytest.fixture
def fitted_project(
    write_minimal_h5_project,  # noqa: F811
    minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    minimal_PeakCollection: Callable[..., PeakCollection],
) -> Callable[..., Path]:
    """A factory for a fitted project file, with or without instrument geometry."""

    def make(*, with_instrument: bool) -> Path:
        ws = minimal_HidraWorkspace(with_instrument=with_instrument, with_masks=True)
        points = ws.get_sub_runs().raw_copy()
        ws.set_sample_log("run_number", points, np.full(len(points), 1327))
        path = write_minimal_h5_project(
            ws, filename=f"fitted_{with_instrument}.h5", with_instrument=with_instrument, with_masks=True
        )
        peaks = minimal_PeakCollection(N_subrun=len(points), sub_runs=points, peak_tag="Fe110")
        project = HidraProjectFile(str(path), mode=HidraProjectFileMode.READWRITE)
        project.write_peak_parameters(peaks)
        project.save()
        project.close()
        return path

    return make


def test_save_is_disabled_but_visible_when_nxstress_is_off(window, config_override, fitted_project):
    # Arrange
    config_override({"nxstress": {"enable": False}})
    window.model.e11 = [str(fitted_project(with_instrument=True))]

    # Act
    window.update_nxstress_action()

    # Assert
    assert not window.saveNXstressAction.isEnabled()
    assert window.saveNXstressAction.isVisible()


def test_save_is_disabled_with_nothing_loaded(window):
    assert not window.saveNXstressAction.isEnabled()
    assert window.saveNXstressAction.isVisible()


def test_save_is_enabled_once_a_writable_direction_is_loaded(window, fitted_project):
    # Arrange
    window.model.e11 = [str(fitted_project(with_instrument=True))]

    # Act
    window.update_nxstress_action()

    # Assert
    assert window.saveNXstressAction.isEnabled()


def test_save_stays_disabled_for_a_workspace_without_geometry(window, fitted_project):
    """The strain/stress project files in `tests/data` are in this state."""
    # Arrange
    window.model.e11 = [str(fitted_project(with_instrument=False))]

    # Act
    window.update_nxstress_action()

    # Assert
    assert not window.saveNXstressAction.isEnabled()
    assert window.saveNXstressAction.isVisible()


def test_load_follows_nxstress_enable(window, config_override):
    # Arrange
    assert window.loadNXstressAction.isEnabled()
    config_override({"nxstress": {"enable": False}})

    # Act
    window.update_nxstress_action()

    # Assert
    assert not window.loadNXstressAction.isEnabled()
    assert window.loadNXstressAction.isVisible()
