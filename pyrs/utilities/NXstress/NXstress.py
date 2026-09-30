"""
pyrs/utilities/NXstress/NXstress.py

Primary service class for NeXus NXstress-compatible I/O.
"""

from datetime import datetime
from nexusformat.nexus import NXdata, NXentry, NXfield, NXFile, nxopen
from pathlib import Path

from pyrs.core.workspaces import HidraWorkspace
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import (
    DEFAULT_TAG,
    GROUP_NAME,
    group_naming_scheme,
    NO_LOG,
    suffix_from_group_name,
    logger,
    REQUIRED_LOGS,
)
from ._input_data import _InputData
from ._instrument import _Instrument, _Masks
from ._sample import _Sample
from ._fit import _Fit, _Diffractogram
from ._peaks import _Peaks, IndexedPeaks
from . import _discriminator

import numpy as np


"""
REQUIRED PARAMETERS FOR NXstress:
---------------------------------

/<entryname>                               (NXentry, group)
│
├─ definition                                (dataset: "NXstress")
├─ start_time                                (dataset: ISO8601 string)
├─ end_time                                  (dataset: ISO8601 string)
├─ processingtype                            (dataset: string)
│
├─ instrument                             (NXinstrument, group)
│   ├─ name                                 (dataset: string)
│   ├─ source                               (NXsource, group)
│   ├─ detector                             (NXdetector, group)
│   └─ mask (optional)                      (NXcollection, group)
│
├─ sample                                 (NXsample, group)
│   ├─ name                                 (dataset: string)
│   ├─ chemical_formula (optional)          (dataset: string)
│   ├─ temperature (optional)               (dataset: string)
│   ├─ stress_field (optional)              (dataset: string)
│   └─ gauge_volume (optional)              (NXparameters, group)
│
├─ fit                                    (NXprocess, group)
│   ├─ @date                                (attribute: ISO8601 string)
│   ├─ @program                             (attribute: string)
│   ├─ description                          (NXnote, group)
│   ├─ peakparameters                       (NXparameters, group)
│   └─ diffractogram                        (NXdata, group)
│        ├─ diffractogram                     (dataset)
│        ├─ diffractogram_errors              (dataset)
│        ├─ daxis/xaxis                       (dataset)
│        ├─ @axes                             (attribute: string)
│        └─ @signal                           (attribute: string)
│
├─ peaks                                  (NXreflections, group)
│   ├─ h                                    (dataset)
│   ├─ k                                    (dataset)
│   ├─ l                                    (dataset)
│   └─ phase_name                           (dataset)
"""


