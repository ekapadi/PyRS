.. _IO_prototype:

==================
NeXus IO prototype
==================

.. contents
  :local:
  
Overview
--------
The objective of the NeXus IO-prototype work was to provide a first-pass implementation of NeXus-compliant output using the existing ``NXstress`` schema.
For purposes of the implementation, it was deemed sufficient to provide *output* methods.  If *input* methods are also required, these should be straightforward to implement.

Primarily, the classes ``HidraProjectFile``, ``HidraWorkspace``, and ``PeakCollection`` are used to obtain information about the reduced data.
Supporting classes such as ``SampleLogs``, and ``InstrumentSetup`` are also used, where information about the instrument and th experiment specifics is required.

A sub-objective was to provide an output format that could include *all* of the data associated with an experiment, such as input-data and any additional normalization spectra.  However, it should be noted that including this information is *optional* with respect to the output format, and it is also common to include this information by simply specifying the input-data file names in appropriate fields.

The next sections provide a correspondance between the python classes, and sections within the ``NXstress`` schema.  Any place where there's still confusion, or there is simply not enough information to meet the requirements of the schema, will be indicated using bold text.

For purposes of the prototype, the ``nexusformat`` python package is used in the implementation, and that working group's validator has been used for validation of compliance.  With respect to validation, its important to use a validator that allows *overriding* NeXus base-class definitions, which ``NXstress`` does extensively.  With respect to the latter, NeXus International Advisory Committee's (NIAC) C-language validator is an *incomplete* implementation, and gives misleading results.

Primary ``NXentry`` group
-------------------------

Issues found:

#. **Providing a single *start-time* and *end-time* for the experiment**.  Right now I left these as lists by scan-point (aka *subrun* number in PyRS).  We could alternatively use the minimum and maximum over all of the sub-run times to obtain these values.  (*Leaving* these fields as lists is possibly non-compliant, but would not be a big deal.)

#. ``FIT`` groups: at present I implemented these as one group per detector mask -- this needs to be extended to include *solid-angle* masks.

#. ``PEAKS`` group: only a single PEAKS group is allowed. (See discussion of "extensions" at end of this document.)


Multiple ``FIT`` (``NXprocess``) groups
---------------------------------------

Each of these groups includes the reduced and normalized *datagram* corresponding to a single detector mask.
These groups also include the parameter-values from the peak fit results.


Issues found:

#. **The splitting of the ``PeakCollection`` fields between ``FIT`` and ``PEAKS`` subgroups from ``NXstress`` was a bit confusing**.  **It also isn't clear whether or not we ever have a *background* that is *measured* data** -- at present that option isn't (yet) supported by the prototype.

#. ** Not yet in PyRS but required in ``NXstress``: ``FIT/DIFFRACTOGRAM/fit``, ``fit_errors``: these datasets should contain the reconstructed spectrum
   from the fitted model.  We don't seem to have methods to do this yet, so these are initialized to NaN.**
   

Single ``PEAKS`` group
----------------------

This group is intended to contain the canonical (or *reference*) peak values.


Issues found:

#. **Converting from ``PyRS`` <peak tag> format to <phase name> and ``(h, k, l)`` (Miller indices) tags**.
At present we make this conversion automatically using a regular-expression based parser, however this is not an ideal solution.  Here it might be better if these values were specified *explicitly* by PyRS.

#. **It's assumed that ``PeakCollection.d_reference`` provides the required values to include in this section**.

#. **``(sx, sy, sz) are included from the logs, but mostly just because the logs had the same variable names -- **this is probably incorrect**!

#. **``(qx, qy, qz) are required by ``NXstress`` (, components of the normalized scattering vector Q in the sample reference frame)**.   These seem to have no correspondance in the current PyRS codebase -- these values are initialized to ``NaN``.



``SAMPLE`` (NXsample) group
---------------------------
This was complicated!  Again the main issue is the *naming* of things in ``NXstress`` vs. the naming in the PyRS codebase

Issues found:

#. **Using ``PointList.(vx, vy, vz)`` as the sample positions**?  Is this correct?

#. **Possible mis-match between per-scan-point logs, and logs which have a single value for the entire experiment**.  This needs to be checked log-by-log!

#. Where at all possible, *all* of the available logs have been included in an additional ``logs`` (``NXcollection``) subgroup.



``INSTRUMENT`` (NXinstrument) group
-----------------------------------

Issues found:
-------------

#. **Treatment of masks is incomplete**.  An attempt has been made to fully implement detector masks.  This assumes that a ``<default>`` mask will always exist, but at present there's no way (yet) to distinguish between solid-angle and detector masks.

#. ***Calibrated* vs. *uncalibrated* instrument is only partially treated*.  This needs to be carefully examined to make sure the treatment is correct.

#. **Monochromator information is only partially available**.

#. **There is a whole lot of room for adjustments and *corrections* in this section!**


Possible extensions
-------------------
If it would be desireable to include fit results from multiple peaks, this can be accomplished by implementing multiple ``NXentry`` groups, with their ``<input data>``, ``<reduced data>``, and etc. sections (i.e. *most* datasets that contain an actual spectrum), linking back to the original ``NXentry``.


