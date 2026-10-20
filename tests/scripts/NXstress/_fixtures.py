"""
Shared builders for the by-hand NXstress scripts in this directory.

Each script here demonstrates one NXstress feature to a reviewer, asserting what
it prints. Run from the repository root:

    pixi run python tests/scripts/NXstress/<script>.py

`tests/scripts/` is never collected by pytest (`norecursedirs`). The synthetic
builders are the same plain functions the NXstress test fixtures wrap, so a
script and a test build identical workspaces.
"""

import contextlib
import copy
import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np

# A script's own directory is first on `sys.path`, not the repository root, so
# `tests.util` is importable only once the root is added.
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pyrs.utilities.config as config_module  # noqa: E402
from neutrons_standard.config import merge_dicts  # noqa: E402
from pyrs.core.workspaces import HidraWorkspace  # noqa: E402
from pyrs.peaks.peak_collection import PeakCollection  # noqa: E402
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode  # noqa: E402
from tests.util.peak_collection_helpers import _SEED, make_peak_collection  # noqa: E402
from tests.util.workspace_helpers import make_minimal_HidraWorkspace  # noqa: E402

TEST_DATA = REPO / "tests" / "data"


def check(label: str, condition: bool) -> None:
    """Print `label` with its outcome, and stop the script if it is false."""
    print(f"  [{'ok' if condition else 'FAILED'}] {label}")
    if not condition:
        raise SystemExit(f"FAILED: {label}")


def sha256(path: Path) -> str:
    """Hex digest of a file's bytes, to show that a refused operation changed nothing."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_project(path: Path) -> tuple[HidraWorkspace, list[PeakCollection]]:
    """A Hidra project file's workspace (reduced data, no raw counts) and its fitted peaks."""
    project = HidraProjectFile(str(path), HidraProjectFileMode.READONLY)
    try:
        ws = HidraWorkspace(Path(path).stem)
        ws.load_hidra_project(project, load_raw_counts=False, load_reduced_diffraction=True)
        peaks = [project.read_peak_parameters(tag) for tag in project.read_peak_tags()]
    finally:
        project.close()
    return ws, peaks


def synthetic_workspace(sub_runs: list[int], *, direction: str | None = None, **kwargs) -> HidraWorkspace:
    """A small synthetic workspace with instrument geometry over `sub_runs`.

    Args:
        sub_runs: Its scan points; workspaces sharing an NXstress entry need disjoint ones.
        direction: If given, recorded as a constant `direction` sample log -- the
            usual discriminator.
        **kwargs: Passed to `make_minimal_HidraWorkspace`.
    """
    ws = make_minimal_HidraWorkspace(sub_runs=np.asarray(sub_runs), **kwargs)
    if direction is not None:
        ws.set_sample_log("direction", np.asarray(sub_runs), np.array([direction] * len(sub_runs)))
    return ws


def synthetic_peaks(ws: HidraWorkspace, tag: str = "Fe 110") -> PeakCollection:
    """A fitted `PeakCollection` over `ws`'s scan points, with reproducible random values."""
    sub_runs = ws.get_sub_runs().raw_copy()
    return make_peak_collection(
        rng=np.random.default_rng(_SEED),
        peak_tag=tag,
        peak_profile="Gaussian",
        background_type="Linear",
        wavelength=1.486,
        projectfilename="/does/not/exist.h5",
        runnumber=1,
        N_subrun=len(sub_runs),
        sub_runs=sub_runs,
    )


@contextlib.contextmanager
def nxstress_config(**keys) -> Iterator[None]:
    """Override `nxstress.*` config keys for the duration of a `with` block.

    Merged into the live `Config` singleton and validated, then restored, exactly
    as the `config_override` test fixture does: every module that bound `Config`
    sees the change. Production reads overrides from a YAML file named by the
    `env` environment variable instead.
    """
    config = config_module.Config
    saved = copy.deepcopy(config._config)
    try:
        merge_dicts(config._config, {"nxstress": keys})
        config_module.validate_config()
        yield
    finally:
        config._config.clear()
        config._config.update(saved)
