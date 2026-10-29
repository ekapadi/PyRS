"""
pyrs/utilities/NXstress/_append.py

Tail-append to an existing NXstress entry (spec 04c): the pre-flight that decides
whether an append may proceed, and the commit that grows every group.

An append is split in two so that its no-op guarantee can be read off the code:

1. `preflight(entry, wss, peakss)` runs every check, touching nothing, and
   returns the `AppendPlan` the commit needs. A refusal therefore leaves the entry
   byte-for-byte unchanged.
2. `commit(entry, wss, plan)` grows each group. Past its first resize there is no
   undo.

A violated invariant -- a duplicate row, an unmet precondition, a disagreement with
the entry -- is raised as `InvariantViolated`. `NXstress` takes that, and any
escape from the commit, as invalidating the instance: continuing would be writing
against an assumption already known to be false. "Unsupported" refusals
(`NotImplementedError`: Case B, an out-of-order read-back) leave it usable.

The checks are named for what they raise:

- `reject_*` raises `InvariantViolated` -- including for the plain `RuntimeError`
  of a group's own `validateAppend` or of `validate_appendable_shapes`, which
  `reject_ungrowable_or_disagreeing_groups` re-raises through `reject`;
- `refuse_*` raises `NotImplementedError`, leaving the instance usable;
- `classify_compound_keys` raises either: a duplicate row is violated, more scan
  points under an existing key are unsupported.
"""

from typing import NamedTuple

import numpy as np
from nexusformat.nexus import NXdata

from pyrs.core.peak_profile_utility import BackgroundFunction
from pyrs.core.workspaces import HidraWorkspace
from pyrs.peaks.peak_collection import PeakCollection
from pyrs.utilities.convertdatatypes import to_text

from ._definitions import (
    GROUP_NAME,
    UNDEFINED_PEAK_TAG,
    appendable,
    appendable_dtype,
    nxstress_diffractogram_keys,
    suffix_from_group_name,
)
from ._fit import _Fit
from ._input_data import _InputData
from ._instrument import _Instrument
from ._peaks import _Peaks, IndexedPeaks
from ._sample import _Sample
from . import _discriminator, _runs, _validation
from ._workspace_key import WorkspaceKey


class InvariantViolated(RuntimeError):
    """An append refused for a violated invariant, which invalidates the `NXstress` instance.

    A `RuntimeError`, as these refusals always were; the subclass is what lets
    `NXstress` tell them from a `RuntimeError` that is merely "unsupported".
    """


class AppendPlan(NamedTuple):
    """What the pre-flight established, for the commit to use unchanged.

    Attributes:
        indexed: The incoming peak collections, each with its workspace's key.
        discriminator_names: The fields the entry records.
        run_boundary: Whether the entry's workspace key carries the run.
    """

    indexed: list[IndexedPeaks]
    discriminator_names: tuple[str, ...]
    run_boundary: bool


def reject(message: str) -> InvariantViolated:
    """Build the exception for a violated invariant.

    Returned rather than raised so each call site reads `raise reject(...)` and the
    traceback starts there.
    """
    return InvariantViolated(message)


def preflight(entry, wss: list[HidraWorkspace], peakss: list[list[PeakCollection]]) -> AppendPlan:
    """Decide whether an append may proceed, touching nothing.

    Every check happens here, before any resize, so a rejected append leaves the
    entry byte-for-byte unchanged. That includes the checks `tail_append` itself
    would make -- resizability and trailing-axis agreement -- which are asked up
    front rather than discovered part-way through, because by then earlier groups
    have grown and there is no undo.

    Args:
        entry: The target `NXentry`, file-backed and open for writing.
        wss: Workspaces to append.
        peakss: One list of `PeakCollection` per workspace, same order.

    Returns:
        The plan `commit` carries out.

    Raises:
        InvariantViolated: On a violated invariant -- a duplicate row, a missing
            precondition, or a disagreement with the entry.
        NotImplementedError: For Case B, extending a compound key already on disk
            with further scan points. That needs a mid-array insertion rather than
            a tail-append and is deliberately out of scope. Also for an append that
            would leave a workspace's scan points out of order on read.
    """
    peaks_group = entry[GROUP_NAME.PEAKS]
    discriminator_names = _discriminator.names_for_read(peaks_group)

    # Asked before any key is built: an entry written before the run index has
    # no run column to grow, and one whose workspace key carries the run needs
    # every incoming workspace to hold exactly one.
    reject_run_index_mismatch(entry, wss)
    run_boundary = _runs.is_boundary(peaks_group)

    indexed = [
        IndexedPeaks(WorkspaceKey.of(ws, discriminator_names, carries_run=run_boundary), collection, ws._sample_logs)
        for ws, collections in zip(wss, peakss)
        for collection in collections
    ]

    run_checks(entry, wss, peakss, indexed, discriminator_names)
    return AppendPlan(indexed, discriminator_names, run_boundary)


