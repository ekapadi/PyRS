"""
pyrs/utilities/NXstress/_definitions.py

Constants and definitions used by NeXus NXstress-compatible I/O.
"""

from enum import Enum, StrEnum
from datetime import datetime
import h5py
import logging
from nexusformat.nexus import (
    NXbeam,
    NXcollection,
    NXdata,
    NXdetector,
    NXentry,
    NXfield,
    NXgroup,
    NXinstrument,
    NXmonochromator,
    NXnote,
    NXparameters,
    NXprocess,
    NXreflections,
    NXsample,
    NXsource,
    NXtransformations,
)
import numpy as np
import re
from typing import List, Tuple

from pyrs.dataobjects.constants import HidraConstants


logger = logging.getLogger("pyrs.utilities.NXstress")
REQUIRED_LOGS: List[str] = []


class _TypeBehavior:
    # Avoid metaclass conflict if mixin were derived from `type` directly.

    def __call__(self, *args, **kwargs):
        # Allow calling the enum member to construct via the underlying type
        return self.value(*args, **kwargs)

    def is_instance(self, obj):
        return isinstance(obj, self.value)

    def is_subclass(self, cls):
        return issubclass(cls, self.value)

    def __str__(self):
        return self.value.__name__


class FIELD_DTYPE(_TypeBehavior, Enum):
    # HDF5 dataset types for various fields
    FLOAT_CONSTANT = np.float64
    FLOAT_DATA = np.float32
    INT_DATA = np.int32
    STRING = h5py.string_dtype(encoding="utf-8")


def CHUNK_SHAPE(rank: int) -> Tuple[int, ...]:
    # chunk fast-axis only
    return (1,) * (rank - 1) + (100,)


class REQUIRED_NAME(StrEnum):
    # These are *required* group or dataset names, as specified in the `NXstress` schema.

    # FIT/DIFFRACTOGRAM sub-fields:
    PEAK_PARAMETERS = "peak_parameters"
    BACKGROUND_PARAMETERS = "background_parameters"
    DGRAM_DIFFRACTOGRAM = "diffractogram"
    DGRAM_DIFFRACTOGRAM_ERRORS = "diffractogram_errors"
    DGRAM_FIT = "fit"
    DGRAM_FIT_ERRORS = "fit_errors"

    INSTRUMENT = "instrument"
    BEAM = "beam_intensity_profile"
    PEAKS = "peaks"


