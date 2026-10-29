import json
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from pyrs.dataobjects.fields import StressField, StrainField, ScalarFieldSample
from pyrs.core.stress_facade import StressFacade
from pyrs.core.summary_generator_stress import SummaryGeneratorStress
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode  # type: ignore
from pyrs.core.workspaces import HidraWorkspace
from pyrs.utilities.restorable_property import restore
from pyrs.utilities.NXstress.NXstress import NXstress
from pyrs.interface.nxstress_load import is_nxstress_file, require_nxstress_enabled
from pyrs.utilities.config import Config, default_run_number
from pyrs.utilities.convertdatatypes import to_text
from qtpy.QtCore import Signal, QObject  # type:ignore

#: The strain directions the viewer holds, in the order it lists them.
DIRECTIONS = ("11", "22", "33")


class Model(QObject):
    propertyUpdated = Signal(str)
    failureMsg = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._e11 = []
        self._e11_strain = None
        self._e22 = []
        self._e22_strain = None
        self._e33 = []
        self._e33_strain = None
        self._e11_peaks = []
        self._e22_peaks = []
        self._e33_peaks = []
        self._peakTags = []
        self._selectedPeak = None
        self._stress = None
        self._stress_facade = None
        self._stressCase = None
        self._youngs_modulus = None
        self._poisson_ratio = None
        self._d0 = None

    def set_workspaces(self, name, filenames):
        setattr(self, name, filenames)

    @property
    def e11(self):
        return self._e11

    @e11.setter
    def e11(self, filename):
        self._e11, self._e11_peaks = self.load_hidra_project_files(filename, "11")
        self._peakTags = list(self._e11_peaks[0].keys()) if len(self._e11_peaks) > 0 else []
        self.propertyUpdated.emit("peakTags")

    @property
    def e11_peaks(self):
        return self._e11_peaks

    @property
    def e22(self):
        return self._e22

    @e22.setter
    def e22(self, filename):
        self._e22, self._e22_peaks = self.load_hidra_project_files(filename, "22")
        if self._e22 and self.check_peak_for_direction("22"):
            self.create_strain("22")

    @property
    def e22_peaks(self):
        return self._e22_peaks

    @property
    def e33(self):
        return self._e33

    @e33.setter
    def e33(self, filename):
        self._e33, self._e33_peaks = self.load_hidra_project_files(filename, "33")
        if self._e33 and self.check_peak_for_direction("33"):
            self.create_strain("33")

    @property
    def e33_peaks(self):
        return self._e33_peaks

    @property
    def peakTags(self):
        return self._peakTags

    @property
    def selectedPeak(self):
        return self._selectedPeak

    @selectedPeak.setter
    def selectedPeak(self, tag):
        self._selectedPeak = tag
        for direction in ("11", "22", "33"):
            if getattr(self, f"e{direction}") and self.check_peak_for_direction(f"{direction}"):
                self.create_strain(direction)
        self.propertyUpdated.emit("selectedPeak")

    @property
    def d0(self):
        if self.stress_facade:
            try:
                return self.stress_facade.d_reference
            except Exception as e:
                self.failureMsg.emit("Reference d spacings are different on different directions", str(e), None)
                return None, dict()

    @property
    def stress(self):
        return self._stress

    @stress.setter
    def stress(self, stress):
        self._stress = stress
        if stress is None:
            self._stress_facade = None
        else:
            self._stress_facade = StressFacade(stress)

    @property
    def stress_facade(self):
        return self._stress_facade

    def create_strain(self, direction):
        print(getattr(self, f"e{direction}"))
        strain_list = [
            StrainField(hidraworkspace=ws, peak_collection=peak[self.selectedPeak])
            for ws, peak in zip(getattr(self, f"e{direction}"), getattr(self, f"e{direction}_peaks"))
        ]
        if len(strain_list) == 1:
            setattr(self, f"_e{direction}_strain", strain_list[0])
        else:
            setattr(self, f"_e{direction}_strain", sum(strain_list[1:], strain_list[0]))

    def check_peak_for_direction(self, direction):
        for peak in getattr(self, f"e{direction}_peaks"):
            if self.selectedPeak not in peak:
                return False
        return True

    def validate_selection(self, direction):
        if not getattr(self, f"e{direction}"):
            return f"e{direction} file hasn't been loaded"

        if not self.e11:
            return "e11 is not loaded, the peak tags from this file will be used"

        if not self.e11_peaks:
            return "e11 contains no peaks, fit peaks first"

        if not self.check_peak_for_direction(f"{direction}"):
            return f"Peak {self.selectedPeak} is not in e{direction}"

    def get_parameter_field(self, plot_param, direction):
        if plot_param == "strain":
            return getattr(self, f"_e{direction}_strain")
        elif plot_param == "d-reference":
            return getattr(self, f"_e{direction}_strain").get_d_reference()
        elif plot_param == "dspacing-center":
            return getattr(self, f"_e{direction}_strain").get_dspacing_center()
        else:
            return getattr(self, f"_e{direction}_strain").get_effective_peak_parameter(plot_param)

    def get_field(self, direction, plot_param, stress_case):
        try:
            if plot_param == "stress":
                self.stress.select(direction)
                return self._stress
            elif plot_param == "strain" and direction == "33" and stress_case == "In-plane stress":
                return self.stress.strain33
            else:
                return self.get_parameter_field(plot_param, direction)
        except Exception as e:
            self.failureMsg.emit(
                f"Failed to generate field for parameter {plot_param} in direction {direction}",
                str(e),
                traceback.format_exc(),
            )

    def calculate_stress(self, stress_case, youngModulus, poissonsRatio, d0):
        build_stress = False
        if self.stress is None or stress_case != self._stressCase:
            build_stress = True

        if build_stress:
            self.stress = StressField(
                self._e11_strain,
                self._e22_strain,
                self._e33_strain if stress_case == "diagonal" else None,
                youngModulus,
                poissonsRatio,
                stress_case,
            )
        else:
            if youngModulus != self._youngs_modulus:
                self._stress.youngs_modulus = youngModulus
            if poissonsRatio != self._poisson_ratio:
                self._stress.poisson_ratio = poissonsRatio

        if d0 is not None and (self._d0 is None or self._d0 != d0):
            if len(d0) == 5:  # ScalarFieldSample case
                self.stress_facade.d_reference = ScalarFieldSample("d0", *d0)
            else:
                self.stress_facade.d_reference = d0

        # cache values to compare if they are changed
        self._stressCase = stress_case
        self._youngs_modulus = youngModulus
        self._poisson_ratio = poissonsRatio
        self._d0 = d0

    def validate_d0_grid_data(self, x_grid, y_grid, z_grid, d0_grid, d0e_grid, default_d0, default_d0e):
        # get stress facade values to validate d0
        n_decimals = 3
        stress = self.stress

        # convert to pandas df for joins
        stress_stacked = np.column_stack(
            (stress.x.round(n_decimals), stress.y.round(n_decimals), stress.z.round(n_decimals))
        )

        grid_stacked = np.column_stack(
            (x_grid.round(n_decimals), y_grid.round(n_decimals), z_grid.round(n_decimals), d0_grid, d0e_grid)
        )

        stress_df = pd.DataFrame(stress_stacked, columns=["x", "y", "z"])
        grid_df = pd.DataFrame(grid_stacked, columns=["x", "y", "z", "d0", "d0e"])

        # left join to show differences between dfs
        full_df = stress_df.merge(grid_df, on=["x", "y", "z"], how="left")

        # logic to find missing data after join
        if not (full_df["d0"].isnull().values.any() or full_df["d0e"].isnull().values.any()):
            full_df.loc[np.isnan(full_df["d0"]), "d0"] = default_d0
            full_df.loc[np.isnan(full_df["d0e"]), "d0e"] = default_d0e
            return (
                1,
                full_df["x"].to_numpy(),
                full_df["y"].to_numpy(),
                full_df["z"].to_numpy(),
                full_df["d0"].to_numpy(),
                full_df["d0e"].to_numpy(),
            )

        elif full_df["d0"].isnull().values.all() or full_df["d0e"].isnull().values.all():
            return -1, None, None, None, None, None
        else:
            full_df.loc[np.isnan(full_df["d0"]), "d0"] = default_d0
            full_df.loc[np.isnan(full_df["d0e"]), "d0e"] = default_d0e
            return (
                0,
                full_df["x"].to_numpy(),
                full_df["y"].to_numpy(),
                full_df["z"].to_numpy(),
                full_df["d0"].to_numpy(),
                full_df["d0e"].to_numpy(),
            )

    def write_stress_to_csv(self, filename, detailed):
        try:
            stress_csv = SummaryGeneratorStress(filename, self._stress)
            if detailed:
                stress_csv.write_full_csv()
            else:
                stress_csv.write_summary_csv()
        except Exception as e:
            self.failureMsg.emit("Failed to write csv", str(e), traceback.format_exc())

    def get_default_csv_filename(self):
        runs = [
            [peak_collection.runnumber for peak_collection in getattr(self._stress, f"strain{d}").peak_collections]
            for d in ("11", "22", "33")
        ]
        runnumbers = []
        for runs in runs:
            for runnumber in runs:
                if runnumber != default_run_number():
                    runnumbers.append(str(runnumber))
        return "HB2B_{}_stress_grid_{}.csv".format("_".join(runnumbers), self.selectedPeak)

    def load_hidra_project_file(self, filename, direction):
        source_project = None
        try:
            source_project = HidraProjectFile(filename, mode=HidraProjectFileMode.READONLY)
            ws = HidraWorkspace(direction)
            # The workspace NAME has always carried the direction here, but `name` is
            # free text that other viewers use for other things. Record it on the
            # `direction` property too, which is what NXstress reads and restores.
            restore(ws, "direction", direction)
            # Reduced diffraction is loaded only for NXstress output, which writes a
            # diffractogram for every peak collection and refuses one without. The
            # viewer itself never reads it, so without NXstress it is not worth the memory.
            ws.load_hidra_project(source_project, False, bool(Config["nxstress.enable"]))
            # The direction is the user's assertion about which file is which, made
            # in the file-selection UI. If the project itself records one and the two
            # disagree, one of them is wrong and neither this model nor the viewer
            # can tell which -- so say so rather than silently preferring either.
            # `ws.direction` would answer with the restored value above, so the log
            # is read directly.
            if "direction" in ws.sample_log_names:
                recorded = to_text(ws.get_sample_log_value("direction"))
                if recorded != direction:
                    raise ValueError(
                        f"This file records direction '{recorded}', but it was selected as the "
                        f"'{direction}' direction.\n"
                        "  Load it under the direction it records, or correct the file."
                    )
            peaks = dict()
            for peak in source_project.read_peak_tags():
                peaks[peak] = source_project.read_peak_parameters(peak)
            return ws, peaks
        except Exception as e:
            self.failureMsg.emit(
                f"Failed to load {filename}. Check that this is a Hidra Project File", str(e), traceback.format_exc()
            )
            return None, dict()
        finally:
            # Closed explicitly, as every other project-file load does, rather than
            # left to garbage collection; everything above reads eagerly.
            if source_project is not None:
                source_project.close()

    def load_hidra_project_files(self, filenames, direction):
        # remove existing stress as it will need to be recreated
        self.stress = None

        workspaces = []
        peaks = []
        if isinstance(filenames, str):
            filenames = [filenames]
        for filename in filenames:
            ws, p = self.load_hidra_project_file(filename, direction)
            if ws is None:
                return [], []
            workspaces.append(ws)
            if p:
                peaks.append(p)

        return workspaces, peaks

    def save_as_nxstress(self, filename: str) -> None:
        """Write every loaded direction to one NXstress file, in one `NXentry`.

        Each loaded workspace -- one per project file, so a direction loaded from
        two runs contributes two -- is written with its own peak collections. They
        are told apart on read by `direction`, which `load_hidra_project_file`
        records on each workspace, and by run number: every run numbers its scan
        points from 1, and NXstress keys each scan point by `(run, scan point)`.

        Raises rather than reporting through `failureMsg`: the viewer writes
        through `gui_helper.write_nxstress_or_report`, which reports the failure
        and leaves any existing file at `filename` untouched.

        Args:
            filename: The `.nxs` file to write. The viewer has already imposed the
                configured extension.

        Raises:
            NXstressDisabled: If NXstress I/O is switched off (`nxstress.enable`).
            RuntimeError: If `direction` is not among `nxstress.discriminator_fields`
                -- without it the directions would be refused as several
                workspaces with no recorded boundary -- or if nothing is loaded.
            ValueError: If a loaded file has no fitted peaks: a direction
                contributes a workspace only together with its peak collections.
        """
        require_nxstress_enabled()
        if "direction" not in Config["nxstress.discriminator_fields"]:
            raise RuntimeError(
                "Saving strain/stress data as NXstress needs 'direction' in the "
                "'nxstress.discriminator_fields' configuration, which tells the directions apart "
                f"in the file; it is {Config['nxstress.discriminator_fields']}.\n"
                "  Add 'direction' to that setting, or save as JSON state instead."
            )

        workspaces: list[HidraWorkspace] = []
        peakss: list = []
        for direction in DIRECTIONS:
            loaded = getattr(self, f"e{direction}")
            peaks = getattr(self, f"e{direction}_peaks")
            # `load_hidra_project_files` keeps a file's peaks only when it has some,
            # so the two lists are paired only when every file had fitted peaks.
            if len(peaks) != len(loaded):
                raise ValueError(
                    f"Direction {direction}: {len(loaded) - len(peaks)} of its {len(loaded)} file(s) "
                    "have no fitted peaks, and NXstress records a direction only through its peaks.\n"
                    "  Fit peaks first, or remove those files."
                )
            workspaces.extend(loaded)
            peakss.extend(list(collections.values()) for collections in peaks)

        if not workspaces:
            raise RuntimeError("Nothing to save: no direction has been loaded.")

        with NXstress(Path(filename), "w") as nx:
            nx.write(workspaces, peakss)

    def load_nxstress(self, filename: str) -> bool:
        """Load every direction from one NXstress file written by `save_as_nxstress`.

        Each workspace in the file goes to the direction it records, replacing
        whatever that direction held; a direction the file does not hold is
        emptied. Strains are rebuilt as they are after loading project files
        direction by direction.

        A file is not a `HidraProjectFile`, so this is separate from
        `load_hidra_project_files` rather than a branch inside it.

        Args:
            filename: The `.nxs` file to read.

        Returns:
            True if the file was loaded. False if it was refused or failed to
            read; the reason has been reported through `failureMsg`, and nothing
            the model held has changed.
        """
        try:
            slots = self._read_nxstress_slots(filename)
        except Exception as e:
            self.failureMsg.emit(
                f"Failed to load {filename}. Check that this is an NXstress file written by the strain/stress viewer",
                str(e),
                traceback.format_exc(),
            )
            return False

        # remove existing stress as it will need to be recreated
        self.stress = None
        for direction, (loaded, peaks) in slots.items():
            setattr(self, f"_e{direction}", loaded)
            setattr(self, f"_e{direction}_peaks", peaks)
            setattr(self, f"_e{direction}_strain", None)

        # The same order as loading direction by direction: peak tags come from e11,
        # then the other directions build their strains for the selected peak.
        self._peakTags = list(self._e11_peaks[0].keys()) if self._e11_peaks else []
        self.propertyUpdated.emit("peakTags")
        for direction in DIRECTIONS:
            if getattr(self, f"e{direction}") and self.check_peak_for_direction(direction):
                self.create_strain(direction)
        return True

    @staticmethod
    def _read_nxstress_slots(filename: str) -> dict[str, tuple[list, list]]:
        """Every workspace of an NXstress file, sorted into the direction it records.

        Args:
            filename: The `.nxs` file to read.

        Returns:
            For each of `DIRECTIONS`, `(workspaces, peaks)` in the shape the model
            holds a direction in: one `{peak_tag: PeakCollection}` per workspace.
            A direction the file does not hold has two empty lists.

        Raises:
            NXstressDisabled: If NXstress I/O is switched off (`nxstress.enable`).
            RuntimeError: If the file holds more than one `NXentry`.
            ValueError: If a workspace records no direction, or one the viewer
                does not hold.
        """
        require_nxstress_enabled()
        with NXstress(Path(filename), "r") as nx:
            entries = nx.entry_numbers()
            if len(entries) != 1:
                raise RuntimeError(
                    f"'{Path(filename).name}' holds {len(entries)} NXentry groups, and the strain/stress "
                    "viewer reads one: nothing in PyRS writes more than one yet."
                )
            workspaces, peakss = nx.read()

        slots: dict[str, tuple[list, list]] = {direction: ([], []) for direction in DIRECTIONS}
        for ws, collections in zip(workspaces, peakss):
            # Raises `ValueError` for a workspace that records no direction.
            direction = ws.direction
            if direction not in slots:
                raise ValueError(f"A workspace in this file records direction '{direction}', not one of {DIRECTIONS}.")
            slots[direction][0].append(ws)
            slots[direction][1].append({collection.peak_tag: collection for collection in collections})
        return slots

    def _restore_direction(self, direction: str, filenames: list[str], *, nxstress_slots: dict) -> None:
        """Load one direction from the files a saved state lists for it.

        A project file loads as it always has, through the direction's setter. An
        NXstress file contributes the workspaces it holds for *this* direction: a
        state saved after an NXstress load lists the `.nxs` once per workspace, so
        each distinct file is taken once. Mixed lists are loaded file by file, in
        order.

        A file that cannot be loaded is reported through `failureMsg` and leaves
        the direction empty, as a failed project-file load does.

        Args:
            direction: One of `DIRECTIONS`.
            filenames: The files the state lists for it.
            nxstress_slots: NXstress files already read during this restore, by
                name, so that one listed for several directions is read once.
        """
        if not any(is_nxstress_file(filename) for filename in filenames):
            self.set_workspaces(f"e{direction}", filenames)
            return

        # remove existing stress as it will need to be recreated
        self.stress = None
        workspaces: list = []
        peaks: list = []
        for filename in dict.fromkeys(filenames):
            if is_nxstress_file(filename):
                try:
                    if filename not in nxstress_slots:
                        nxstress_slots[filename] = self._read_nxstress_slots(filename)
                    loaded, loaded_peaks = nxstress_slots[filename][direction]
                    if not loaded:
                        raise ValueError(f"'{Path(filename).name}' holds no workspace for direction {direction}.")
                except Exception as e:
                    self.failureMsg.emit(
                        f"Failed to load {filename} for direction {direction}", str(e), traceback.format_exc()
                    )
                    workspaces, peaks = [], []
                    break
                workspaces.extend(loaded)
                peaks.extend(loaded_peaks)
            else:
                ws, p = self.load_hidra_project_file(filename, direction)
                if ws is None:
                    workspaces, peaks = [], []
                    break
                workspaces.append(ws)
                if p:
                    peaks.append(p)

        setattr(self, f"_e{direction}", workspaces)
        setattr(self, f"_e{direction}_peaks", peaks)
        setattr(self, f"_e{direction}_strain", None)
        if direction == "11":
            # As the e11 setter does: the peak tags on offer come from e11.
            self._peakTags = list(peaks[0].keys()) if peaks else []
            self.propertyUpdated.emit("peakTags")

    def get_filenames_for_direction(self, direction):
        return [w.hidra_project_file for w in getattr(self, f"e{direction}")]

    def to_json(self, filename):
        try:
            json_output = dict()
            json_output["stress_case"] = self._stressCase
            json_output["filenames_11"] = self.get_filenames_for_direction("11")
            json_output["filenames_22"] = self.get_filenames_for_direction("22")
            json_output["filenames_33"] = self.get_filenames_for_direction("33")
            json_output["peak_tag"] = self.selectedPeak
            json_output["youngs_modulus"] = self._youngs_modulus
            json_output["poisson_ratio"] = self._poisson_ratio
            if self._d0 is None:
                json_output["d0"] = None
            elif len(self._d0) == 5:  # ScalarFieldSample case
                json_output["d0"] = {
                    "d0": self._d0[0],
                    "d0_error": self._d0[1],
                    "vx": self._d0[2],
                    "vy": self._d0[3],
                    "vz": self._d0[4],
                }
            else:
                json_output["d0"] = {"d0": self._d0[0], "d0_error": self._d0[1]}

            with open(filename, "w") as f:
                json.dump(json_output, f)
        except Exception as e:
            self.failureMsg.emit(f"Failed save json file to {filename}", str(e), traceback.format_exc())

    def from_json(self, filename):
        with open(filename) as f:
            data = json.load(f)

        self._selectedPeak = data["peak_tag"]

        nxstress_slots: dict = {}
        for direction in ("11", "22", "33"):
            self._restore_direction(direction, data[f"filenames_{direction}"], nxstress_slots=nxstress_slots)
            if getattr(self, f"e{direction}"):
                self.create_strain(direction)

        d0_data = data["d0"]
        if d0_data is None:
            d0 = None
        elif len(d0_data) == 2:
            d0 = (d0_data["d0"], d0_data["d0_error"])
        else:
            d0 = (d0_data["d0"], d0_data["d0_error"], d0_data["vx"], d0_data["vy"], d0_data["vz"])

        stress_case = data["stress_case"]
        directions = DIRECTIONS if stress_case == "diagonal" else DIRECTIONS[:2]
        if all(self.validate_selection(direction) is None for direction in directions):
            self.calculate_stress(stress_case, data["youngs_modulus"], data["poisson_ratio"], d0)
        else:
            # A direction failed to load, which has been reported. As in the window,
            # stress waits for complete inputs; the constants still restore to the form.
            # d0 is not cached: `calculate_stress` skips a d0 equal to the cached one,
            # so a later stress would be built without it.
            self._stressCase = stress_case
            self._youngs_modulus = data["youngs_modulus"]
            self._poisson_ratio = data["poisson_ratio"]

        self.propertyUpdated.emit("modelUpdated")

    @property
    def modelUpdated(self):
        return self._stressCase, self.selectedPeak, self._youngs_modulus, self._poisson_ratio