def commit(entry, wss: list[HidraWorkspace], plan: AppendPlan) -> None:
    """Grow every group below the entry by the incoming rows, as `preflight` planned.

    A **tail-append**: the incoming batch is sorted among itself and added after
    each dataset's current end. Nothing already on disk is read back into
    `HidraWorkspace`/`PeakCollection` form, reordered or rewritten -- particularly
    not the raw detector counts, which are the bulk of an entry. The file is
    therefore "locally sorted, globally segmented" afterwards rather than globally
    sorted, which is all the reader has ever required: `_Peaks.peakCollectionRanges`
    enforces that each compound key occupies one contiguous run and that
    `scan_point` increases within it, and nothing more.

    The entry-level `start_time`/`end_time` belong to `NXstress`, which grows them
    first.
    """
    logss = [ws._sample_logs for ws in wss]
    _InputData.init_group(wss, data=entry[GROUP_NAME.INPUT_DATA])
    _Instrument.init_group(wss, data=entry[GROUP_NAME.INSTRUMENT])
    _Sample.init_group(logss, data=entry[GROUP_NAME.SAMPLE_DESCRIPTION])
    _Fit.init_group(wss, plan.indexed, logss, data=entry[GROUP_NAME.FIT])
    _Peaks.init_group(
        plan.indexed,
        logss[0],
        plan.discriminator_names,
        data=entry[GROUP_NAME.PEAKS],
        run_boundary=plan.run_boundary,
    )


def run_checks(
    entry,
    wss: list[HidraWorkspace],
    peakss: list[list[PeakCollection]],
    indexed: list[IndexedPeaks],
    discriminator_names: tuple,
) -> None:
    """Run every pre-flight check on an incoming batch, in order, touching nothing.

    Runs to completion before the first resize. That ordering is what makes
    both rejection outcomes true no-ops, and it is the reason every check
    that could fail part-way through an append lives here rather than at the
    point of use -- including the ones `tail_append` would otherwise make
    during mutation. Kept as a readable list of calls for the same reason:
    this is the method a reader has to follow in full to believe the no-op
    property, so it is the one that must stay short.

    Raises:
        InvariantViolated: On any violated invariant.
        NotImplementedError: For Case B, or for an out-of-order read-back.
            Leaves the instance usable.
    """
    # Ordinary write-time validation applies to the incoming batch regardless
    # of where it is going.
    try:
        _validation.validate_inputs(wss, peakss, indexed)
    except ValueError as error:
        raise reject(f"NXstress: cannot append -- {error}") from error

    reject_unmet_case_a_preconditions(peakss, discriminator_names)
    reject_unconfigured_columns(entry, discriminator_names)
    reject_discriminator_type_mismatch(entry, indexed, discriminator_names)
    reject_ungrowable_or_disagreeing_groups(entry, wss)
    classify_compound_keys(entry, indexed, discriminator_names)
    reject_scan_point_collisions(entry, wss)
    refuse_unreadable_append_order(entry, wss, discriminator_names)
    reject_diffractogram_key_mismatch(entry, wss)
    reject_fit_model_mismatch(entry, indexed)