class GROUP_NAME(StrEnum):
    # Group names: ordered by their appearance in the NXstress schema:
    #
    # -- Unless initialized from a `REQUIRED_NAME`, these may be modified as necessary.
    # -- In case of multiple group instances, the enum value here becomes the <base_name>,
    #    with the <instance number> or <tag> becoming a name suffix (see `group_naming_scheme` below).
    #

    # --- mypy: ---
    allowMultiple: bool
    nxClass: type[NXgroup]
    # -------------

    # Multiple NXentry are allowed in case there are multiple reduced data sets:
    #   e.g. from the same input data set, using different optimal peak-fit combinations.
    ENTRY = ("entry", True, NXentry)

    INSTRUMENT = (REQUIRED_NAME.INSTRUMENT, False, NXinstrument)
    CALIBRATION = ("calibration", False, NXnote)

    # SOURCE = ('source', False, NXsource)
    SOURCE = ("SOURCE", False, NXsource)  # *** DEBUG *** validator bug

    # DETECTOR = ('detector', True, NXdetector)
    DETECTOR = ("DETECTOR", True, NXdetector)  # *** DEBUG *** validator bug

    TRANSFORMATIONS = ("transformations", False, NXtransformations)
    BEAM = (REQUIRED_NAME.BEAM, False, NXbeam)
    MONOCHROMATOR = ("monochromator", False, NXmonochromator)

    # SAMPLE_DESCRIPTION = ('sample', False, NXsample)
    SAMPLE_DESCRIPTION = ("SAMPLE_DESCRIPTION", False, NXsample)  # *** DEBUG *** validator bug

    # FIT (NXprocess) groups contain the reduced data (and associated metadata):
    #   there should be one FIT group corresponding to each detector mask.

    # FIT   = ('fit', True, NXprocess)
    FIT = ("FIT", True, NXprocess)  # *** DEBUG *** validator bug

    # input NXparameters subgroup in 'NXprocess'
    INPUT = ("input", False, NXparameters)

    # DESCRIPTION = ('description', False, NXnote) # *** DEBUG *** validator bug
    DESCRIPTION = ("DESCRIPTION", False, NXnote)

    PEAK_PARAMETERS = (REQUIRED_NAME.PEAK_PARAMETERS, False, NXparameters)
    BACKGROUND_PARAMETERS = (REQUIRED_NAME.BACKGROUND_PARAMETERS, False, NXparameters)

    # DIFFRACTOGRAM = ('diffractogram', False, NXdata) # *** DEBUG *** validator bug
    DIFFRACTOGRAM = ("DIFFRACTOGRAM", False, NXdata)
    DGRAM_TWO_THETA_NAME = ("XAXIS", False, NXfield)  # *** DEBUG *** validator bug: normally would be just 'two_theta'

    # DIFFRACTOGRAM sub-fields:
    DGRAM_DIFFRACTOGRAM = (REQUIRED_NAME.DGRAM_DIFFRACTOGRAM, False, NXfield)
    DGRAM_DIFFRACTOGRAM_ERRORS = (REQUIRED_NAME.DGRAM_DIFFRACTOGRAM_ERRORS, False, NXfield)
    DGRAM_FIT = (REQUIRED_NAME.DGRAM_FIT, False, NXfield)
    DGRAM_FIT_ERRORS = (REQUIRED_NAME.DGRAM_FIT_ERRORS, False, NXfield)

    # PEAKS (NXreflections) presents the canonical reduction result: there is only one per NXentry.
    PEAKS = (REQUIRED_NAME.PEAKS, False, NXreflections)

    ## OPTIONAL GROUPS, allowed by but not specified by the schema: ##

    # Including the input data allows all of the information for a reduction to be contained in one file.
    INPUT_DATA = ("input_data", False, NXdata)

    # Masks are added as a subgroup under the `INSTRUMENT` group:
    #   both <detector mask> and <solid-angle mask> are currently recognized,
    #   however the mask names must be distinct, because they're used as suffix tags
    #   when creating other group names.
    MASKS = ("masks", False, NXcollection)

    def __new__(cls, value, allowMultiple: bool, nxClass: type[NXgroup]):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.allowMultiple = allowMultiple
        obj.nxClass = nxClass
        return obj


# `NXstress` records `peak_parameters` and `background_parameters` in distinct groups.
EFFECTIVE_BACKGROUND_PARAMETERS = ["A0", "A1", "A2"]

# Name or suffix corresponding to the default dataset:
# -- when a group name uses this as a suffix tag (e.g. multiple FIT (NXprocess) groups, one for each mask)
#    this default tag should be _omitted_ from the group name.
# -- presently this is only used for masks, to allow multiple FIT.diffractogram groups.
DEFAULT_TAG = HidraConstants.DEFAULT_MASK

UNDEFINED_PEAK_TAG = "_undefined_"

NO_LOG = "_no_log_"


def group_naming_scheme(base_name: str, suffix: int | str) -> str:
    # Generate the name for an HDF5 group, allowing for multiple group instances:
    #   instance:
    #     int: enumerated group names: '_1' is omitted;
    #     str: group names (e.g. 'DIFFRACTOGRAM' (NXdata)), delineated using a tag suffix: '__DEFAULT_' is omitted.
    if not isinstance(suffix, (int, str)):
        raise RuntimeError(f"`group_naming_scheme`: not implemented for suffix '{suffix}'")

    tag = ""
    if isinstance(suffix, int) and suffix > 1 or isinstance(suffix, str) and suffix != DEFAULT_TAG:
        tag = f"_{suffix}"

    return f"{base_name}{tag}"


def suffix_from_group_name(group_name: str, base_name: str) -> str:
    """Reverse of `group_naming_scheme`: extract the suffix from a group name.

    'DIFFRACTOGRAM' -> DEFAULT_TAG
    'DIFFRACTOGRAM_mask_A' -> 'mask_A'

    Parameters
    ----------
    group_name : str
        The group name to parse
    base_name : str
        The base name used to form the group name

    Returns
    -------
    str
        The appended suffix (or DEFAULT_TAG for the default case)
    """
    prefix = str(base_name)
    if group_name == prefix:
        return DEFAULT_TAG
    elif group_name.startswith(prefix + "_"):
        return group_name[len(prefix) + 1 :]
    else:
        raise RuntimeError(f"Cannot extract suffix (e.g. mask name) from '{group_name}'")


