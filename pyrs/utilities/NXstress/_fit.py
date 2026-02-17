"""
pyrs/utilities/NXstress/_fit.py

Private service class for NeXus NXstress-compatible I/O.
This class provides I/O for the `fit` `NXprocess` subgroup:
  this subgroup includes the reduced output data as a 'diffraction_data' `NXdata` group.
"""

from datetime import datetime
from nexusformat.nexus import (
    NXdata, NXfield, NXnote, NXparameters, NXprocess
)
import numpy as np
from typing import Tuple

from pyrs.peaks.peak_collection import PeakCollection
from pyrs.core.peak_profile_utility import (
    BackgroundFunction, EFFECTIVE_PEAK_PARAMETERS
)
from pyrs.core.workspaces import HidraWorkspace
from pyrs.dataobjects.sample_logs import SampleLogs
from pyrs.utilities.pydantic_transition import validate_call_

from ._definitions import (
    FIELD_DTYPE, CHUNK_SHAPE, DEFAULT_TAG,
    GROUP_NAME, EFFECTIVE_BACKGROUND_PARAMETERS,
    group_naming_scheme
)
from ._peaks import _Peaks

"""
REQUIRED PARAMETERS FOR NXstress:
---------------------------------

├─ fit                                    (NXprocess, group)
│   ├─ date                               (dataset: ISO8601 string)
│   ├─ program                            (dataset: string)
│   ├─ description                         (NXnote, group)
│   ├─ peakparameters                      (NXparameters, group)
│   └─ diffractogram                       (NXdata, group)
│        ├─ diffractogram                  (dataset)
│        ├─ diffractogram_errors           (dataset)
│        ├─ daxis/xaxis                    (dataset)
│        ├─ @axes                          (attribute: string)
│        └─ @signal                        (attribute: string)
"""

