# ruff: noqa: E741 # use `l` for `l` in `(h, k, l)`!
"""
pyrs/utilities/NXstress/_peaks.py

Private service class for NeXus NXstress-compatible I/O.
This class provides I/O for the `peaks` `NXreflections` subgroup:
  this subgroup includes fitted peak data, as used in reduction.
"""

import logging
import numpy as np
from nexusformat.nexus import NXreflections, NXfield
import re
from typing import NamedTuple

from pyrs.peaks.peak_collection import PeakCollection
from pyrs.dataobjects.constants import HidraConstants
from pyrs.dataobjects.sample_logs import SampleLogs
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import CHUNK_SHAPE, FIELD_DTYPE


_logger = logging.getLogger(__name__)


"""
REQUIRED PARAMETERS FOR NXstress:
---------------------------------

├─ peaks                                  (NXreflections, group)
│   ├─ h                                   (dataset)
│   ├─ k                                   (dataset)
│   ├─ l                                   (dataset)
│   └─ phase_name                          (dataset)

`PeakCollection` to `peaks` (NXreflections), `FIT` (NXprocess) mapping:
-----------------------------------------------------------------------

1. `peaks` provides the `n_Peaks` index which identifies `FIT` entries, with the exception of the `diffractogram` which are indexed separately.

- A flattened index is used `(<phase>, h, k, l, <mask>, <scan point>)`: all <scan point> may not be present, and to support legacy code specifying the <mask> is optional,
  and it will default to the key '_DEFAULT_';  Note that <mask> was not retained as a `PeakCollection` field prior to this implementation, but it does seem to be required;

- This flattened index allows appending (not yet implemented), however each index value must identify a *unique* entry (i.e. there can be no duplicates);

- Each combination of `(<phase>, h, k, l, <mask>, ...)` corresponds to *one* `PeakCollection` instance;

- For input and output purposes (to and from HDF5), the entire index set will be sorted lexographically prior to output.  This makes the append operation more complicated,
  but provides robustness against duplicates (or overwrites).

2. `diffractogram` are stored as 'diffractogram_<mask key>', and indexed by <scan point>.  Any single <scan point> that does not have an entry will be filled in with `NaN`.

"""


