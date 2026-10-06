"""
pyrs/utilities/NXstress/_input_data.py

Private service class for NeXus NXstress-compatible I/O.
This class provides I/O for the `input_data` `NXdata` subgroup.
"""

from nexusformat.nexus import NXdata, NXfield
import numpy as np

from pyrs.core.workspaces import HidraWorkspace
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import CHUNK_SHAPE, FIELD_DTYPE, growable, tail_append


"""
REQUIRED PARAMETERS FOR NXstress:
---------------------------------

NONE: 'input_data' (NXdata, group) is allowed by the NXstress schema, but it is optional.
"""


class _InputData:
    ########################################
    # ALL methods must be `classmethod`.  ##
    ########################################

    @classmethod
    @validate_call_
    def init_group(cls, wss: list[HidraWorkspace], data: NXdata | None = None):
        # Initialize the input-data group, concatenating the inputs in workspace order.

        # Raw data may not actually be loaded in the `HidraWorkspace`:
        #   in that case, just initialize an empty NXdata group.
        loaded = [bool(len(ws._raw_counts)) for ws in wss]
        if len(wss) > 1 and any(loaded) and not all(loaded):
            # A partial concatenation would produce a `scan_point` axis that is
            # neither every input's scan points nor one input's, and `readSubruns`
            # below compares it for exact equality -- so the file would be
            # unreadable rather than merely incomplete.
            raise RuntimeError(
                "NXstress._input_data: raw detector counts are loaded for some input workspaces "
                f"and not others (loaded={loaded}).\n"
                "  Load raw counts for every input, or for none of them."
            )

        per_workspace = [(ws, list(ws._raw_counts.keys())) for ws in wss if len(ws._raw_counts)]
        scan_points = [p for _, points in per_workspace for p in points]
        scans = (
            np.concatenate(
                [
                    np.stack([ws.get_detector_counts(p).astype(FIELD_DTYPE.FLOAT_DATA.value) for p in points])
                    for ws, points in per_workspace
                ]
            )
            if scan_points
            else np.empty((0, 0), dtype=FIELD_DTYPE.FLOAT_DATA.value)
        )

        if data is not None:
            # Append (spec 04c): grow both datasets in lockstep, after their current end.
            # Re-checked here as well as in the pre-flight pass, since this method is
            # reachable on its own.
            cls.validateAppend(wss, data)
            if scan_points:
                tail_append(data["detector_counts"], scans)
                tail_append(data["scan_point"], np.asarray(scan_points))
            return data

        data = NXdata()
        data["detector_counts"] = NXfield(scans, maxshape=(None, None), chunks=CHUNK_SHAPE(2))
        data["scan_point"] = NXfield(np.asarray(scan_points), **growable(1))

        # Set attributes for axes and signal
        data.attrs["signal"] = "detector_counts"
        data.attrs["axes"] = ["scan_point", "."]

        return data

    @classmethod
    def validateAppend(cls, wss: list[HidraWorkspace], data: NXdata) -> None:
        """Check incoming workspaces against an existing input-data group, without mutating it.

        An entry whose counts were never loaded holds a `(0, 0)` `detector_counts`,
        and appending real counts to it would leave the scan points already on disk
        with no data -- `readSubruns` compares the scan-point axis for exact
        equality, so the result is an unreadable entry rather than an incomplete
        one. The same rule `init_group` enforces across a single multi-workspace
        write, applied across the append boundary.

        Args:
            wss: Workspaces being appended.
            data: The target entry's existing `input_data` group.

        `detector_counts` is two-dimensional -- scan point by pixel -- and only
        the first axis grows, so a detector of a different size cannot be
        appended either.

        Raises:
            RuntimeError: If raw counts are present on one side and not the
                other, or if the pixel counts differ.
        """
        incoming_loaded = any(len(ws._raw_counts) for ws in wss)
        on_disk_loaded = data["detector_counts"].shape[0] > 0
        if on_disk_loaded != incoming_loaded:
            raise RuntimeError(
                f"NXstress._input_data: the target entry "
                f"{'has' if on_disk_loaded else 'does not have'} raw detector counts, while the "
                f"incoming workspaces {'do' if incoming_loaded else 'do not'}.\n"
                "  Load raw counts for both sides, or for neither."
            )
        if not incoming_loaded:
            return

        existing_pixels = int(data["detector_counts"].shape[1])
        for n, ws in enumerate(wss):
            for point in ws._raw_counts:
                incoming_pixels = int(np.asarray(ws.get_detector_counts(point)).shape[0])
                if incoming_pixels != existing_pixels:
                    raise RuntimeError(
                        f"NXstress._input_data: cannot append -- input workspace [{n}] has "
                        f"{incoming_pixels} detector pixel(s), the target entry {existing_pixels}.\n"
                        "  Only the scan-point axis grows on an append; the pixel axis is fixed "
                        "when the entry is written."
                    )
                break

    @classmethod
    @validate_call_
    def readSubruns(cls, ws: HidraWorkspace, data: NXdata, rows: np.ndarray | None = None):
        # Initialize `HidraWorkspace` detector_counts from input-data group.

        # TODO: append to the `HidraWorkspace`, if any detector_counts data already exists.
        scan_points = data["scan_point"].nxdata

        # An empty group means raw counts were not available when the file was written — nothing to load.
        if len(scan_points) == 0:
            return

        # A multi-workspace entry concatenates every input's counts into one
        # array; `rows` selects this workspace's slice of it. The exact-match
        # check below is what makes that slice meaningful, so it is applied to
        # the selection rather than skipped for it.
        if rows is not None:
            scan_points = scan_points[rows]

        # `HidraWorkspace` must already contain its `SampleLogs`, and scan-points must match.
        if ws.get_sub_runs() != scan_points:
            raise RuntimeError("not implemented: append or change detector_counts data on existing workspace")

        scans = data["detector_counts"].nxdata
        if rows is not None:
            scans = scans[rows]
        for n, p in enumerate(scan_points):
            ws.set_raw_counts(p, scans[n])