class _PeakParameters:

    @classmethod
    def _init(cls, peakss: list[PeakCollection]) -> NXparameters:
        # required 'peak_parameters' subgroup
        pp = NXparameters()
        peak_profile = peakss[0].peak_profile
        
        # To be compliant with `NXstress` schema:
        #   this cannot be tiled: all `PeakCollection` must share the same `peak_profile`.
        pp['title'] = NXfield(str(peak_profile).lower(), dtype=FIELD_DTYPE.STRING.value)
        
        pp['center'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='degree'
        )
        pp['center_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='degree'
        ) 
        pp['height'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        ) 
        pp['height_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        ) 
        pp['fwhm'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='degree'
        ) 
        pp['fwhm_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='degree'
        )
        
        # Voigt or Pseudo-Voigt: Lorentzian fraction
        pp['form_factor'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='1'
        )
        pp['form_factor_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='1'
        )
        
        return pp
          
    @classmethod
    @validate_call_
    def init_group(cls, peakss: list[PeakCollection]) -> NXparameters:
        # required 'peak_parameters' subgroup
        pp = cls._init(peakss)

        for peak_collection in sorted(peakss, key=_Peaks.PeakIndex.sort_key):
            cls._append_peak(pp, peak_collection)
        
        return pp
                    
    @classmethod
    @validate_call_
    def _append_peak(cls, pp: NXparameters, peaks: PeakCollection) -> NXparameters:
        # Append the peak parameters from a single `PeakCollection` instance.
        
        # Verify the `PeakCollection` peak-profile type.
        peak_profile = str(peaks.peak_profile).lower()
        if peak_profile != pp['title']:
            raise ValueError(
                f"All `PeakCollection` must share the same peak profile ''{pp['title']}'', not ''{peak_profile}''."
            )

        # Use _effective_ peak parameters here: all peaks will then have the same number of parameter,
        #   and all parameter values will be in the expected column.
        # We have one new parameter value for each of 'N_scan' subruns.
                        
        N_scan = len(peaks.sub_runs)
        cur_rows = pp['center'].shape[0]
        new_rows = cur_rows + N_scan
        
        ## In the following, make sure to include _only_ the peak-function parameters.
        params_value, params_error = peaks.get_effective_params()
        
        pp['center'].resize((new_rows,))
        pp['center_errors'].resize((new_rows,))
        pp['height'].resize((new_rows,))
        pp['height_errors'].resize((new_rows,))
        pp['fwhm'].resize((new_rows,))
        pp['fwhm_errors'].resize((new_rows,))
        pp['form_factor'].resize((new_rows,))
        pp['form_factor_errors'].resize((new_rows,))
        
        pp['center'][cur_rows:] = params_value['Center'].astype(np.float64)
        pp['center_errors'][cur_rows:] = params_error['Center'].astype(np.float64)
        pp['height'][cur_rows:] = params_value['Height'].astype(np.float64)
        pp['height_errors'][cur_rows:] = params_error['Height'].astype(np.float64)
        pp['fwhm'][cur_rows:] = params_value['FWHM'].astype(np.float64)
        pp['fwhm_errors'][cur_rows:] = params_error['FWHM'].astype(np.float64)

        # Voigt or Pseudo-Voigt: Lorentzian fraction
        pp['form_factor'][cur_rows:] = (1.0 - params_value['Mixing']).astype(np.float64)
        pp['form_factor_errors'][cur_rows:] = params_error['Mixing'].astype(np.float64)
        
        return pp

    @classmethod
    def peakParametersForRange(cls, pp, start: int, end: int) -> tuple:
        """Extract peak parameters for a specific range and convert to native parameters.
        
        Reads effective parameters from the NXparameters group, slices to the specified range,
        and converts to native parameters using the appropriate converter.
        
        CRITICAL: form_factor is stored as (1 - Mixing), so we invert: Mixing = 1 - form_factor
        
        Parameters
        ----------
        pp : NXparameters
            Peak parameters group
        start : int
            Starting index (inclusive)
        end : int
            Ending index (exclusive)
            
        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (native_values, native_errors) structured arrays
        """
        from pyrs.core.peak_profile_utility import (
            PeakShape, get_parameter_dtype, get_effective_parameters_converter
        )
        
        # Get peak profile type
        peak_shape = PeakShape.getShape(pp['title'].nxdata)
        
        # Build effective parameter structured arrays
        N = end - start
        eff_values = np.zeros(N, dtype=get_parameter_dtype(effective=True))
        eff_errors = np.zeros(N, dtype=get_parameter_dtype(effective=True))
        
        # Slice datasets and populate effective arrays
        eff_values['Center'] = pp['center'].nxdata[start:end]
        eff_values['Height'] = pp['height'].nxdata[start:end]
        eff_values['FWHM'] = pp['fwhm'].nxdata[start:end]
        
        # CRITICAL: Invert form_factor to Mixing
        eff_values['Mixing'] = 1.0 - pp['form_factor'].nxdata[start:end]
        
        eff_errors['Center'] = pp['center_errors'].nxdata[start:end]
        eff_errors['Height'] = pp['height_errors'].nxdata[start:end]
        eff_errors['FWHM'] = pp['fwhm_errors'].nxdata[start:end]
        eff_errors['Mixing'] = pp['form_factor_errors'].nxdata[start:end]
        
        # Intensity is not stored separately (derived from Height/FWHM/Mixing)
        # Set to NaN - will be recalculated if needed
        eff_values['Intensity'] = np.nan
        eff_errors['Intensity'] = np.nan
        
        # A0, A1, A2 are not in peak_parameters - will be merged from background
        eff_values['A0'] = 0.0
        eff_values['A1'] = 0.0
        eff_values['A2'] = 0.0
        eff_errors['A0'] = 0.0
        eff_errors['A1'] = 0.0
        eff_errors['A2'] = 0.0
        
        # Convert to native parameters
        converter = get_effective_parameters_converter(peak_shape)
        native_values, native_errors = converter.calculate_native_parameters(eff_values, eff_errors)
        
        return native_values, native_errors
        
class _BackgroundParameters:

    @classmethod
    def _init(cls, peakss: list[PeakCollection]) -> NXparameters:
        # required 'background_parameters' subgroup
        bp = NXparameters()

        # To be compliant with `NXstress` schema:
        #   this cannot be tiled: all `PeakCollection` must share the same `background_type`.
        background_function = BackgroundFunction.getFunction(peakss[0].background_type)
        bp['title'] = NXfield(str(background_function).lower(), dtype=FIELD_DTYPE.STRING.value) 

        bp['A0'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )
        bp['A0_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )

        bp['A1'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )
        bp['A1_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )        

        bp['A2'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )
        bp['A2_errors'] = NXfield(
            np.empty((0,), dtype=np.float64),
            maxshape=(None,),
            chunks=CHUNK_SHAPE(1),
            units='counts'
        )
        
        return bp
                          
    @classmethod
    @validate_call_
    def init_group(cls, peakss: list[PeakCollection]) -> NXparameters:
        # required 'background_parameters' subgroup
        bp = cls._init(peakss)

        for peak_collection in sorted(peakss, key=_Peaks.PeakIndex.sort_key):
            cls._append_peak(bp, peak_collection)
        
        return bp
                           
    @classmethod
    @validate_call_
    def _append_peak(cls, bp: NXparameters, peaks: PeakCollection) -> NXparameters:
        # Append the background parameters from a single `PeakCollection` instance.
        
        # Verify the `PeakCollection` background type.
        background_function = BackgroundFunction.getFunction(peaks.background_type)
        background_title = str(background_function).lower()
        if background_title != bp['title']:
            raise ValueError(
                f"All `PeakCollection` must share the same background type ''{bp['title']}'', not ''{background_title}''."
            )

        ## In the following, make sure to include _only_ the background parameters.
        params_value, params_error = peaks.get_effective_params()
        
        N_scan = len(peaks.sub_runs)
        cur_rows = bp['A0'].shape[0]
        new_rows = cur_rows + N_scan
        
        bp['A0'].resize((new_rows,))
        bp['A0_errors'].resize((new_rows,))        
        bp['A1'].resize((new_rows,))
        bp['A1_errors'].resize((new_rows,))        
        bp['A2'].resize((new_rows,))
        bp['A2_errors'].resize((new_rows,))
        
        bp['A0'][cur_rows:,] = params_value['A0'].astype(np.float64) 
        bp['A0_errors'][cur_rows:,] = params_error['A0'].astype(np.float64) 
        bp['A1'][cur_rows:,] = params_value['A1'].astype(np.float64) 
        bp['A1_errors'][cur_rows:,] = params_error['A1'].astype(np.float64) 
        bp['A2'][cur_rows:,] = params_value['A2'].astype(np.float64) 
        bp['A2_errors'][cur_rows:,] = params_error['A2'].astype(np.float64) 
        
        return bp

    @classmethod
    def backgroundParametersForRange(cls, bp, start: int, end: int) -> tuple:
        """Extract background parameters for a specific range.
        
        Reads background coefficients from the NXparameters group and slices to the specified range.
        
        Parameters
        ----------
        bp : NXparameters
            Background parameters group
        start : int
            Starting index (inclusive)
        end : int
            Ending index (exclusive)
            
        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (eff_bg_values, eff_bg_errors) structured arrays with A0, A1, A2 fields
        """
        from pyrs.core.peak_profile_utility import get_parameter_dtype
        
        # Build effective background parameter arrays
        N = end - start
        eff_bg_values = np.zeros(N, dtype=get_parameter_dtype(effective=True))
        eff_bg_errors = np.zeros(N, dtype=get_parameter_dtype(effective=True))
        
        # Slice datasets and populate arrays
        eff_bg_values['A0'] = bp['A0'].nxdata[start:end]
        eff_bg_values['A1'] = bp['A1'].nxdata[start:end]
        eff_bg_values['A2'] = bp['A2'].nxdata[start:end]
        
        eff_bg_errors['A0'] = bp['A0_errors'].nxdata[start:end]
        eff_bg_errors['A1'] = bp['A1_errors'].nxdata[start:end]
        eff_bg_errors['A2'] = bp['A2_errors'].nxdata[start:end]
        
        return eff_bg_values, eff_bg_errors
               
class _Diffractogram:

    @classmethod
    def _get_diffraction_data(cls, ws: HidraWorkspace, mask_name: str) -> Tuple[np.ndarray, np.ndarray]:
        # Workaround for PyRS codebase use of `None` as the default key.
        data_key, errors_key = cls._diffraction_data_keys(mask_name)
        return ws._diff_data_set[data_key], ws._var_data_set[errors_key]

    @classmethod
    def _diffraction_data_keys(cls, mask_name: str) -> Tuple[str, str]:
        # Workaround for PyRS codebase use of `None` as the default key.
        if mask_name != DEFAULT_TAG:
            data_key = mask_name
            errors_key = f"{mask_name}_var"
        else:
            data_key = None # <default key>
            errors_key = 'main_var'
        return data_key, errors_key 
        
    @classmethod
    def _init(cls, ws: HidraWorkspace) -> NXdata:
        if ws._2theta_matrix is None:
            raise RuntimeError("Usage error: cannot write NXstress file: workspace doesn't include any reduced data.")        
        dg = NXdata()
        return dg 

    @classmethod
    @validate_call_
    def init_group(cls, ws: HidraWorkspace, maskName: str, peakss: list[PeakCollection]) -> NXdata:
        # required DIFFRACTOGRAM (NXdata) subgroup:        
        data_key, errors_key = cls._diffraction_data_keys(maskName)
        if data_key not in ws._diff_data_set or errors_key not in ws._var_data_set:
            # *** DEBUG ***
            print(f"==> Workspace: diffraction data keys: {ws._diff_data_set.keys()}, error keys: {ws._var_data_set.keys()}")
            raise RuntimeError(f"Reduced data for mask '{maskName}' is not attached to the workspace.")
        
        dg = cls._init(ws)
        dg.attrs['signal'] = GROUP_NAME.DGRAM_DIFFRACTOGRAM
        dg.attrs['auxiliary_signals'] = [
            GROUP_NAME.DGRAM_DIFFRACTOGRAM_ERRORS,
            GROUP_NAME.DGRAM_FIT,
            GROUP_NAME.DGRAM_FIT_ERRORS
        ] 
        dg.attrs['axes'] = ['scan_point', '.'] # do _not_ specify a 2-D theta in 'axes'
        dg.attrs['two_theta_indices'] = [0, 1] # two-theta has shape (<N scan points>, <N 2-theta, per scan-point>)
        dg['scan_point'] = NXfield(ws.get_sub_runs())
        dg['scan_point'].attrs['units'] = ''
        
        two_theta = ws._2theta_matrix
        # dg['two_theta'] = NXfield(
        dg[GROUP_NAME.DGRAM_TWO_THETA_NAME] = NXfield( # *** DEBUG *** validator bug
            two_theta,
            units='degree'
        )
        
        data, errors = cls._get_diffraction_data(ws, maskName)
        dg[GROUP_NAME.DGRAM_DIFFRACTOGRAM] = NXfield(
            data,
            dtype=FIELD_DTYPE.FLOAT_DATA.value,
            interpretation='spectrum',
            units='counts'
        )
 
        dg[GROUP_NAME.DGRAM_DIFFRACTOGRAM_ERRORS] = NXfield(
            errors,
            dtype=FIELD_DTYPE.FLOAT_DATA.value,
            units='counts'
        )
        
        # ENTRY/FIT/DIFFRACTOGRAM/fit, fit_errors: required datasets: these should contain the spectrum reconstructed from the fitted model.
        #   For the moment, this will be initialized to NaN.
        dg[GROUP_NAME.DGRAM_FIT] = NXfield(np.empty((0, 0), dtype=np.float64),
                                           maxshape=(None, None), chunks=CHUNK_SHAPE(2), fillvalue=np.nan)
        dg[GROUP_NAME.DGRAM_FIT].attrs['interpretation'] = 'spectrum'
        dg[GROUP_NAME.DGRAM_FIT].attrs['units'] = 'counts'                                        
        dg[GROUP_NAME.DGRAM_FIT_ERRORS] = NXfield(np.empty((0, 0), dtype=np.float64),
                                                  maxshape=(None, None), chunks=CHUNK_SHAPE(2), fillvalue=np.nan)
        dg[GROUP_NAME.DGRAM_FIT_ERRORS].attrs['units'] = 'counts'                                        
        
        return dg
        

class _Fit:
    ########################################
    # ALL methods must be `classmethod`.  ##
    ########################################

    ##
    ## Notes:
    ## -- Under 'NXstress', there can be multiple FIT (NXprocess) groups in the NXentry, but the results from only 
    ##    one of these should be promoted to the canonical fit results in the PEAKS (NXreflections) group.
    ## -- FIT (NXprocess) contains the as-fit peak and background parameters, including any information associated
    ##    with the fitting process.  In this section, any appropriate coordinate system may be used.
    ## -- Not yet in PyRS: FIT/DIFFRACTOGRAM/fit, fit_errors: these datasets should contain the reconstructed spectrum
    #     from the fitted model.  We don't seem to have methods to do this yet, so these are initialized to NaN.
    ## -- The canonical fit results in PEAKS (NXreflections) should contain the final results, converted to the final
    ##    coordinate system (e.g. usually `d-spacing`).
    ##
    @classmethod
    @validate_call_
    def _init(
        cls,
        logs: SampleLogs, *,
        processing_description: str,
        processing_time
    ) -> NXprocess:
        # Initialize the 'FIT' (NXprocess) group:

        fit = NXprocess()
        
        input_ = NXparameters()
        input_['description'] = f'Peak fits and reduced diffractogram data'
        fit[GROUP_NAME.INPUT] = input_
        
        # Required information fields:
        fit['date'] = NXfield(processing_time)
        fit['program'] = NXfield('PyRS')
        fit['raw_data_file'] = NXfield(logs['Filename'][0].decode('utf-8'))

        note = NXnote(
            type='text/plain',
            description='Processing description',
            # author='',
            # date='',
            data=processing_description
        )
        fit[GROUP_NAME.DESCRIPTION] = note

        return fit
    
    @classmethod
    @validate_call_
    def init_group(
        cls,
        ws: HidraWorkspace,
        peakss: list[PeakCollection],
        logs: SampleLogs,
        processing_description: str = '',
        processing_time: str = None
    ):
        # Initialize a new 'FIT' (NXprocess) group:
        #   (see `_definitions.group_naming_scheme`).
        
        ## Under `NXstress`: `FIT` (NXprocess) groups contain peak and background-fit results, including any
        ##    information relevant to the fitting process used.
        fit = cls._init(
            logs,
            processing_description=processing_description,
            processing_time=processing_time if bool(processing_time) else datetime.now().astimezone().isoformat()
        )
        fit[GROUP_NAME.PEAK_PARAMETERS] = _PeakParameters.init_group(peakss)
        fit[GROUP_NAME.BACKGROUND_PARAMETERS] = _BackgroundParameters.init_group(peakss)
        
        # Add one DIFFRACTOGRAM group for each mask present in the workspace.
        masks = set(ws._mask_dict.keys())
        if None in masks:
            masks.remove(None)
        masks.add(DEFAULT_TAG)
        for mask in masks:
            ## TODO: mask naming (and storage) is messed up.  They all need to be accessed the same way,
            ##   regardless of whether or not the "default" mask is being accessed.
            ##   Here we assume that this loop also accesses data for the _DEFAULT_ mask, and that the default
            ##   mask has the '_DEFAULT_' name, and not some other name, such as 'main' or `None`?!          
            dgram_name = group_naming_scheme(GROUP_NAME.DIFFRACTOGRAM, mask)
            if dgram_name in fit.NXdata:
                raise RuntimeError(
                    f"Usage error: DIFFRACTOGRAM (NXdata) group '{dgram_name}' already exists in the current (NXprocess) group."
                )
            fit[dgram_name] = _Diffractogram.init_group(ws, mask, peakss)
        
        return fit

    @classmethod
    def validateWorkspaceAndPeaksData(cls, ws: HidraWorkspace, peakss: list[PeakCollection]):
        # VERIFY that scan_point[s] and mask[s] reference by any `PeakCollection` are present in the workspace.
        scan_point = set(ws.get_sub_runs().raw_copy())
        
        masks = set(ws._mask_dict.keys())
        if None in masks:
            masks.remove(None)
        masks.add(DEFAULT_TAG)

        for peaks in peakss:
            # VERIFY that any <scan point> referenced by any `PeakCollection` is included in the workspace.
            
            # Note: `PeakCollection.get_sub_runs()` is *broken*:
            #   it does not actually return a `SubRuns` instance!
            peaks_scan_point = set(peaks._sub_run_array.raw_copy())
            if not peaks_scan_point.issubset(scan_point):
                raise ValueError(
                    f"Scan points {peaks_scan_point}, required by `PeakCollection`,\n"
                    f"  are not present in workspace scan points {scan_point}."
                )
        
            # VERIFY that any <mask> referenced by any `PeakCollection` is included in the workspace.
            peaks_mask = peaks.mask
            data_key, errors_key = _Diffractogram._diffraction_data_keys(peaks_mask)
            if data_key not in ws._diff_data_set or errors_key not in ws._var_data_set:
                raise ValueError(
                    f"Reduced data required for mask '{peaks_mask}', required by `PeakCollection`,\n"
                    f"  is not present in the workspace '{masks}'."
                )