def reject_run_index_mismatch(entry, wss: list[HidraWorkspace]) -> None:
    """The target entry must carry the run index, in a form the incoming workspaces fit.

    Three refusals, all before anything is resized, all invalidating the
    instance like every other violated precondition:

    - An entry written before the run index has no `run_number` column, on
      `peaks` or on `SAMPLE_DESCRIPTION`, so the incoming rows' runs would have
      nowhere to go -- the same reason an entry written before 04c is refused.
    - An entry whose workspace key does not carry the run
      (`_runs.BOUNDARY_ATTRIBUTE` false) holds one workspace merged from
      several runs, and anything appended would be read back as part of it.
    - An entry whose key does carry the run cannot take an incoming workspace
      merged from several runs: it has no one key to join under.
    """
    peaks_group = entry[GROUP_NAME.PEAKS]
    if _runs.RUN_NUMBER not in peaks_group or _runs.RUN_NUMBER not in entry[GROUP_NAME.SAMPLE_DESCRIPTION]:
        raise reject(
            "NXstress: cannot append -- the target entry was written before PyRS recorded run "
            "numbers, so it has no `run_number` column for the incoming rows.\n"
            "  Write a new file instead."
        )
    if not _runs.is_boundary(peaks_group):
        raise reject(
            "NXstress: cannot append -- the target entry holds a single workspace merged from "
            "several runs, so anything appended to it would be read back as part of that "
            "workspace.\n  Write a new file instead."
        )
    merged = _runs.merged_inputs([ws._sample_logs for ws in wss])
    if merged:
        raise reject(
            f"NXstress: cannot append -- input workspace(s) {merged} hold several runs, and this "
            "entry tells its workspaces apart by run.\n"
            "  Append one workspace per run."
        )


def reject_unmet_case_a_preconditions(peakss: list, discriminator_names: tuple[str, ...]) -> None:
    """Case A's two preconditions, inherited from 04b's write-time invariants."""
    # -- Case A precondition 1: every incoming workspace must contribute at
    #    least one `PeakCollection`. `_validation.validate_multi_workspace` already enforces
    #    this, but only for N > 1; on append it binds at N == 1 too, because
    #    the entry it joins holds other workspaces whose rows must stay
    #    distinguishable from these.
    empty = [n for n, collections in enumerate(peakss) if not collections]
    if empty:
        raise reject(
            f"NXstress: cannot append -- input workspace(s) {empty} contribute no "
            "`PeakCollection`.\n"
            "  The peak index is the only place a workspace's identity is recorded, so one "
            "with no peaks could not be recovered from the appended entry."
        )

    # -- Case A precondition 2: the target must already have a discriminator
    #    scheme. Attaching a new, distinguishable workspace to an entry written
    #    without one would mean adding an on-disk column. That is mechanically
    #    possible (see `probes/a4_h5py_nexusformat_append.py`) but it is schema
    #    restructuring, which this pass excludes -- a scope decision, not a
    #    format limit. See the plan's Decisions Log item 22.
    if not discriminator_names:
        raise reject(
            "NXstress: cannot append -- the target entry carries no discriminator columns, so "
            "an appended workspace could not be told apart from the one(s) already there.\n"
            "  Configure 'nxstress.discriminator_fields' and write the entry afresh; this pass "
            "does not add a column to an entry that lacks one."
        )


def reject_unconfigured_columns(entry, discriminator_names: tuple[str, ...]) -> None:
    """Every `peaks` column must be one the append knows how to grow.

    A read ignores a column it does not recognise; an append cannot. It grows
    the reserved columns and the configured discriminators, so any other
    column -- another producer's reflection field, or a discriminator the
    configuration does not name -- would be left short, and the group would
    no longer be row-aligned.
    """
    configured = {_discriminator.column_name(name) for name in discriminator_names}
    unknown = sorted(_discriminator.columns_on_disk(entry[GROUP_NAME.PEAKS]) - configured)
    if unknown:
        raise reject(
            f"NXstress: cannot append -- this entry's `peaks` group has column(s) {unknown}, "
            f"which are neither PyRS's own nor among the discriminator fields "
            f"{list(discriminator_names)}.\n"
            "  An append grows only the columns it knows, so these would be left short. "
            "Write a new entry instead."
        )


def reject_discriminator_type_mismatch(
    entry, indexed: list[IndexedPeaks], discriminator_names: tuple[str, ...]
) -> None:
    """Incoming discriminator values must fit the type of the column already on disk.

    The column's type was fixed by the entry's first write. A text value
    appended to a numeric column (or the reverse) fails inside `_Peaks`'
    append, after other groups have grown; a float appended to an integer
    column would be truncated without any error.
    """
    peaks_group = entry[GROUP_NAME.PEAKS]
    for name in discriminator_names:
        on_disk = peaks_group[_discriminator.column_name(name)].dtype
        incoming = np.asarray([dict(item.key.discriminators)[name] for item in indexed]).dtype
        if not appendable_dtype(incoming, on_disk):
            raise reject(
                f"NXstress: cannot append -- discriminator field '{name}' is stored as {on_disk} "
                f"in this entry, and the incoming value(s) are {incoming}.\n"
                "  A discriminator must keep the type the entry was first written with."
            )


