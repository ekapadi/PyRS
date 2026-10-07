"""
pyrs/utilities/NXstress/_discriminator.py

Discriminator-field support for multi-workspace NXstress I/O.

When more than one `HidraWorkspace` is written into a single `NXentry`, the
boundary between them has to be recoverable at read time. It is recovered from
**discriminator columns** on the combined peak index: one extra column per
configured field name, carrying that workspace's value for the field on every
row the workspace contributed.

Which fields those are is deployment policy, not a per-call argument, so it
comes from `pyrs.utilities.config.Config["nxstress.discriminator_fields"]`.
Typical workflow:

1. `field_names()` reads and validates the configured names.
2. `resolve(ws, name)` takes each name's value off each input workspace.
3. `key(ws, names)` packages those as a name-keyed, order-independent tuple,
   which `_peaks.py` writes to disk and sorts on.
4. On read, `apply(ws, name, value)` puts the value back onto each
   reconstructed workspace, so a caller can tell them apart by inspecting the
   same field it originally supplied.

Values are carried **name-keyed** rather than positionally: `discriminator_fields`
could be reordered in config between a write and a later read, and a positional
tuple would silently misattribute values in that case.
"""

import logging
from typing import Any

import numpy as np

from pyrs.core.workspaces import HidraWorkspace

from pyrs.utilities.config import Config

from pyrs.utilities.restorable_property import is_restorable, restore

from ._definitions import allowed_identifier


_logger = logging.getLogger(__name__)


# Column names `_Peaks._init` writes onto the `peaks` (NXreflections) group.
# A discriminator field may not encode onto any of these: it would either
# shadow the reserved column or be mistaken for one at read time, and both
# corrupt a round trip with no error to signal it.
#
# Pinned against the real group by
# `plans/NXstress-prod/probes/a4_nxstress_extra_columns.py`, and by
# `test_discriminator.py::test_reserved_columns_matches_peaks_init`, so that
# adding a column to `_init` without extending this set fails a test rather
# than silently narrowing the guard.
RESERVED_PEAK_COLUMNS = frozenset(
    {
        "scan_point",
        "h",
        "k",
        "l",
        "phase_name",
        "mask",
        "qx",
        "qy",
        "qz",
        "center",
        "center_errors",
        "center_type",
        "sx",
        "sy",
        "sz",
    }
)


# A discriminator key: `(name, value)` pairs sorted by name, so two keys built
# from the same fields compare equal regardless of the order config listed them.
DiscriminatorKey = tuple[tuple[str, Any], ...]


def field_names() -> tuple[str, ...]:
    """Configured discriminator field names, validated.

    Returns:
        The names from `nxstress.discriminator_fields`, in configured order.
        Empty when no discriminator is configured, which is the default.

    Raises:
        ValueError: If a name is blank, if the same name appears twice, or if a
            name encodes onto a reserved `NXreflections` column.
    """
    try:
        configured = Config["nxstress.discriminator_fields"]
    except Exception:  # noqa: BLE001 - a missing or broken key is "none configured"
        _logger.warning(
            "NXstress._discriminator: config key 'nxstress.discriminator_fields' could not be read;\n"
            "  proceeding as if no discriminator fields were configured."
        )
        return ()

    if configured is None:
        return ()
    if not isinstance(configured, (list, tuple)):
        raise ValueError(
            f"Config['nxstress.discriminator_fields'] must be a list of field names, "
            f"got {configured!r} ({type(configured).__name__})."
        )

    names = tuple(configured)
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Config['nxstress.discriminator_fields'] entries must be non-blank strings, "
                f"got {name!r} in {list(names)}."
            )
    if len(set(names)) != len(names):
        raise ValueError(
            f"Config['nxstress.discriminator_fields'] names the same field more than once: {list(names)}."
        )

    for name in names:
        collision = column_name(name)
        if collision in RESERVED_PEAK_COLUMNS:
            raise ValueError(
                f"Discriminator field '{name}' collides with the reserved `NXreflections` "
                f"column '{collision}'.\n"
                f"  Reserved: {sorted(RESERVED_PEAK_COLUMNS)}.\n"
                f"  Rename the field in `nxstress.discriminator_fields`."
            )
        _validate_round_trippable(name)
    return names


