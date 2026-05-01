"""
tests/scripts/cis_tests/NXstress_demo_script.py

Smoke-test / "by hand" demo script for the NXstress I/O implementation.

Features demonstrated
---------------------
1. Loading a ``HidraWorkspace`` from an existing HiDRA project file
   (``tests/data/3393_PWHT-TD.h5``).

2. Fitting two diffraction peaks with
   ``tests.util.peak_collection_helpers.generate_PeakCollection_from_workspace``
   to produce a ``list[PeakCollection]``.

   The ``fit_dic`` below mirrors the starting point given in the docstring of
   that helper, but with ``peak_label`` values adjusted to follow the
   ``peak_tag`` convention required by ``NXstress``:

       "<phase_name> <hkl>"   e.g. "Fe 311"

   where ``<hkl>`` is a string of 3 N digits that encodes the Miller indices
   (h, k, l) as N-digit zero-padded integers.  The two peaks present in the
   data file are the austenitic-iron reflections "Fe 311" and "Fe 222", as
   confirmed by the ``hklPhase`` log stored in the file.

3. Writing the workspace and fitted peak collections to a new
   NXstress-compatible NeXus file via ``NXstress`` used as a context manager.

4. Reading the data back from the NXstress file and printing a short summary
   to confirm that the round-trip succeeded.

Usage
-----
Run this script directly (not via pytest)::

    python tests/scripts/cis_tests/NXstress_demo_script.py

The output NXstress file is written to the current working directory as
``NXstress_demo_output.nxs``.
"""

from pathlib import Path

from pyrs.core.workspaces import HidraWorkspace
from pyrs.projectfile.file_object import HidraProjectFile, HidraProjectFileMode
from pyrs.utilities.NXstress import NXstress

from tests.util.peak_collection_helpers import generate_PeakCollection_from_workspace

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Repository root is two levels above the directory of this script:
#   tests/scripts/cis_tests/  ->  tests/scripts/  ->  tests/  ->  <root>
_REPO_ROOT = Path(__file__).resolve().parents[3]

DATA_FILE = _REPO_ROOT / "tests" / "data" / "3393_PWHT-TD.h5"
OUTPUT_FILE = Path("NXstress_demo_output.nxs")

# ---------------------------------------------------------------------------
# Peak-fit configuration
# ---------------------------------------------------------------------------
# ``peak_label`` values MUST follow the ``peak_tag`` convention so that
# ``_Peaks._parse_peak_tag`` can extract a phase name and Miller indices.
# The data file records "Fe 311, Fe 222" in its ``hklPhase`` log.
#
# fit_dic format:
#   key   – arbitrary string used as an ordered loop index
#   value – dict with:
#       "peak_range"  : [x_min, x_max]  (2θ in degrees)
#       "peak_label"  : peak_tag string  ("<phase> <hkl>")
#       "d0"          : reference d-spacing in Å (for strain calculation)
FIT_DIC = {
    "0": {"peak_range": [87.599, 91.569], "peak_label": "Fe 311", "d0": 1.08},
    "1": {"peak_range": [93.544, 95.890], "peak_label": "Fe 222", "d0": 1.03},
}

# ---------------------------------------------------------------------------
# Step 1 – Load the HidraWorkspace
# ---------------------------------------------------------------------------
print("=" * 60)
print("Step 1: Loading HidraWorkspace")
print(f"  file: {DATA_FILE}")

ws = HidraWorkspace("3393_PWHT-TD")
with HidraProjectFile(DATA_FILE, mode=HidraProjectFileMode.READONLY) as project_file:
    ws.load_hidra_project(project_file, load_raw_counts=True, load_reduced_diffraction=True)

print(f"  sub-runs loaded : {len(ws.get_sub_runs())}")
print(f"  wavelength      : {ws.get_wavelength(calibrated=True, throw_if_not_set=False)} Å")

# ---------------------------------------------------------------------------
# Step 2 – Fit peaks and build list[PeakCollection]
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("Step 2: Fitting peaks with generate_PeakCollection_from_workspace")

peak_collections = generate_PeakCollection_from_workspace(ws, FIT_DIC)

print(f"  PeakCollections fitted: {len(peak_collections)}")
for pc in peak_collections:
    print(f"    peak_tag      : {pc.peak_tag!r}")
    print(f"    peak_profile  : {pc.peak_profile}")
    print(f"    background    : {pc.background_type}")

# ---------------------------------------------------------------------------
# Step 3 – Write to NXstress file
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print(f"Step 3: Writing NXstress file -> {OUTPUT_FILE}")

with NXstress(OUTPUT_FILE, mode="w") as nxs:
    nxs.write(ws, peak_collections)

print(f"  Written: {OUTPUT_FILE.resolve()}")

# ---------------------------------------------------------------------------
# Step 4 – Read back and verify round-trip
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("Step 4: Reading back from NXstress file")

with NXstress(OUTPUT_FILE, mode="r") as nxs:
    ws_back, peaks_back = nxs.read(entry_number=1)

print(f"  sub-runs read back    : {len(ws_back.get_sub_runs())}")
print(f"  PeakCollections read  : {len(peaks_back)}")
for pc in peaks_back:
    print(f"    peak_tag (read back): {pc.peak_tag!r}")

# Quick consistency check
assert len(ws_back.get_sub_runs()) == len(ws.get_sub_runs()), (
    "Round-trip sub-run count mismatch!"
)
assert len(peaks_back) == len(peak_collections), (
    "Round-trip PeakCollection count mismatch!"
)

print()
print("=" * 60)
print("Demo completed successfully.")
