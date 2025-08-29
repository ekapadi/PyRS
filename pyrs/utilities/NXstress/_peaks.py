"""
pyrs/utilities/NXstress/_peaks.py

Private service class for NeXus NXstress-compatible I/O.
This class provides I/O for the `peaks` `NXreflections` subgroup:
  this subgroup includes fitted peak data, as used in reduction.
"""

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

import numpy as np
from nexusformat.nexus import (
    NXentry, NXreflections, NXfield
)
import re
from typing import Any, NamedTuple

from pyrs.peaks.peak_collection import PeakCollection
from pyrs.dataobjects.sample_logs import SampleLogs
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import CHUNK_SHAPE, FIELD_DTYPE

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
        l: int
        mask: str
        scan_point: int

        @classmethod
        def sort_key(cls, peaks: PeakCollection) -> tuple[Any]:
            # Define an ordering for `PeakCollection` instances
            phase_name, (h, k, l) = _Peaks._parse_peak_tag(peaks.peak_tag)
            mask = peaks.mask
            return (phase_name, h, k, l, mask)
                
    @classmethod
    def _parse_peak_tag(cls, tag: str) -> tuple[str, tuple[int, int, int]]:
        # Parse a peak-tag string into its <phase name> and Miller indices (h, k, l).
        maybeHKL = max(re.finditer(r"\d+", tag), key=lambda m: len(m.group(0)), default=None)
        if maybeHKL is None or len(maybeHKL.group(0)) % 3 != 0:
            raise RuntimeError(
                f"Unable to parse peak tag '{tag}' into its <phase name> and Miller indices (h, k, l)."
            )
        # Extract <phase name> as the rest of the tag.
        i, j = maybeHKL.span()
        phase = (tag[:i] + tag[j:]).strip()
        if not bool(phase):
            raise RuntimeError(
                f"Unable to parse <phase name> from peak tag '{tag}'."
            )
        
        # Extract (h, k, l)
        maybeHKL = maybeHKL.group(0)
        N_d = len(maybeHKL) // 3
        h, k, l = int(maybeHKL[0: N_d]), int(maybeHKL[N_d: 2 * N_d]), int(maybeHKL[2 * N_d: 3 * N_d])
        
        return phase, (h, k, l)
        
    @classmethod
    def _init(cls, logs: SampleLogs) -> NXreflections:
        # Initialize the 'PEAKS' group
        peaks = NXreflections()

        peaks['scan_point'] = NXfield(np.empty((0,), dtype=np.int32),
                                      maxshape=(None,), chunks=CHUNK_SHAPE(1))

        peaks['h'] = NXfield(np.empty((0,), dtype=np.int32),
                             maxshape=(None,), chunks=CHUNK_SHAPE(1),
                             units='')
        peaks['k'] = NXfield(np.empty((0,), dtype=np.int32),
                             maxshape=(None,), chunks=CHUNK_SHAPE(1),
                             units='')
        peaks['l'] = NXfield(np.empty((0,), dtype=np.int32),
                             maxshape=(None,), chunks=CHUNK_SHAPE(1),
                             units='')
        
        peaks['phase_name'] = NXfield(np.empty((0,), dtype=FIELD_DTYPE.STRING.value),
                                      maxshape=(None,), chunks=CHUNK_SHAPE(1))
        
        peaks['mask'] = NXfield(np.empty((0,), dtype=FIELD_DTYPE.STRING.value),
                                      maxshape=(None,), chunks=CHUNK_SHAPE(1))
        
        ## Components of the normalized scattering vector Q in the sample reference frame
        ##   'qx', 'qy', and 'qz' are *required* by NXstress, but it looks as if PyRS doesn't
        ##   use these -- initialize to `NaN`.
        peaks['qx'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan)
        peaks['qx'].attrs['units'] = '1'        
        peaks['qy'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan)        
        peaks['qy'].attrs['units'] = '1'        
        peaks['qz'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan)        
        peaks['qz'].attrs['units'] = '1'        
        ##

        peaks['center'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,), chunks=CHUNK_SHAPE(1),
            units='angstrom'
        )        
        peaks['center_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='angstrom')
        peaks['center_type'] = NXfield('d-spacing')  
        
        # Sample position for each subrun -- initialize to `NaN`.
        ss_units = {
            ## work around: units may be an empty string
            'sx': logs.units('sx') if bool(logs.units('sx')) else 'mm',
            'sy': logs.units('sy') if bool(logs.units('sy')) else 'mm',
            'sz': logs.units('sz') if bool(logs.units('sz')) else 'mm',
        }
        peaks['sx'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan,
                              units=ss_units['sx'])
        peaks['sy'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan,
                              units=ss_units['sy'])
        peaks['sz'] = NXfield(np.empty((0,), dtype=np.float64),
                              maxshape=(None,), chunks=CHUNK_SHAPE(1), fillvalue=np.nan,
                              units=ss_units['sz'])

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
        phase_name, (h, k, l) = cls._parse_peak_tag(peak_collection.peak_tag)
        mask = peak_collection.mask
        
        # Each dataset has scan point as its first index.
        phase_name = np.array((phase_name,) * N_scan) 
        h, k, l = np.array((h,) * N_scan), np.array((k,) * N_scan), np.array((l,) * N_scan)
        mask = np.array((mask,) * N_scan)
        
        d_reference, d_reference_error = peak_collection.get_d_reference()
        d_reference = np.array((d_reference,) * N_scan)
        d_reference_error = np.array((d_reference_error,) * N_scan)
        
        curr_len = peaks['h'].shape[0]
        new_len = curr_len + N_scan
        
        peaks['scan_point'].resize((new_len,))
        
        peaks['h'].resize((new_len,))
        peaks['k'].resize((new_len,))
        peaks['l'].resize((new_len,))
        peaks['phase_name'].resize((new_len,))
        peaks['mask'].resize((new_len,))

        # For `PEAKS` (NXreflections) group: 'center' means `d_reference`.
        peaks['center'].resize((new_len,))
        peaks['center_errors'].resize((new_len,))
        
        peaks['sx'].resize((new_len,))
        peaks['sy'].resize((new_len,))
        peaks['sz'].resize((new_len,))
        
        peaks['scan_point'][curr_len:] = scan_point
        peaks['h'][curr_len:] = h
        peaks['k'][curr_len:] = k
        peaks['l'][curr_len:] = l
        peaks['phase_name'][curr_len:] = phase_name
        peaks['mask'][curr_len:] = mask
        
        peaks['center'][curr_len:] = d_reference.ravel()
        peaks['center_errors'][curr_len:] = d_reference_error.ravel()
        
        """ # This doesn't make sense!
        peaks['sx'][curr_len:] = logs['sx']
        peaks['sy'][curr_len:] = logs['sy']
        peaks['sz'][curr_len:] = logs['sz']
        """ # TODO: fix this!
        peaks['sx'][curr_len:] = np.full((N_scan,), np.nan) 
        peaks['sy'][curr_len:] = np.full((N_scan,), np.nan) 
        peaks['sz'][curr_len:] = np.full((N_scan,), np.nan)

        return peaks