def reject_ungrowable_or_disagreeing_groups(entry, wss: list[HidraWorkspace]) -> None:
    """Everything `tail_append` would refuse, and every per-group disagreement.

    Asked before the first resize rather than during mutation: a refusal
    discovered part-way through leaves the entry desynchronized, and such an
    entry reads back without error. See 04c's Follow-up 3 F3.1.
    """
    # -- Every dataset this append will grow must be able to grow, and must
    #    agree with the incoming rows on its trailing axes. Asked here rather
    #    than discovered inside `tail_append`, which runs during mutation:
    #    by then earlier groups have grown, the entry is desynchronized, and
    #    it reads back without error. See 04c's Follow-up 3 F3.1.
    #
    # -- Per-group agreement with the existing entry. Each of these lives on the
    #    group that owns the rule and is called here, before any resize, so that a
    #    mismatch is a true no-op rather than a half-grown entry.
    #
    # The groups raise a plain `RuntimeError`; re-raised through `reject` so that
    # these refusals invalidate the instance like every other violated invariant.
    try:
        validate_appendable_shapes(entry, wss)
        _Instrument.validateAppend(wss, entry[GROUP_NAME.INSTRUMENT])
        _InputData.validateAppend(wss, entry[GROUP_NAME.INPUT_DATA])
        _Sample.validateAppend([ws._sample_logs for ws in wss], entry[GROUP_NAME.SAMPLE_DESCRIPTION])
        _Fit.validateAppend(wss, entry[GROUP_NAME.FIT])
    except NotImplementedError:
        # A `RuntimeError` subclass, but "unsupported" rather than "violated",
        # and so not a reason to invalidate the instance.
        raise
    except RuntimeError as error:
        raise reject(str(error)) from error


def classify_compound_keys(entry, indexed: list[IndexedPeaks], discriminator_names: tuple[str, ...]) -> None:
    """Case A (proceed), Case B (unsupported) or duplicate (violated invariant)."""
    # -- Case A / Case B / duplicate, from the entry's existing peak index.
    existing_rows: dict = {}
    for workspace_key, key, start, end in _Peaks.peakCollectionRanges(entry[GROUP_NAME.PEAKS], discriminator_names):
        points = entry[GROUP_NAME.PEAKS]["scan_point"].nxdata[start:end]
        existing_rows[(workspace_key, key)] = set(np.asarray(points).tolist())

    for item in indexed:
        compound = (item.key, _Peaks.PeakIndex.sort_key(item.collection))
        if compound not in existing_rows:
            continue  # Case A -- a key the entry does not hold yet.
        incoming = set(item.collection.sub_runs.raw_copy().tolist())
        shared = incoming & existing_rows[compound]
        if shared:
            raise reject(
                f"NXstress: cannot append -- scan point(s) {sorted(shared)} are already present "
                f"in this entry under {compound[1]}{item.key.describe()}.\n"
                "  An appended row may not duplicate one already committed."
            )
        raise NotImplementedError(
            f"NXstress: appending further scan points to the compound key {compound[1]}{item.key.describe()}"
            ", which this entry already holds, is not supported.\n"
            "  Each key must occupy one contiguous run, so new scan points under an existing "
            "key would have to be inserted into the middle of it -- a different operation from "
            "the tail-append this implements. Appending a NEW workspace is supported."
        )


def reject_scan_point_collisions(entry, wss: list[HidraWorkspace]) -> None:
    """The `(run, scan point)` axis must stay partitioned across the whole entry."""
    # -- The reader attributes rows to a workspace by `(run, scan point)`, so a
    #    pair appearing twice in one entry cannot be attributed at all. A scan
    #    point alone may repeat across runs.
    sd = entry[GROUP_NAME.SAMPLE_DESCRIPTION]
    on_disk = set(_runs.pairs(_runs.axis(sd), np.asarray(sd["scan_point"].nxdata)))
    for n, ws in enumerate(wss):
        incoming = set(_runs.workspace_pairs(ws._sample_logs))
        collisions = on_disk & incoming
        if collisions:
            raise reject(
                f"NXstress: cannot append -- (run, scan point) pair(s) {sorted(collisions)} of input "
                f"workspace [{n}] are already in this entry.\n"
                "  The reader recovers each workspace's rows by (run, scan point), so a repeated "
                "pair cannot be attributed."
            )