class NXstress:
    ##################################################################
    ## Service class to write NXstress-compliant NXentries:         ##
    ##   the `write` method writes the next `NXentry` to the file.  ##
    ##################################################################

    ## Context-manager related methods:
    def __init__(self, file_path: Path, mode: str = "r"):
        self._path = str(file_path)
        self._mode = mode
        self._nx = NXFile(self._path, self._mode)  # low-level handle
        self._root = None  # will *ONLY* be set in __enter__

    def __enter__(self) -> "NXstress":
        self._root = nxopen(self._path, self._mode)
        if self._root is None:
            raise RuntimeError(
                f"Unexpected `nexusformat` error opening '{self._path}' "
                f"for {'read' if 'r' in self._mode else 'write'}."
            )
        self._root.__enter__()

        return self

    def __exit__(self, exc_type, exc, tb):
        if self._root:
            self._root.__exit__(exc_type, exc, tb)
            self._root = None

        # Do not suppress exceptions
        return False

    def write(self, wss: list[HidraWorkspace], peakss: list[list[PeakCollection]]):
        # Write the _next_ NXentry to the file:
        #
        # -- multiple NXentry are allowed by the NXstress schema.
        # -- each NXentry includes:
        #
        #   -- [optional] input_data: raw detector counts, indexed by 'scan_point' (aka: 'subrun');
        #   -- the `NXinstrument`, including its `NXdetector`, applicable `NXtransformations`
        #      and detector and solid-angle masks;
        #   -- a canonical PEAKS instance:
        #
        #      -- peaks are indexed by: phase, (h, k, l), mask, <scan point>
        #         (no duplicate entries are allowed)
        #
        #   -- reduced 'diffraction_data' sections corresponding to the PEAKS entries:
        #
        #     -- peak-fit details, indexed as for the PEAKS indices;
        #     -- normalized and reduced data for each mask, indexed by 'scan_point';
        #     -- a calculated model spectrum: this section is still in progress.
        #

        #   -- more than one `HidraWorkspace` may share one NXentry: their rows are
        #      concatenated in workspace order, and the boundary between them is
        #      recovered on read from the discriminator columns named by
        #      `nxstress.discriminator_fields` (see `_discriminator.py`).

        ######################################################
        ## Recommended usage:                               ##
        ## -------------------------------------------------##
        ## from pyrs/utilities/NXstress import NXstress     ##
        ## ...                                              ##
        ## wss: list[HidraWorkspace]                        ##
        ## peakss: list[list[PeakCollection]]               ##
        ##   -- one inner list per workspace, same order.   ##
        ## ...                                              ##
        ## # To write the first (, or only) entry:          ##
        ## with NXstress(<file name>.nxs, 'w') as nxS:      ##
        ##     nxS.write([ws], [peaks])                     ##
        ## -------------------------------------------------##
        ## # A workspace with no peak fits at all:          ##
        ##     nxS.write([ws], [[]])                        ##
        ## -------------------------------------------------##
        ## # To write an additional entry:                  ##
        ## # alternatively, this could have been done       ##
        ## # in the first `with` clause above.              ##
        ## with NXfile(<same file name>.nxs, 'a') as nxS:   ##
        ##     nxS.write([ws], [peaks])                     ##
        ######################################################

        if self._root is None:
            raise RuntimeError("Usage error: only usage as context manager is supported!")
        entry_number = len(self._root.NXentry) + 1
        entry_name = group_naming_scheme(GROUP_NAME.ENTRY, entry_number)
        if entry_name in self._root:
            raise RuntimeError(f"Not implemented: overwriting existing `NXentry` '/{entry_name}'.")

        entry = self.init_group(wss, peakss)
        self._root[entry_name] = entry

    def read(self, entry_number: int = 1):
        """Read back the workspaces and peak collections of one NXstress NXentry.

        Parameters
        ----------
        entry_number : int
            Which NXentry to read (1-based). Default is 1.

        Returns
        -------
        tuple
            `(list[HidraWorkspace], list[list[PeakCollection]])`, parallel and
            in the same order -- the same shape `write` accepts. An entry
            written from one workspace, or written with
            `nxstress.merge_workspaces`, yields one of each.

        Raises
        ------
        RuntimeError
            If the entry's discriminator columns disagree with
            `nxstress.discriminator_fields`, or if the recovered scan-point
            sets do not partition the entry's scan-point axis.
        """
        # Verify context manager is active
        if self._root is None:
            raise RuntimeError("Usage error: only usage as context manager is supported!")

        # Resolve entry name
        entry_name = group_naming_scheme(GROUP_NAME.ENTRY, entry_number)

        # Access entry
        entry = self._root[entry_name]

        # Read peak collections FIRST: in a multi-workspace entry they are the
        # only record of where one workspace's rows end and the next begin, so
        # nothing else can be split until they have been read and grouped.
        indexed = []
        discriminator_names: tuple = ()
        if GROUP_NAME.PEAKS in entry:
            peaks_group = entry[GROUP_NAME.PEAKS]
            discriminator_names = _discriminator.names_for_read(peaks_group)
            if GROUP_NAME.FIT in entry:
                indexed = _Peaks.peakCollectionsFromNexus(peaks_group, entry[GROUP_NAME.FIT], discriminator_names)

        scan_point_axis = entry[GROUP_NAME.SAMPLE_DESCRIPTION]["scan_point"].nxdata
        selections = self._workspaceSelections(indexed, scan_point_axis, discriminator_names)

        # Instrument geometry, detector shift and masks are entry-wide.
        default_mask, mask_dict = _Masks.masksFromNexus(entry[GROUP_NAME.INSTRUMENT][GROUP_NAME.MASKS])

        workspaces = []
        peak_collections = []
        for rows, discriminators, collections in selections:
            ws = self._workspaceFromNexus(entry, rows, default_mask, mask_dict)
            for name, value in discriminators:
                _discriminator.apply(ws, name, value)
            workspaces.append(ws)
            peak_collections.append(collections)

        return workspaces, peak_collections

    @classmethod
    def _workspaceSelections(cls, indexed, scan_point_axis, discriminator_names: tuple):
        """Split one entry into per-workspace (rows, discriminators, collections).

        Each workspace's scan-point *set* is the union of its peak collections'
        scan points, and its rows of the scan-point family are selected by
        membership in that set -- not by position. That is what makes the read
        independent of the order `write` happened to concatenate the inputs in.

        Returns
        -------
        list[tuple]
            `(rows, discriminators, collections)` per workspace, where `rows` is
            a boolean mask over `scan_point_axis`, or `None` for a
            single-workspace entry (which needs no selection at all).
        """
        groups: dict = {}
        for item in indexed:
            groups.setdefault(item.discriminators, []).append(item.collection)

        if not discriminator_names or len(groups) <= 1:
            # One workspace: a pre-04b file, a single-workspace write, or a
            # `merge_workspaces` write, all of which read back whole -- no rows
            # need selecting. Its discriminators are still carried through, so a
            # single-workspace save round-trips its value like any other.
            discriminators, collections = next(iter(groups.items())) if groups else ((), [])
            return [(None, discriminators, collections)]

        selections = []
        claimed = np.zeros(len(scan_point_axis), dtype=bool)
        for discriminators, collections in groups.items():
            points = set()
            for collection in collections:
                points |= set(collection.sub_runs.raw_copy().tolist())
            rows = np.isin(scan_point_axis, sorted(points))
            overlap = claimed & rows
            if overlap.any():
                raise RuntimeError(
                    f"NXstress: scan points {sorted(set(np.asarray(scan_point_axis)[overlap].tolist()))} "
                    f"are claimed by more than one workspace in this entry "
                    f"(at {dict(discriminators)}).\n"
                    "  Input workspaces must cover disjoint scan points; this file cannot be split."
                )
            claimed |= rows
            selections.append((rows, discriminators, collections))

        if not claimed.all():
            unclaimed = sorted(set(np.asarray(scan_point_axis)[~claimed].tolist()))
            raise RuntimeError(
                f"NXstress: scan points {unclaimed} belong to no workspace in this entry.\n"
                "  Every scan point must be covered by some input workspace's `PeakCollection`s."
            )
        return selections

    @classmethod
    def _workspaceFromNexus(cls, entry, rows, default_mask, mask_dict) -> HidraWorkspace:
        """Reconstruct one `HidraWorkspace` from its rows of a (possibly shared) entry."""
        # Read sample logs. `rows` is applied inside, before any `SubRuns` is
        # built: the entry's concatenated scan-point axis need not be
        # monotonic, and `SubRuns` rejects a non-monotonic array outright.
        sample_logs = _Sample.sampleLogsFromNexus(entry[GROUP_NAME.SAMPLE_DESCRIPTION], rows)

        # Read instrument
        geometry, shift, wavelength = _Instrument.instrumentFromNexus(entry[GROUP_NAME.INSTRUMENT], rows)
        is_calibrated = shift is not None

        # Build workspace
        ws = HidraWorkspace()
        ws.set_sample_logs_from_object(sample_logs)
        # `set_wavelength` expects `dict[int, float]`
        ws.set_wavelength(
            {subrun_index: wavelength[n] for n, subrun_index in enumerate(ws.get_sub_runs())}, is_calibrated
        )
        ws.set_instrument_geometry(geometry)
        if shift is not None:
            ws.set_detector_shift(shift)
        ws.set_masks_from_dict(default_mask, mask_dict)

        # Read raw counts if present
        if GROUP_NAME.INPUT_DATA in entry:
            _InputData.readSubruns(ws, entry[GROUP_NAME.INPUT_DATA], rows)

        # Read reduced diffraction data from FIT group's DIFFRACTOGRAM subgroups
        if GROUP_NAME.FIT in entry:
            fit_group = entry[GROUP_NAME.FIT]
            diff_data = {}
            var_data = {}
            two_theta_matrix = None

            for child_name in fit_group:
                child = fit_group[child_name]
                if not isinstance(child, NXdata):
                    continue
                mask_name = suffix_from_group_name(child_name, GROUP_NAME.DIFFRACTOGRAM)
                scan_pts, two_theta, data, errors = _Diffractogram.diffractogramFromNexus(child, rows)

                # Map DEFAULT_TAG to None for workspace dict keys
                ws_mask_key = None if mask_name == DEFAULT_TAG else mask_name
                diff_data[ws_mask_key] = data

                # NOTE: Despite the field name 'diffractogram_errors',
                #   variance values (not standard errors) are stored in this field.
                var_data[ws_mask_key] = errors

                if two_theta_matrix is None:
                    two_theta_matrix = two_theta

            if two_theta_matrix is not None:
                ws.set_reduced_diffraction_data_set(two_theta_matrix, diff_data, var_data)

        return ws

    ############################################
    # ALL non-context-manager related methods ##
    #   must be `classmethod`.                ##
    ############################################

    @classmethod
    def _validateWorkspaceAndPeaksData(
        cls, wss: list[HidraWorkspace], peakss: list[list[PeakCollection]], indexed: list
    ):
        if len(peakss) != len(wss):
            raise ValueError(
                f"NXstress.write expects one list of `PeakCollection` per workspace: "
                f"got {len(wss)} workspace(s) and {len(peakss)} peak list(s)."
            )
        if not wss:
            raise ValueError("NXstress.write requires at least one `HidraWorkspace`.")

        for n, ws in enumerate(wss):
            # VERIFY that all required logs are present.
            logs = ws.sample_log_names
            for k in REQUIRED_LOGS:
                if k not in logs:
                    raise ValueError(f"NXstress requires log '{k}', which is not present in workspace [{n}]")

        if len(wss) > 1:
            cls._validateMultiWorkspace(wss, peakss)

        # VERIFY that no duplicate PeakCollections exist
        _Peaks.validateNoDuplicatePeaks(indexed)

        # VERIFY that any <scan point> or <mask> referenced by any `PeakCollection` is included in the workspace.
        for ws, peaks in zip(wss, peakss):
            _Fit.validateWorkspaceAndPeaksData(ws, peaks)

    @classmethod
    def _validateMultiWorkspace(cls, wss: list[HidraWorkspace], peakss: list[list[PeakCollection]]):
        """The three invariants that only bite when an entry holds N > 1 workspaces.

        Each is a write-time gate rather than a documented convention, because
        violating any of them produces a file that is *readable* and wrong
        rather than one that fails: an unsplittable entry, or one whose rows
        are attributed to the wrong workspace.
        """
        # 1. Without a discriminator, the boundary between inputs is not recorded
        #    anywhere -- so merging them must be an explicit choice.
        if not _discriminator.field_names() and not _discriminator.merge_workspaces():
            raise ValueError(
                f"NXstress.write was given {len(wss)} workspaces, but "
                "'nxstress.discriminator_fields' names no field, so they could not be told apart "
                "when the file is read.\n"
                "  Configure a discriminator field, or set 'nxstress.merge_workspaces: true' to "
                "merge them indistinguishably on purpose."
            )

        # 2. A workspace contributing no `PeakCollection` has no discriminator
        #    value on disk, and therefore no recoverable scan-point set.
        empty = [n for n, peaks in enumerate(peakss) if not peaks]
        if empty:
            raise ValueError(
                f"NXstress.write: input workspace(s) {empty} contribute no `PeakCollection`.\n"
                "  With more than one workspace in an entry, every workspace must contribute at "
                "least one -- the peak index is the only place a workspace's identity is recorded, "
                "so one with no peaks cannot be recovered on read."
            )

        # 3. The read side recovers each workspace by scan-point value membership,
        #    which cannot distinguish two workspaces that share a scan point.
        seen: dict = {}
        for n, ws in enumerate(wss):
            for point in ws.get_sub_runs().raw_copy().tolist():
                if point in seen:
                    raise ValueError(
                        f"NXstress.write: scan point {point} appears in both input workspace "
                        f"[{seen[point]}] and [{n}].\n"
                        "  Input workspaces sharing an entry must cover disjoint scan points: the "
                        "reader recovers each workspace's rows by scan-point value, so an overlap "
                        "cannot be attributed."
                    )
                seen[point] = n

    @classmethod
    @validate_call_
    def _init(cls, wss: list[HidraWorkspace]) -> NXentry:
        # Create the NXentry and initialize any required attributes.

        """
        ├─ definition                             (dataset: "NXstress")
        ├─ start_time                             (dataset: ISO8601 string)
        ├─ end_time                               (dataset: ISO8601 string)
        ├─ processing_type                        (dataset: string)
        :: apart from 'definition', these fields may also be
             lists by subrun.
        """
        entry = NXentry()
        entry["definition"] = "NXstress"

        # lists of 'start_time', 'end_time' for all subruns, concatenated across inputs
        n_scan_point = sum(len(ws._sample_logs.subruns) for ws in wss)
        try:
            start_times: list[str] = [
                datetime.fromisoformat(t.decode("utf-8")).astimezone().isoformat()
                for ws in wss
                for t in ws.get_sample_log_values("start_time")
            ]
            end_times: list[str] = [
                datetime.fromisoformat(t.decode("utf-8")).astimezone().isoformat()
                for ws in wss
                for t in ws.get_sample_log_values("end_time")
            ]
        except ValueError as e:
            if "Invalid isoformat string" not in str(e):
                raise
            logger.warning(
                f"Log entries for sub-run start and end times are not in ISO-8601 format:\n"
                f"  in order to continue writing, a value of '{NO_LOG}' will be used for all time entries!"
            )
            start_times = end_times = [NO_LOG] * n_scan_point
        entry["start_time"] = NXfield(start_times)
        entry["end_time"] = NXfield(end_times)

        # the type of the primary strain calculation:
        #   this might also be 'two-theta', but 'd-spacing' seems more likely
        entry["processing_type"] = "d-spacing"

        return entry

    @classmethod
    def _discriminatorNames(cls, wss: list[HidraWorkspace]) -> tuple:
        """Discriminator fields to write this entry with.

        Whenever any field is configured, its column is written -- `N == 1`
        included. That keeps the read-side cross-check a plain equality test,
        and lets a single-workspace save round-trip its discriminator value
        the same way a multi-workspace one does.
        """
        if _discriminator.merge_workspaces() and len(wss) > 1 and not _discriminator.field_names():
            return ()
        return _discriminator.field_names()

    @classmethod
    @validate_call_
    def init_group(cls, wss: list[HidraWorkspace], peakss: list[list[PeakCollection]]) -> NXentry:
        # Create and initialize a single NXstress-compatible NXentry tree:
        #   _multiple_ NXentry can exist within an NXstress-compatible HDF5 file.
        #   For example, distinct entries might be added for each set of
        #   data-reduction or sample conditions.
        #
        #   One NXentry may also hold _multiple_ `HidraWorkspace`: their rows are
        #   concatenated in workspace order throughout, and told apart on read by
        #   the discriminator columns on the peak index.

        discriminator_names = cls._discriminatorNames(wss)

        # One flattened list of peak collections, each tagged with its own
        # workspace's discriminator values and sample logs. This is what keeps
        # the three position-aligned groups (PEAKS, peak parameters, background
        # parameters) in the same order as each other.
        indexed = [
            IndexedPeaks(_discriminator.key(ws, discriminator_names), collection, ws._sample_logs)
            for ws, collections in zip(wss, peakss)
            for collection in collections
        ]

        # Verify that all data required by NXstress are present.
        cls._validateWorkspaceAndPeaksData(wss, peakss, indexed)

        # Initialize this NXentry, and add required attributes.
        entry = cls._init(wss)

        # 'input_data' group
        entry[GROUP_NAME.INPUT_DATA] = _InputData.init_group(wss)

        # 'instrument' group
        entry[GROUP_NAME.INSTRUMENT] = _Instrument.init_group(wss)

        # 'SAMPLE_DESCRIPTION' group
        logss = [ws._sample_logs for ws in wss]
        entry[GROUP_NAME.SAMPLE_DESCRIPTION] = _Sample.init_group(logss)

        # 'FIT' group
        entry[GROUP_NAME.FIT] = _Fit.init_group(wss, indexed, logss)

        # 'PEAKS' group
        entry[GROUP_NAME.PEAKS] = _Peaks.init_group(indexed, logss[0], discriminator_names)

        return entry