def _validate_round_trippable(name: str) -> None:
    """Reject a field that `resolve` could read but `apply` could not put back.

    `resolve` prefers a `HidraWorkspace` property over a sample log, so a field
    naming a **read-only** property is readable but not restorable: the value
    would be written to the file correctly and then lost on read, with the
    reconstructed workspace answering its constructor default instead. Nothing
    raises -- `write(read(f))` simply stores something different from `f`.

    Checked here, against configuration, rather than at write time: a field that
    cannot round-trip is a deployment mistake, and the cheapest moment to say so
    is before any file exists.

    A name that is not a property at all is left alone -- it will be resolved as
    a sample log, which round-trips through `set_sample_log`, and whether that
    log exists cannot be known from configuration.

    Args:
        name: A configured discriminator field name.

    Raises:
        ValueError: If `name` is a read-only `HidraWorkspace` property that is
            neither settable nor marked `@restorable()`.
    """
    if not name.isidentifier():
        return
    prop = getattr(HidraWorkspace, name, None)
    if not isinstance(prop, property):
        return
    if prop.fset is not None or is_restorable(HidraWorkspace, name):
        return
    raise ValueError(
        f"Discriminator field '{name}' is a read-only `HidraWorkspace` property, so its value "
        f"could be written to a file but never restored when the file is read back.\n"
        f"  Mark it `@restorable()` in `pyrs/core/workspaces.py` if it should participate in "
        f"NXstress round trips, or name a sample log instead."
    )


def merge_workspaces() -> bool:
    """Whether a multi-workspace write may merge indistinguishably.

    Only consulted when no discriminator field is configured. `False` -- the
    default -- rejects such a write outright rather than producing a file whose
    workspace boundaries cannot be recovered.
    """
    try:
        value = Config["nxstress.merge_workspaces"]
    except Exception:  # noqa: BLE001 - a missing or broken key is the safe default
        _logger.warning(
            "NXstress._discriminator: config key 'nxstress.merge_workspaces' could not be read;\n"
            "  proceeding as if it were false."
        )
        return False
    if not isinstance(value, bool):
        raise ValueError(
            f"Config['nxstress.merge_workspaces'] must be a bool, got {value!r} ({type(value).__name__})."
        )
    return value


def column_name(name: str) -> str:
    """On-disk column name for a discriminator field.

    Uses the same reversible encoding `_sample.py` applies to retained log
    names, so a field name containing characters NeXus disallows still round
    trips exactly.
    """
    return allowed_identifier(name)


def resolve(ws: HidraWorkspace, name: str) -> Any:
    """This workspace's value for one discriminator field.

    Prefers a matching `@property` when the class defines one, and otherwise
    falls back to the sample log of the same name.

    The `isinstance(..., property)` test is doing real work, and a bare
    `hasattr` would not do it: `HidraWorkspace` has methods whose names could
    plausibly be configured as fields (`save_experimental_data`, say), and
    `getattr` on one returns a bound method rather than a value.

    Args:
        ws: The workspace to take the value from.
        name: A configured discriminator field name.

    Returns:
        The single value this workspace carries for the field.

    Raises:
        ValueError: If `name` matches neither a property nor a sample log.
        AssertionError: If the sample log is not constant across the
            workspace's scan points -- raised by `get_sample_log_value`, which
            already performs that check, so no constancy test is repeated here.
    """
    if name.isidentifier() and isinstance(getattr(type(ws), name, None), property):
        return _as_text(getattr(ws, name))
    return _as_text(ws.get_sample_log_value(name))