# NeXus `validItemName`, the authoritative rule for what may appear in a group or
# field name. Reproduced verbatim from `nxdl.xsd` of the NeXus definitions
# repository (`nexusformat/definitions`, NXDL v2026.01, commit 004da96e):
#
#     <xs:pattern value="[a-zA-Z0-9_]([a-zA-Z0-9_.]*[a-zA-Z0-9_])?" />
#     <xs:maxLength value="63" />
#
# The rule is NOT shipped by the installed `nexusformat` package, and it is not
# in the NXstress application definition either -- it belongs to the NXDL schema
# that governs all of them. The application definition itself is vendored at
# `docs/developer/source/design/nexus/NXstress.nxdl.xml`; this rule lives here,
# beside the code that enforces it. `plans/NXstress-prod/probes/` reads the
# upstream file live and fails if either value below has drifted from it.
#
# Two consequences that are easy to get wrong, and were:
#   * '.' is legal in the INTERIOR only -- never leading or trailing;
#   * a LEADING DIGIT is legal, so '2theta' (a real log name) needs no escaping.
VALID_ITEM_NAME = r"[a-zA-Z0-9_]([a-zA-Z0-9_.]*[a-zA-Z0-9_])?"
MAX_IDENTIFIER_LENGTH = 63

_VALID_ITEM_NAME_RE = re.compile(f"^{VALID_ITEM_NAME}$")

# `__` (two underscores) introduces an escape. Making the introducer two
# characters rather than one is what keeps names legible: a lone '_' is then
# never the start of an escape, so it passes through untouched. Of the 185 real
# log names in `tests/data`, 118 encode verbatim and *none* needs an escaped
# underscore -- where a single-'_' introducer would have rewritten all 37 names
# containing one.
_ESCAPE = "__"

_EDGE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_INTERIOR_CHARS = _EDGE_CHARS | {"."}


def _legal_at(ch: str, *, edge: bool) -> bool:
    # The rule is position-dependent in exactly one way: '.' is allowed in the
    # interior but not at either end.
    return ch in (_EDGE_CHARS if edge else _INTERIOR_CHARS)


def _escape_char(ch: str) -> str:
    codepoint = ord(ch)
    return f"{_ESCAPE}{codepoint:02X}" if codepoint < 256 else f"{_ESCAPE}u{codepoint:04X}"


# Throughout the PyRS codebase, `None` is the key for the default mask -- in
# `HidraWorkspace._mask_dict` and `._diff_data_set` alike. NXstress cannot use `None`
# as a group name, so it uses `DEFAULT_TAG`. The two functions below are the single
# place that correspondence is expressed; before, each call site re-derived it inline
# (`keys.discard(None); keys.add(DEFAULT_TAG)`), which is what the TODO in `_fit.py`
# meant by "mask naming (and storage) is messed up". Writer and reader now agree by
# construction rather than by coincidence.


def workspace_mask_key(mask_name: str):
    """Map an NXstress mask name to the key `HidraWorkspace` stores it under.

    Args:
        mask_name: Mask name as written to the NXstress file.

    Returns:
        `None` for the default mask, otherwise `mask_name` unchanged.

    Example:
        >>> workspace_mask_key(DEFAULT_TAG) is None
        True
    """
    return None if mask_name == DEFAULT_TAG else mask_name


def nxstress_mask_name(mask_key) -> str:
    """Map a `HidraWorkspace` mask key to the name NXstress writes.

    Args:
        mask_key: Mask key as held by `HidraWorkspace`; `None` is the default mask.

    Returns:
        `DEFAULT_TAG` for the default mask, otherwise `mask_key` unchanged.

    Example:
        >>> nxstress_mask_name(None) == DEFAULT_TAG
        True
    """
    return DEFAULT_TAG if mask_key is None else mask_key


