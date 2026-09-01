"""
Shared fixtures for GUI-model (non-Qt) unit tests under `tests/unit/pyrs/interface/`.

These tests exercise `PeakFittingModel`/`TextureFittingModel` directly -- no
`QWidget` is constructed -- so they stay in `unit/`, not `ui/`.
"""

from pathlib import Path
from typing import Callable

import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.projectfile.file_object import HidraProjectFile, HidraProjectFileMode


@pytest.fixture
def write_minimal_h5_project(tmp_path: Path) -> Callable[..., Path]:
    """Persist a synthetic in-memory `HidraWorkspace` (e.g. from `minimal_HidraWorkspace`)
    to a real `.h5` `HidraProjectFile` on disk under `tmp_path`.

    Both `PeakFittingModel.save_fit_result` and `TextureFittingModel.save_fit_result`
    copy an existing project file and then patch peak parameters into the copy for
    their `.h5` branch -- exercising that branch (as opposed to the NXstress branch,
    which writes fresh with no existing file) requires a real file on disk to start
    from.
    """

    def _init(ws: HidraWorkspace, filename: str = "project.h5") -> Path:
        file_path = tmp_path / filename
        project = HidraProjectFile(str(file_path), mode=HidraProjectFileMode.OVERWRITE)
        # `sub_runs=None` exports all sub-runs -- passing `ws.get_sub_runs()` (a
        # `SubRuns` instance) directly breaks `save_reduced_diffraction_data`'s
        # internal `sub_runs_array - 1` indexing, which assumes a plain ndarray.
        ws.save_experimental_data(project, sub_runs=None, ignore_raw_counts=True)
        ws.save_reduced_diffraction_data(project, sub_runs=None)
        project.save()
        project.close()
        return file_path

    return _init