class _Peaks:
    ########################################
    # ALL methods must be `classmethod`.  ##
    ########################################

    class PeakIndex(NamedTuple):
        # Corresponds to the `n_Peaks` index in the `NXstress` schema.
        # Each `PeakCollection` instance provides
        #   `(<phase>, h, k, l, <mask>, ...)`, i.e. multiple scan_point;
        #   `scan_point` are distinct, but are not required to be contiguous, nor complete.
        phase_name: str
        h: int
        k: int
        l: int  # noqa: E741
        mask: str
        scan_point: int

        @classmethod
        def sort_key(cls, peaks: PeakCollection) -> tuple[str, int, int, int, str]:
            # Define an ordering for `PeakCollection` instances
            phase_name, (h, k, l) = _Peaks._parse_peak_tag(peaks.peak_tag)
            mask = peaks.mask
            return (phase_name, h, k, l, mask)

    @classmethod
    def _parse_peak_tag(cls, tag: str) -> tuple[str, tuple[int, int, int]]:
        # Parse a peak-tag string into its <phase name> and Miller indices (h, k, l).
        match: re.Match[str] | None = max(
            re.finditer(r"\d+", tag),
            key=lambda m: len(m.group(0)),
            default=None,
        )
        if match is None or len(match.group(0)) % 3 != 0:
            raise RuntimeError(f"Unable to parse peak tag '{tag}' into its <phase name> and Miller indices (h, k, l).")
        # Extract <phase name> as the rest of the tag.
        i, j = match.span()
        phase = (tag[:i] + tag[j:]).strip()
        if not bool(phase):
            raise RuntimeError(f"Unable to parse <phase name> from peak tag '{tag}'.")

        # Extract (h, k, l)
        maybeHKL = match.group(0)
        N_d = len(maybeHKL) // 3
        h, k, l_ = int(maybeHKL[0:N_d]), int(maybeHKL[N_d : 2 * N_d]), int(maybeHKL[2 * N_d : 3 * N_d])

        return phase, (h, k, l_)

    @classmethod
    def _init(cls, logs: SampleLogs) -> NXreflections:
        # Initialize the 'PEAKS' group
        peaks = NXreflections()

        peaks["scan_point"] = NXfield(np.empty((0,), dtype=np.int32), maxshape=(None,), chunks=CHUNK_SHAPE(1))

        peaks["h"] = NXfield(np.empty((0,), dtype=np.int32), maxshape=(None,), chunks=CHUNK_SHAPE(1), units="")
        peaks["k"] = NXfield(np.empty((0,), dtype=np.int32), maxshape=(None,), chunks=CHUNK_SHAPE(1), units="")
        peaks["l"] = NXfield(np.empty((0,), dtype=np.int32), maxshape=(None,), chunks=CHUNK_SHAPE(1), units="")

        peaks["phase_name"] = NXfield(
            np.empty((0,), dtype=FIELD_DTYPE.STRING.value), maxshape=(None,), chunks=CHUNK_SHAPE(1)
        )

        peaks["mask"] = NXfield(
            np.empty((0,), dtype=FIELD_DTYPE.STRING.value), maxshape=(None,), chunks=CHUNK_SHAPE(1)
        )

        ## Components of the normalized scattering vector Q in the sample reference frame
        ##   'qx', 'qy', and 'qz' are *required* by NXstress, but it looks as if PyRS doesn't
        ##   use these -- initialize to `NaN`.
        peaks["qx"] = NXfield(
            np.empty((0,), dtype=np.float64), maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan
        )
        peaks["qx"].attrs["units"] = "1"
        peaks["qy"] = NXfield(
            np.empty((0,), dtype=np.float64), maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan
        )
        peaks["qy"].attrs["units"] = "1"
        peaks["qz"] = NXfield(
            np.empty((0,), dtype=np.float64), maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan
        )
        peaks["qz"].attrs["units"] = "1"
        ##

        peaks["center"] = NXfield(
            np.empty((0,), dtype=np.float64), maxshape=(None,), chunks=CHUNK_SHAPE(1), units="angstrom"
        )
        peaks["center_errors"] = NXfield(
            np.empty((0,), dtype=np.float64), maxshape=(None,), chunks=CHUNK_SHAPE(1), units="angstrom"
        )
        peaks["center_type"] = NXfield("d-spacing")

        # Sample position for each subrun -- initialize to `NaN`.
        #
        # NXstress requires `peaks/sx,sy,sz` and defines them as the *sample position
        # in the sample reference frame* (see the vendored application definition at
        # `docs/developer/source/design/nexus/NXstress.nxdl.xml`). In PyRS that
        # quantity is `PointList.(vx, vy, vz)` -- NOT the stage-position logs that
        # happen to be spelled `sx`/`sy`/`sz`, which the stress/strain workflow does
        # not use. Those remain available in their own right, under
        # SAMPLE_DESCRIPTION/logs. Each field records its true source in
        # `local_name`, the same convention `_sample.py` uses for retained logs,
        # because the field name alone is misleading here.
        ss_units = {
            ## work around: units may be an empty string
            axis: logs.units(axis) if bool(logs.units(axis)) else "mm"
            for axis in HidraConstants.SAMPLE_COORDINATE_NAMES
        }
        peaks["sx"] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            fillvalue=np.nan,
            units=ss_units["vx"],
        )
        peaks["sy"] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            fillvalue=np.nan,
            units=ss_units["vy"],
        )
        peaks["sz"] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            fillvalue=np.nan,
            units=ss_units["vz"],
        )

        for peak_axis, coord_axis in zip(("sx", "sy", "sz"), HidraConstants.SAMPLE_COORDINATE_NAMES):
            peaks[peak_axis].attrs["local_name"] = coord_axis

        return peaks

    @classmethod
    def init_group(cls, peakss: list[PeakCollection], logs: SampleLogs) -> NXreflections:
        # Initialize the PEAKS group:
        #   according to the NXstress schema, this group contains the canonical reduction data,
        #   in a form usable for stress / strain calculations.

        # TODO: these code sections are implemented in a form that allows new scan-point data to be appended
        #   However, at present, appending data is not yet supported.
        peaks = cls._init(logs)

        for peak_collection in sorted(peakss, key=_Peaks.PeakIndex.sort_key):
            cls._append_peak(peaks, peak_collection, logs)

        return peaks

    @classmethod
    def _append_peak(cls, peaks: NXreflections, peak_collection: PeakCollection, logs: SampleLogs) -> NXreflections:
        # Append a `PeakCollection` to an initialized PEAKS group.
        scan_point = peak_collection.sub_runs.raw_copy()
        N_scan = len(scan_point)
        phase_name, (h, k, l_) = cls._parse_peak_tag(peak_collection.peak_tag)
        mask = peak_collection.mask

        # Each dataset has scan point as its first index.
        phase_name_arr = np.array((phase_name,) * N_scan)
        h_arr = np.array((h,) * N_scan)
        k_arr = np.array((k,) * N_scan)
        l_arr = np.array((l_,) * N_scan)
        mask_arr = np.array((mask,) * N_scan)

        d_reference_arr, d_reference_error_arr = peak_collection.get_d_reference()

        curr_len = peaks["h"].shape[0]
        new_len = curr_len + N_scan

        peaks["scan_point"].resize((new_len,))

        peaks["h"].resize((new_len,))
        peaks["k"].resize((new_len,))
        peaks["l"].resize((new_len,))
        peaks["phase_name"].resize((new_len,))
        peaks["mask"].resize((new_len,))

        # For `PEAKS` (NXreflections) group: 'center' means `d_reference`.
        peaks["center"].resize((new_len,))
        peaks["center_errors"].resize((new_len,))

        peaks["sx"].resize((new_len,))
        peaks["sy"].resize((new_len,))
        peaks["sz"].resize((new_len,))

        peaks["scan_point"][curr_len:] = scan_point
        peaks["h"][curr_len:] = h_arr
        peaks["k"][curr_len:] = k_arr
        peaks["l"][curr_len:] = l_arr
        peaks["phase_name"][curr_len:] = phase_name_arr
        peaks["mask"][curr_len:] = mask_arr

        peaks["center"][curr_len:] = d_reference_arr.ravel()
        peaks["center_errors"][curr_len:] = d_reference_error_arr.ravel()

        # The original form of this block read `logs['sx']` wholesale, which is why it
        # was commented out as not making sense: a log spans *every* scan point in the
        # workspace, while this slice needs only the scan points of THIS
        # `PeakCollection`. `get_pointlist` takes the subrun subset directly.
        for peak_axis, values in zip(("sx", "sy", "sz"), cls._sample_positions(logs, scan_point, N_scan)):
            peaks[peak_axis][curr_len:] = values

        return peaks

    @classmethod
    def _sample_positions(cls, logs: SampleLogs, scan_point: np.ndarray, N_scan: int) -> tuple:
        """Sample position for a `PeakCollection`'s scan points, as (vx, vy, vz).

        Args:
            logs: Sample logs for the whole workspace.
            scan_point: The subrun numbers this `PeakCollection` covers.
            N_scan: Number of scan points, used to shape the `NaN` fallback.

        Returns:
            Three arrays of length `N_scan`, in millimetres. All `NaN` when the
            coordinate logs are absent or non-finite.
        """
        try:
            point_list = logs.get_pointlist(scan_point)
            return (point_list.vx, point_list.vy, point_list.vz)
        except (ValueError, AssertionError) as e:
            # Match `_sample.py`'s handling: a workspace with no usable sample
            # coordinates still writes a valid file, with `NaN` where the positions
            # would go, rather than failing an entire save.
            _logger.warning(
                f"NXstress._peaks: sample coordinates "
                f"{HidraConstants.SAMPLE_COORDINATE_NAMES} are unavailable ({e});\n"
                "  `peaks/sx,sy,sz` will be written as NaN."
            )
            nan = np.full((N_scan,), np.nan)
            return (nan, nan.copy(), nan.copy())

    @classmethod
    def peakCollectionRanges(cls, peaks) -> list[tuple[tuple[str, int, int, int, str], int, int]]:
        """Identify contiguous blocks of PeakCollection data in NXreflections group.

        Each PeakCollection corresponds to a unique 5-tuple (phase_name, h, k, l, mask)
        with multiple scan-points written as a contiguous block in increasing order.

        Parameters
        ----------
        peaks : NXreflections
            The peaks group from which to read the flattened index

        Returns
        -------
        list[tuple[tuple[str, int, int, int, str], int, int]]
            List of (key, start, end) where:
            - key is (phase_name, h, k, l, mask)
            - start is the first index (inclusive)
            - end is the last index (exclusive)

        Raises
        ------
        RuntimeError
            If scan_point values are not strictly increasing within a block
        RuntimeError
            If interleaved blocks are detected for the same sub-index key
        """
        # Read index arrays via .nxdata
        phase_name = peaks["phase_name"].nxdata[:]
        h = peaks["h"].nxdata[:]
        k = peaks["k"].nxdata[:]
        l_ = peaks["l"].nxdata[:]
        mask = peaks["mask"].nxdata[:]
        scan_point = peaks["scan_point"].nxdata[:]

        if len(phase_name) == 0:
            return []

        # Decode bytes to strings if necessary
        if phase_name.dtype.kind == "S" or phase_name.dtype.kind == "O":
            phase_name = np.array([p.decode("utf-8") if isinstance(p, bytes) else str(p) for p in phase_name])
        if mask.dtype.kind == "S" or mask.dtype.kind == "O":
            mask = np.array([m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in mask])

        ranges = []
        seen_keys = set()

        # Track current block
        current_key = (str(phase_name[0]), int(h[0]), int(k[0]), int(l_[0]), str(mask[0]))
        start_idx = 0

        for i in range(1, len(phase_name)):
            key = (str(phase_name[i]), int(h[i]), int(k[i]), int(l_[i]), str(mask[i]))

            if key != current_key:
                # Block boundary - validate and record current block
                end_idx = i

                # Check for strictly increasing scan_point within block
                block_scan_points = scan_point[start_idx:end_idx]
                if not np.all(block_scan_points[1:] > block_scan_points[:-1]):
                    raise RuntimeError(
                        f"scan_point values are not strictly increasing within PeakCollection block "
                        f"at {current_key}, indices [{start_idx}, {end_idx})"
                    )

                # Check for interleaved blocks
                if current_key in seen_keys:
                    raise RuntimeError(f"Interleaved blocks detected for sub-index {current_key}")

                seen_keys.add(current_key)
                ranges.append((current_key, start_idx, end_idx))

                # Start new block
                current_key = key
                start_idx = i

        # Handle last block
        end_idx = len(phase_name)
        block_scan_points = scan_point[start_idx:end_idx]
        if not np.all(block_scan_points[1:] > block_scan_points[:-1]):
            raise RuntimeError(
                f"scan_point values are not strictly increasing within PeakCollection block "
                f"at {current_key}, indices [{start_idx}, {end_idx})"
            )

        if current_key in seen_keys:
            raise RuntimeError(f"Interleaved blocks detected for sub-index {current_key}")

        seen_keys.add(current_key)
        ranges.append((current_key, start_idx, end_idx))

        return ranges

    @classmethod
    def validateNoDuplicatePeaks(cls, peakss: list[PeakCollection]) -> None:
        """Validate that no duplicate PeakCollections exist in the list.

        Each PeakCollection must have a unique 5-tuple key (phase_name, h, k, l, mask).

        Parameters
        ----------
        peakss : list[PeakCollection]
            List of PeakCollection instances to validate

        Raises
        ------
        ValueError
            If any duplicate keys are found
        """
        seen_keys = {}
        for peaks in peakss:
            key = cls.PeakIndex.sort_key(peaks)
            if key in seen_keys:
                raise ValueError(
                    f"Duplicate PeakCollection detected in output list at {key} "
                    f"-- did you forget to initialize the `mask` key?"
                )
            seen_keys[key] = peaks

    @classmethod
    @validate_call_
    def peakCollectionsFromNexus(cls, peaks, fit) -> list[PeakCollection]:
        """Read PeakCollections from NXreflections and NXprocess groups.

        Note: This implementation assumes positive Miller indices. Negative indices
        are not supported by the current _parse_peak_tag implementation.

        Parameters
        ----------
        peaks : NXreflections
            The peaks (NXreflections) group containing d-spacing and Miller indices
        fit : NXprocess
            The FIT (NXprocess) group containing peak_parameters and background_parameters

        Returns
        -------
        list[PeakCollection]
            List of reconstructed PeakCollection instances
        """
        from ._fit import _PeakParameters, _BackgroundParameters
        from ._definitions import GROUP_NAME, UNDEFINED_PEAK_TAG

        # Get the parameter groups
        pp = fit[GROUP_NAME.PEAK_PARAMETERS]
        bp = fit[GROUP_NAME.BACKGROUND_PARAMETERS]

        # A file written with peakss=[] (e.g. CombineRunsViewer's NXstress export,
        # which has no PeakCollection concept at all) has its title fields set to
        # the writer's own UNDEFINED_PEAK_TAG sentinel (see
        # _PeakParameters.init_group / _BackgroundParameters.init_group) -- there
        # is nothing to reconstruct. The reader previously didn't recognize its
        # own writer's sentinel and crashed trying to parse it as a real
        # PeakShape/BackgroundFunction name.
        pp_title = pp["title"].nxdata
        if isinstance(pp_title, bytes):
            pp_title = pp_title.decode()
        if pp_title == UNDEFINED_PEAK_TAG:
            return []

        # Get peak profile and background function from titles
        from pyrs.core.peak_profile_utility import PeakShape, BackgroundFunction

        peak_profile = PeakShape.getShape(pp["title"].nxdata)
        background_function = BackgroundFunction.getFunction(bp["title"].nxdata)

        # Get ranges for each PeakCollection
        ranges = cls.peakCollectionRanges(peaks)

        peak_collections = []
        for (phase_name, h, k, l_, mask), start, end in ranges:
            # Extract scan points for this range
            sub_runs_array = peaks["scan_point"].nxdata[start:end]

            # Get peak parameters
            native_peak_values, native_peak_errors = _PeakParameters.peakParametersForRange(pp, start, end)

            # Get background parameters
            bg_values, bg_errors = _BackgroundParameters.backgroundParametersForRange(bp, start, end)

            # Merge background into native peak arrays
            # A0 and A1 are always present, A2 only for Quadratic background
            native_peak_values["A0"] = bg_values["A0"]
            native_peak_values["A1"] = bg_values["A1"]
            native_peak_errors["A0"] = bg_errors["A0"]
            native_peak_errors["A1"] = bg_errors["A1"]
            # A2 only exists if background is Quadratic
            if "A2" in native_peak_values.dtype.names:
                native_peak_values["A2"] = bg_values["A2"]
                native_peak_errors["A2"] = bg_errors["A2"]

            param_values = native_peak_values
            param_errors = native_peak_errors

            # Reconstruct peak_tag with zero-padded Miller indices
            # Use max absolute value to ensure all indices have the same digit count
            max_val = max(abs(h), abs(k), abs(l_))
            N_d = len(str(max_val))
            peak_tag = f"{phase_name}{str(h).zfill(N_d)}{str(k).zfill(N_d)}{str(l_).zfill(N_d)}"

            # Extract d_reference and errors
            d_reference = peaks["center"].nxdata[start]
            d_reference_error = peaks["center_errors"].nxdata[start]

            # Construct PeakCollection with mask keyword
            pc = PeakCollection(
                peak_tag=peak_tag,
                peak_profile=peak_profile,
                background_type=background_function,
                wavelength=np.nan,  # Will be set by workspace if needed
                projectfilename="",
                runnumber=0,
                d_reference=d_reference,
                d_reference_error=d_reference_error,
                mask=mask,
            )

            # Set peak fitting values
            N = len(sub_runs_array)
            fit_costs = np.full(N, np.nan)
            pc.set_peak_fitting_values(sub_runs_array, param_values, param_errors, fit_costs)

            peak_collections.append(pc)

        return peak_collections