def nxstress_mask_names(*mask_keys) -> set:
    """Normalise one or more collections of workspace mask keys to NXstress names.

    The default mask is always present in the result: NXstress requires one, and it
    is generated at write time when the workspace has none.

    Args:
        *mask_keys: Iterables of `HidraWorkspace` mask keys.

    Returns:
        The set of NXstress mask names, always including `DEFAULT_TAG`.
    """
    names = {DEFAULT_TAG}
    for keys in mask_keys:
        names.update(nxstress_mask_name(key) for key in keys)
    return names


def allowed_identifier(s: str) -> str:
    """Convert an arbitrary PV-log name to a NeXus-compliant identifier.

    The conversion is **injective and reversible** -- see :func:`decode_identifier`.
    That matters more than it sounds: the previous implementation replaced ':'
    with '_' and nothing else, which is many-to-one, so two distinct PV logs
    (``HB2B:CS:X`` and ``HB2B_CS_X``) collapsed onto one group and the second
    silently overwrote the first, including the ``local_name`` attribute that
    exists to record the original name. Being injective makes that collision
    impossible rather than merely detectable.

    Encoding forms, all introduced by ``__``:

    ==========  ==========================================================
    ``__XX``    the character with byte value ``0xXX`` -- ``__3A`` is ``:``
    ``__uXXXX`` a codepoint above U+00FF
    ``__5F``    a literal ``_`` that would otherwise be read as an escape
    ``_``       a lone underscore means itself
    ==========  ==========================================================

    Args:
        s: PV-log name, as recorded by the control system. Arbitrary text.

    Returns:
        A name matching :data:`VALID_ITEM_NAME`, no longer than
        :data:`MAX_IDENTIFIER_LENGTH` characters.

    Raises:
        ValueError: If `s` is empty, or if the encoded form exceeds the
            63-character NeXus limit.

    Example:
        >>> allowed_identifier("HB2B:Mot:sz_real")
        'HB2B__3AMot__3Asz_real'
        >>> allowed_identifier("2theta")
        '2theta'
    """
    if not s:
        raise ValueError("Cannot convert an empty string to a NeXus identifier")

    out: List[str] = []
    last = len(s) - 1
    for i, ch in enumerate(s):
        edge = i == 0 or i == last
        if ch == "_":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            # A lone '_' only becomes ambiguous when the NEXT emitted token also
            # starts with '_' -- that is, the next character is another '_', or is
            # itself illegal and so will be escaped. One character of lookahead.
            if nxt == "_" or (nxt != "" and not _legal_at(nxt, edge=(i + 1 == last))):
                out.append(_escape_char("_"))
            else:
                out.append("_")
        elif _legal_at(ch, edge=edge):
            out.append(ch)
        else:
            out.append(_escape_char(ch))

    encoded = "".join(out)
    if len(encoded) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"PV-log name '{s}' encodes to '{encoded}' ({len(encoded)} characters),\n"
            f"  which exceeds the NeXus limit of {MAX_IDENTIFIER_LENGTH}."
        )
    return encoded


def decode_identifier(s: str) -> str:
    """Recover the original PV-log name from :func:`allowed_identifier` output.

    Decoding needs no lookahead: ``__u`` begins a 7-character form, ``__`` a
    4-character one, and anything else is a literal.

    Args:
        s: An identifier produced by :func:`allowed_identifier`.

    Returns:
        The original PV-log name.

    Raises:
        ValueError: If `s` contains a truncated or non-hexadecimal escape.

    Example:
        >>> decode_identifier("HB2B__3AMot__3Asz_real")
        'HB2B:Mot:sz_real'
    """
    out: List[str] = []
    i = 0
    while i < len(s):
        try:
            if s.startswith(f"{_ESCAPE}u", i):
                out.append(chr(int(s[i + 3 : i + 7], 16)))
                i += 7
            elif s.startswith(_ESCAPE, i):
                out.append(chr(int(s[i + 2 : i + 4], 16)))
                i += 4
            else:
                out.append(s[i])
                i += 1
        except ValueError as e:
            raise ValueError(f"Malformed escape in NeXus identifier '{s}' at position {i}") from e
    return "".join(out)


def is_ISO_8601(s: str) -> bool:
    scannable = True
    try:
        datetime.fromisoformat(s)
    except ValueError as e:
        if "Invalid isoformat string" not in str(e):
            raise
        scannable = False
    return scannable
