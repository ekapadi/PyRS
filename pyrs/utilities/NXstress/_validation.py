"""
pyrs/utilities/NXstress/_validation.py

Write-time validation of the workspaces and peak collections given to `NXstress`.

Everything here runs before anything is written, and raises rather than writing a
file that would be readable and wrong. An append runs the same checks on its
incoming batch (`_append.run_checks`) before its own.

Typical workflow:

1. `validate_entry_number(n)` refuses an entry number that is not 1-based.
2. `validate_inputs(wss, peakss, indexed)` checks one write's inputs, and through
   `validate_multi_workspace` the invariants that bind only when an entry holds
   more than one workspace.
3. `refuse_unreadable_scan_point_order(...)` refuses an entry whose workspaces
   could not be read back, for write and append alike.
"""

import numpy as np

from pyrs.core.workspaces import HidraWorkspace
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import REQUIRED_LOGS
from ._fit import _Fit
from ._peaks import _Peaks
from . import _discriminator, _runs, _workspace_key
from ._workspace_key import WorkspaceKey


def validate_entry_number(entry_number: int) -> None:
    """Refuse an entry number below 1: entries are numbered from 1."""
    if entry_number < 1:
        raise ValueError(f"NXstress: `entry_number` is 1-based; got {entry_number}.")


@validate_call_
def validate_inputs(wss: list[HidraWorkspace], peakss: list[list[PeakCollection]], indexed: list) -> None:
    """Check one write's inputs: their shapes, required logs, and peak collections against workspaces.

    Raises:
        ValueError: Naming the first violated requirement.
    """
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
        validate_multi_workspace(wss, peakss)

    # VERIFY that no duplicate PeakCollections exist
    _Peaks.validateNoDuplicatePeaks(indexed)

    # VERIFY that any <scan point> or <mask> referenced by any `PeakCollection` is included in the workspace.
    for ws, peaks in zip(wss, peakss):
        _Fit.validateWorkspaceAndPeaksData(ws, peaks)


def validate_multi_workspace(wss: list[HidraWorkspace], peakss: list[list[PeakCollection]]) -> None:
    """The invariants that only bite when an entry holds N > 1 workspaces.

    The first four are write-time gates rather than documented conventions,
    because violating any of them produces a file that is *readable* and
    wrong rather than one that fails: an unsplittable entry, or one whose
    rows are attributed to the wrong workspace. The fifth guards a file
    that would be written correctly and then could not be read back.
    """
    # 1. Without a discriminator, the boundary between inputs is not recorded
    #    anywhere. NXstress does not merge workspaces: that is PyRS's job,
    #    done before the write (Decisions Log row 45).
    if not _discriminator.field_names():
        raise ValueError(
            f"NXstress.write was given {len(wss)} workspaces, but "
            "'nxstress.discriminator_fields' names no field, so they could not be told apart "
            "when the file is read.\n"
            "  Configure a discriminator field, or merge the workspaces into one in PyRS "
            "before writing, as CombineRuns does."
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

    # 3. With several workspaces in one entry, each must hold a single run: the
    #    run is part of the workspace key (`_workspace_key.entry_carries_run`), so a workspace merged
    #    from several runs in PyRS has no one key to be read back under.
    merged = _runs.merged_inputs([ws._sample_logs for ws in wss])
    if merged:
        raise ValueError(
            f"NXstress.write: input workspace(s) {merged} hold several runs "
            f"({[sorted(_runs.run_numbers(wss[n]._sample_logs)) for n in merged]}).\n"
            "  A workspace merged from several runs can only be written on its own: alongside "
            "other workspaces, its rows could not be told apart from theirs on read."
        )

    # 4. The read side recovers each workspace by `(run, scan point)` membership,
    #    which cannot distinguish two workspaces sharing a run AND a scan point.
    #    A scan point alone may repeat -- every run numbers its scan points from 1.
    seen: dict = {}
    for n, ws in enumerate(wss):
        for point in _runs.workspace_pairs(ws._sample_logs):
            if point in seen:
                raise ValueError(
                    f"NXstress.write: (run, scan point) {point} appears in both input workspace "
                    f"[{seen[point]}] and [{n}].\n"
                    "  Input workspaces sharing an entry must not repeat a scan point within one "
                    "run: the reader recovers each workspace's rows by (run, scan point), so a "
                    "repeat cannot be attributed. Two workspaces with no `run_number` log share "
                    "the configured default run number."
                )
            seen[point] = n

    # 5. Each workspace read back must hold its scan points in increasing order.
    discriminator_names = _workspace_key.entry_discriminator_names(wss)
    run_boundary = _workspace_key.entry_carries_run(wss)
    points_by_key: dict = {}
    for ws in wss:
        points_by_key.setdefault(WorkspaceKey.of(ws, discriminator_names, carries_run=run_boundary), set()).update(
            _runs.workspace_pairs(ws._sample_logs)
        )
    runs = np.concatenate([_runs.for_scan_points(ws._sample_logs) for ws in wss])
    axis = np.concatenate([ws.get_sub_runs().raw_copy() for ws in wss])
    refuse_unreadable_scan_point_order(runs, axis, points_by_key, operation="write")


def refuse_unreadable_scan_point_order(
    runs: np.ndarray, axis: np.ndarray, points_by_key: dict, *, operation: str
) -> None:
    """Refuse an entry whose read-back workspaces would hold out-of-order scan points.

    `read` gives each workspace the rows whose `(run, scan point)` pairs it
    claims, in the order they are on disk, and builds a `SubRuns` from them
    -- which refuses anything not strictly increasing. Interleaved inputs
    are therefore fine when their workspace keys differ, but workspaces
    sharing one key (every discriminator value, and the run when the run is
    part of the key) are read back as one, and their concatenated axis must
    increase.

    Refused rather than sorted: the on-disk row order is the inputs' order,
    and re-sorting the rows would break the round trip -- there would
    then be no way to re-assign them to the individual workspaces on read.
    The requirement itself is arbitrary, and dropping it is recommended: it
    follows from `SubRuns` refusing a non-increasing axis, not from the format.

    Args:
        runs: The entry's whole run axis, aligned with `axis`.
        axis: The entry's whole scan-point axis, as it would be on disk.
        points_by_key: Each workspace key's `(run, scan point)` pairs,
            mirroring how `_read.workspace_selections` groups the entry on read.
        operation: "write" or "append", for the message.

    Raises:
        NotImplementedError: If any read-back workspace's scan points would
            not be strictly increasing. Nothing has been written, and an
            appending instance stays usable.
    """
    if len(points_by_key) <= 1:
        selections = [axis]
    else:
        pairs = _runs.pairs(runs, axis)
        selections = [
            axis[np.array([pair in points for pair in pairs], dtype=bool)] for points in points_by_key.values()
        ]
    for points in selections:
        if np.any(points[1:] <= points[:-1]):
            raise NotImplementedError(
                f"NXstress: cannot {operation} -- one workspace would be read back from this entry "
                f"with scan points {points.tolist()}, in that order, and PyRS requires a "
                "workspace's scan points to be strictly increasing.\n"
                "  Pass the workspaces in increasing scan-point order, or give them distinct "
                "discriminator values so that they are read back separately."
            )
