"""`nxstress.enable` switching all of NXstress, and phase 3's configuration defaults.

Shows that:

1. with `nxstress.enable: false`, every NXstress path is refused, loading as
   well as saving: the single-workspace viewers' loader, the strain/stress
   viewer's load and save, the save actions' availability, and the load dialogs'
   file filter, which drops `NXstress (*.nxs)`;
2. `nxstress.default_run_number` is PyRS's one "no run number" (shipped as -1),
   a `PeakCollection` built without a run number takes it, and 0 is refused,
   since it reads as a real run;
3. the shipped `nxstress.discriminator_fields` is `["direction"]`, and a single
   workspace with no direction -- every PeakFitting save -- records no boundary
   and reads back as one workspace.

Leaves `nxstress_off.yml` in the output directory: an override file for the
PR's GUI steps, used as `env=<output-dir>/nxstress_off.yml pixi run pyrs`.

Run from the repository root:

    pixi run python tests/scripts/cis_tests/NXstress/enable_and_defaults.py [output-dir]
"""

from _fixtures import (
    check,
    config_override,
    nxstress_config,
    output_dir,
    run,
    section,
    synthetic_peaks,
    synthetic_workspace,
)

import h5py

from pyrs.interface.gui_helper import load_file_filter, nxstress_save_available
from pyrs.interface.nxstress_load import NXstressDisabled, read_single_workspace
from pyrs.interface.strainstressviewer.model import Model
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.utilities.config import Config, default_run_number
from pyrs.utilities.NXstress.NXstress import NXstress


def first_line(error: BaseException) -> str:
    return str(error).splitlines()[0]


def switched_off(out) -> None:
    section("nxstress.enable: false")
    path = out / "enable.nxs"
    ws = synthetic_workspace([1, 2, 3])
    with NXstress(path, "w") as nx:
        nx.write([ws], [[synthetic_peaks(ws)]])

    print(f"  load filter, on:  {load_file_filter('H5 (*.h5)')!r}")
    with nxstress_config(enable=False):
        print(f"  load filter, off: {load_file_filter('H5 (*.h5)')!r}")
        check("the load dialogs no longer offer .nxs", "nxs" not in load_file_filter("H5 (*.h5)"))
        check("Save as NXstress... is unavailable", not nxstress_save_available(ws))

        try:
            read_single_workspace(path)
            message = None
        except NXstressDisabled as error:
            message = first_line(error)
        print(f"  PeakFitting / Texture load -> NXstressDisabled: {message}")
        check("the single-workspace viewers' load is refused", message is not None)

        viewer = Model()
        reported: list = []
        viewer.failureMsg.connect(lambda *args: reported.append(args[1]))
        loaded = viewer.load_nxstress(str(path))
        print(f"  strain/stress Load NXstress -> {loaded}, reported: {reported[0] if reported else None}")
        check("the strain/stress viewer's load is refused and reported", not loaded and len(reported) == 1)

        try:
            viewer.save_as_nxstress(str(out / "never_written.nxs"))
            message = None
        except NXstressDisabled as error:
            message = first_line(error)
        print(f"  strain/stress Save as NXstress -> NXstressDisabled: {message}")
        check("the strain/stress viewer's save is refused", message is not None)
        check("nothing was written", not (out / "never_written.nxs").exists())


def run_number_default() -> None:
    section("nxstress.default_run_number")
    print(f"  shipped: {default_run_number()}")
    check("the shipped value is -1", default_run_number() == -1)
    collection = PeakCollection("Fe 110", "Gaussian", "Linear")
    print(f"  a PeakCollection built without a run number: runnumber = {collection.runnumber}")
    check("it takes the configured value", collection.runnumber == -1)
    with nxstress_config(default_run_number=7):
        check("an override is seen when called", PeakCollection("Fe 110", "Gaussian", "Linear").runnumber == 7)
    try:
        with config_override({"nxstress": {"default_run_number": 0}}):
            message = None
    except Exception as error:
        # The first line is a heading; the second names the key and the reason.
        message = " ".join(line.strip() for line in str(error).splitlines()[:2])
    print(f"  default_run_number: 0 -> {message}")
    check("0 is refused", message is not None)


def direction_by_default(out) -> None:
    section("discriminator_fields ships as [direction]")
    print(f"  shipped: {Config['nxstress.discriminator_fields']}")
    check("the shipped value is ['direction']", list(Config["nxstress.discriminator_fields"]) == ["direction"])
    path = out / "no_direction.nxs"
    ws = synthetic_workspace([1, 2, 3])
    with NXstress(path, "w") as nx:
        nx.write([ws], [[synthetic_peaks(ws)]])
    with h5py.File(path, "r") as f:
        recorded = [name.decode() for name in f["entry/peaks"].attrs["discriminator_fields"]]
        columns = "direction" in f["entry/peaks"]
    with NXstress(path, "r") as nx:
        workspaces, _ = nx.read()
    print(f"  a workspace with no direction: recorded fields {recorded}, direction column: {columns}")
    check("it records no boundary", recorded == [] and not columns)
    check("it reads back as one workspace", len(workspaces) == 1)


def main() -> None:
    out = output_dir()
    switched_off(out)
    override = out / "nxstress_off.yml"
    override.write_text("nxstress:\n  enable: false\n")
    print(f"  Left for the GUI steps: {override}")
    run_number_default()
    direction_by_default(out)


if __name__ == "__main__":
    run(main)