def refuse_unreadable_append_order(entry, wss: list[HidraWorkspace], discriminator_names: tuple[str, ...]) -> None:
    """The appended entry must still read back with increasing scan points per workspace.

    An appended workspace sharing a discriminator value with rows already on
    disk is read back together with them, after them; so are all rows of an
    entry holding a single discriminator value. A tail-append of lower scan
    points is then unreadable. "Unsupported" rather than "violated", like
    Case B, so the instance stays usable.
    """
    points_by_key: dict = {}
    peaks_group = entry[GROUP_NAME.PEAKS]
    run_boundary = _runs.is_boundary(peaks_group)
    for workspace_key, _key, start, end in _Peaks.peakCollectionRanges(peaks_group, discriminator_names):
        points_by_key.setdefault(workspace_key, set()).update(
            _runs.pairs(peaks_group[_runs.RUN_NUMBER].nxdata[start:end], peaks_group["scan_point"].nxdata[start:end])
        )
    for ws in wss:
        points_by_key.setdefault(WorkspaceKey.of(ws, discriminator_names, carries_run=run_boundary), set()).update(
            _runs.workspace_pairs(ws._sample_logs)
        )
    sd = entry[GROUP_NAME.SAMPLE_DESCRIPTION]
    runs = np.concatenate([_runs.axis(sd)] + [_runs.for_scan_points(ws._sample_logs) for ws in wss])
    axis = np.concatenate([np.asarray(sd["scan_point"].nxdata)] + [ws.get_sub_runs().raw_copy() for ws in wss])
    _validation.refuse_unreadable_scan_point_order(runs, axis, points_by_key, operation="append")


def reject_diffractogram_key_mismatch(entry, wss: list[HidraWorkspace]) -> None:
    """Every scan point in an entry needs a diffractogram under each key.

    Compares **diffractogram keys**, not detector-mask names. The two are
    different sets: a key is a reduction identifier -- `eta_-5.0`,
    `mask_a_eta_-5.0` -- that references a detector mask without being one,
    and only a reduction that used the default mask *alone* produces a bare
    `DEFAULT_TAG` key. Reading this side through `nxstress_mask_names`, which
    injects `DEFAULT_TAG` because every reduction uses the default mask,
    therefore added a key the writer never emits -- and made every texture
    append impossible. See 04's Follow-up 8.
    """
    # -- The diffractogram key set must match. A key the entry has no group
    #    for would need a new group with no rows for the scan points already on
    #    disk, which is restructuring rather than growth.
    incoming_keys: set = set()
    for ws in wss:
        incoming_keys |= nxstress_diffractogram_keys(ws._diff_data_set.keys())
    on_disk_keys = {
        suffix_from_group_name(name, GROUP_NAME.DIFFRACTOGRAM)
        for name in entry[GROUP_NAME.FIT]
        if isinstance(entry[GROUP_NAME.FIT][name], NXdata)
    }
    if incoming_keys != on_disk_keys:
        raise reject(
            f"NXstress: cannot append -- the incoming workspaces' reduced-diffraction keys do "
            f"not match the target entry's.\n"
            f"  On disk:   {sorted(on_disk_keys)}\n"
            f"  Incoming:  {sorted(incoming_keys)}\n"
            "  Every scan point in an entry must have a diffractogram under each key."
        )


def reject_fit_model_mismatch(entry, indexed: list[IndexedPeaks]) -> None:
    """All peak collections in one entry share a single fit model."""
    # -- The peak profile and background function are entry-wide scalars that
    #    an append cannot change. `_append_peak` would raise on a mismatch, but
    #    only after earlier groups had already grown.
    fit_group = entry[GROUP_NAME.FIT]
    for group_name, label, incoming_titles in (
        (
            GROUP_NAME.PEAK_PARAMETERS,
            "peak profile",
            {str(item.collection.peak_profile).lower() for item in indexed},
        ),
        (
            GROUP_NAME.BACKGROUND_PARAMETERS,
            "background function",
            {str(BackgroundFunction.getFunction(item.collection.background_type)).lower() for item in indexed},
        ),
    ):
        on_disk_title = to_text(fit_group[group_name]["title"].nxdata)
        if str(on_disk_title) == UNDEFINED_PEAK_TAG:
            # The entry was written with no peak collections at all (the
            # CombineRuns export shape, `write([ws], [[]])`). Its fit model is
            # the writer's own sentinel, so comparing against it would reject
            # the append for apparently disagreeing with `_undefined_`. Say
            # what is actually wrong instead.
            raise reject(
                "NXstress: cannot append -- the target entry holds no `PeakCollection`s, so it "
                "records no fit model and no discriminator values for the rows already in it.\n"
                "  An appended workspace could not be told apart from them. Write a new entry."
            )
        if incoming_titles - {str(on_disk_title)}:
            raise reject(
                f"NXstress: cannot append -- the incoming `PeakCollection`s' {label} "
                f"{sorted(incoming_titles)} does not match the target entry's "
                f"'{on_disk_title}'.\n"
                "  All peak collections in one entry share a single fit model."
            )