def _as_text(value: Any) -> Any:
    """Normalise a string value to `str`, leaving everything else alone.

    HDF5 hands string data back as `bytes` even when it was written through the
    variable-length *UTF-8* dtype, so a value read from a file is `b"11"` where
    `"11"` was written. Left alone, a discriminator would therefore stop
    comparing equal to itself across a round trip -- and, because the comparison
    is what groups rows by workspace, would split one workspace into two rather
    than raise. Evidence:
    `plans/NXstress-prod/probes/a4_string_log_dtypes.py`.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8")
    if isinstance(value, np.str_):
        return str(value)
    return value


def apply(ws: HidraWorkspace, name: str, value: Any) -> None:
    """Put a discriminator value back onto a reconstructed workspace.

    Mirrors `resolve`, so a field backed by a property round-trips rather than
    being read from one place and written to another. Three cases, in order: a
    read/write property is assigned; a read-only `restorable_property` has its
    declared backing attribute written; anything else becomes a sample log.

    The middle case is the one that is easy to omit, and omitting it is silent:
    `resolve` reads any property, so a read-only one would be read from the
    property and written to a log, and the reconstructed workspace would answer
    with its constructor default instead of the stored value.

    Args:
        ws: A workspace reconstructed by `NXstress.read`, already carrying its
            sample logs -- `set_sample_log` needs the scan points.
        name: A configured discriminator field name.
        value: The value recovered from the file.
    """
    prop = getattr(type(ws), name, None) if name.isidentifier() else None
    if isinstance(prop, property) and prop.fset is not None:
        setattr(ws, name, value)
        return

    # A read-only property that declares a backing attribute. Without this branch
    # `resolve` would read the property while `apply` wrote a sample log, so the
    # value silently changed across a round trip -- the property kept answering
    # with whatever the constructor defaulted to.
    if is_restorable(ws, name):
        restore(ws, name, value)
        return

    sub_runs = ws.get_sub_runs().raw_copy()
    ws.set_sample_log(name, sub_runs, np.full(len(sub_runs), value))


def key(ws: HidraWorkspace, names: tuple[str, ...]) -> DiscriminatorKey:
    """Name-keyed discriminator key for one input workspace.

    Args:
        ws: The workspace to take values from.
        names: Configured field names, in any order.

    Returns:
        `(name, value)` pairs sorted by name. Empty when `names` is empty,
        which is the single-workspace and merged cases.
    """
    return tuple(sorted((name, resolve(ws, name)) for name in names))


def sort_values(disc_key: DiscriminatorKey) -> tuple:
    """The values of a discriminator key, in name order.

    This is the slowest-varying prefix of the peak index's sort key. Name order
    -- not configured order -- is what makes the resulting row order depend only
    on the field *set*, so reordering `discriminator_fields` in config cannot
    change what a write produces.
    """
    return tuple(value for _, value in disc_key)


def columns_on_disk(peaks) -> set[str]:
    """Discriminator column names present on a `peaks` (NXreflections) group.

    The partition is exact rather than heuristic: `field_names` refuses any
    configured name that encodes onto a reserved column, so every column that
    is not reserved is a discriminator and nothing else can be.
    """
    return {str(name) for name in peaks} - RESERVED_PEAK_COLUMNS


def names_for_read(peaks) -> tuple[str, ...]:
    """Discriminator field names to read a `peaks` group with, cross-checked.

    Configuration is the authority on which fields discriminate -- but a file
    written under different configuration must not be read as though it were
    written under this one. The two are compared, and a disagreement raises.

    The one tolerated disagreement is a file carrying *no* discriminator
    columns: that is what a pre-04b file, a single-workspace file written
    before any field was configured, and a `merge_workspaces` file all look
    like, and all three are legitimately read back as one workspace.

    Args:
        peaks: The `peaks` (NXreflections) group being read.

    Returns:
        The configured field names when the file carries their columns, or an
        empty tuple when the file carries none.

    Raises:
        RuntimeError: If the file's discriminator columns are neither absent
            nor exactly the configured set.
    """
    configured = field_names()
    on_disk = columns_on_disk(peaks)

    if not on_disk:
        if configured:
            _logger.info(
                f"NXstress._discriminator: this entry carries no discriminator columns, "
                f"while 'nxstress.discriminator_fields' names {list(configured)};\n"
                f"  reading it as a single workspace."
            )
        return ()

    expected = {column_name(name) for name in configured}
    if on_disk != expected:
        raise RuntimeError(
            f"NXstress: this entry's discriminator columns do not match the configured fields.\n"
            f"  On disk:    {sorted(on_disk)}\n"
            f"  Configured: {sorted(expected)} (from 'nxstress.discriminator_fields' "
            f"= {list(configured)})\n"
            f"  The file was written under different configuration. Set "
            f"'nxstress.discriminator_fields' to match it, or read a file written under this one."
        )
    return configured