def appendable_datasets(entry) -> dict:
    """Every dataset in `entry` that an append grows, declared by its owner.

    Each grouping module reports the datasets *it* writes row-aligned, because
    each one owns its group's layout. Inside a group NXstress writes, a field
    is either row-aligned -- and therefore `growable` -- or an entry-wide
    scalar, so a field added to such a group later is covered without editing
    anything here.

    This replaced a sweep of the whole entry for `shape[0] == n_scan`, which
    was wrong in both directions. It **over**-matched, and over-matching is
    not the harmless direction it was documented to be: the result feeds a
    resizability *requirement*, so any entry-wide array that happened to be
    `n_scan` long rejected a legal append. Three detector masks and three scan
    points was enough -- `masks/names` is entry-wide, is never grown, and is
    required by `_Instrument.validateAppend` to stay constant, yet the append
    was refused with a message blaming an out-of-date writer. It also
    **under**-matched: the peak index is one row per (compound key, scan
    point), so it equals `n_scan` only while each workspace fits exactly one
    peak. Fit a second phase -- the ordinary multi-peak case -- and `peaks/*`
    and both parameter groups dropped out of the pre-flight entirely, leaving
    exactly the mid-mutation refusal that 04c's Follow-up 3 F3.1 hoisted out.
    See 04c's Follow-up 5.

    Args:
        entry: The target `NXentry`.

    Returns:
        Path -> `NXfield`, for every dataset an append would extend.
    """
    found = {
        f"{GROUP_NAME.ENTRY}/start_time": entry["start_time"],
        f"{GROUP_NAME.ENTRY}/end_time": entry["end_time"],
    }
    for group_name, owner in (
        (GROUP_NAME.INPUT_DATA, _InputData),
        (GROUP_NAME.INSTRUMENT, _Instrument),
        (GROUP_NAME.SAMPLE_DESCRIPTION, _Sample),
        (GROUP_NAME.FIT, _Fit),
        (GROUP_NAME.PEAKS, _Peaks),
    ):
        if group_name in entry:
            found.update(
                {
                    f"{GROUP_NAME.ENTRY}/{path}": field
                    for path, field in owner.appendableDatasets(entry[group_name]).items()
                }
            )
    return found


def validate_appendable_shapes(entry, wss: list[HidraWorkspace]) -> None:
    """Every dataset the append will grow can grow, without growing any of them.

    Two distinct refusals, both of which `tail_append` would otherwise make
    during mutation:

    1. **Resizability.** A dataset written without `maxshape` is contiguous
       and can never be extended -- a file from a PyRS predating `growable`.
    2. **Trailing-axis agreement**, delegated to the groups that own the
       two-dimensional data, since only they know what the incoming rows
       would be shaped like.

    Which datasets those are is likewise asked of the groups that wrote them
    (`appendable_datasets`), not inferred from array length.

    Args:
        entry: The target `NXentry`.
        wss: Workspaces being appended.

    Raises:
        RuntimeError: Naming every dataset that cannot grow.
    """
    fixed = [path for path, field in appendable_datasets(entry).items() if not appendable(field)]
    if fixed:
        raise RuntimeError(
            f"NXstress: cannot append -- {len(fixed)} dataset(s) in this entry were written at a "
            f"fixed size and cannot be extended: {sorted(fixed)}.\n"
            "  Appending requires every per-scan-point dataset to have been created resizable "
            "(`maxshape`/`chunks`). A file written by a PyRS predating that change cannot be "
            "appended to -- write a new entry instead."
        )
