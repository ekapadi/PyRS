# ruff: noqa: F841
"""
Tests for pyrs/utilities/NXstress/_instrument.py
"""

from collections.abc import Callable
import logging

import numpy as np
from nexusformat.nexus import NXcollection, NXinstrument, NXdetector_module
import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.utilities.NXstress import _instrument as _instrument_module
from pyrs.utilities.NXstress._instrument import _Instrument, _Masks
from pyrs.utilities.NXstress._definitions import DEFAULT_TAG
from pyrs.utilities.NXstress.NXstress import NXstress
from tests.util.mask_helpers import add_named_detector_mask


class TestInstrument:
    """Test suite for _instrument.py"""

    def test_Masks_init(self):
        """Verify _Masks._init creates empty NXcollection with required fields"""
        masks = _Masks._init()

        assert isinstance(masks, NXcollection)
        assert "names" in masks
        assert "detector" in masks
        assert "solid_angle" in masks

        # Verify empty structure
        assert len(masks["names"]) == 0
        assert isinstance(masks["detector"], NXcollection)
        assert isinstance(masks["solid_angle"], NXcollection)

    def test_Masks_init_group_with_default_mask(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify default mask appears in masks with DEFAULT_TAG name"""
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)

        masks = _Masks.init_group(ws)

        assert isinstance(masks, NXcollection)
        assert DEFAULT_TAG in masks["names"]
        assert DEFAULT_TAG in masks["detector"]

    def test_Masks_init_group_append(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify calling init_group twice (detector then solid_angle) populates both"""
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)

        # First call for detector masks
        masks = _Masks.init_group(ws)
        initial_count = len(masks["names"])

        # Second call for solid angle masks (appending)
        # For this test, we'll use the same workspace but we'll just change the names.
        defaults = ws._diff_data_set[None], ws._var_data_set[None], ws._mask_dict.get(None, None)
        ws._diff_data_set = {f"{k}_2nd": v for k, v in ws._diff_data_set.items() if k is not None}
        ws._var_data_set = {f"{k}_2nd": v for k, v in ws._var_data_set.items() if k is not None}
        ws._mask_dict = {f"{k}_2nd": v for k, v in ws._mask_dict.items() if k is not None}
        # Re-add the default items:
        ws._diff_data_set[None], ws._var_data_set[None] = defaults[0:2]
        if defaults[2]:
            ws._mask_dict[None] = defaults[2]

        # In real usage, solid angle masks would be different data
        masks = _Masks.init_group(ws, masks=masks)

        # Names should have been appended
        assert len(masks["names"]) >= initial_count

    def test_Masks_init_group_duplicate_raises(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify behavior when attempting to add duplicate masks

        A non-default named mask is added to the workspace.  The first call to
        `init_group` writes it; the second call must raise because the same
        name is already present in the masks group.
        """
        ws = minimal_HidraWorkspace(with_instrument=True)

        # Add a non-default named mask so that `mask_keys(ws)` contains a
        # name other than DEFAULT_TAG.  The first `init_group` call will write
        # it; the second call will find it already in `names` and raise.
        add_named_detector_mask(ws, "test_mask")

        masks = _Masks.init_group(ws)

        with pytest.raises(RuntimeError, match=r".*Usage error: mask .* has already been written.*"):
            masks2 = _Masks.init_group(ws, masks=masks)

    def test_Instrument_init(self):
        """Verify _Instrument._init creates NXinstrument with name and short_name"""
        inst = _Instrument._init("HB2B", "HB2B")

        assert isinstance(inst, NXinstrument)
        assert "name" in inst
        assert inst["name"] == "HB2B"
        assert inst["name"].attrs["short_name"] == "HB2B"

    def test_Instrument_detector_module_fields(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify NXdetector_module contains required fields"""
        ws = minimal_HidraWorkspace(with_instrument=True)

        inst = _Instrument.init_group([ws])

        assert "DETECTOR" in inst
        detector = inst["DETECTOR"]
        assert "detector_bank" in detector

        det_module = detector["detector_bank"]
        assert isinstance(det_module, NXdetector_module)

        # Verify required fields
        assert "data_size" in det_module
        assert "fast_pixel_direction" in det_module
        assert "slow_pixel_direction" in det_module
        assert "depends_on" in det_module

        # Verify data_size is 2D array [rows, cols]
        assert len(det_module["data_size"]) == 2
        assert det_module["data_size"].dtype == np.int64

    def test_Instrument_transformations_chain(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify all 8 transformations exist and depends_on chain is correct"""
        ws = minimal_HidraWorkspace(with_instrument=True)

        inst = _Instrument.init_group([ws])

        detector = inst["DETECTOR"]
        assert "transformations" in detector

        trans = detector["transformations"]

        # Verify all 8 transformations exist
        expected_transforms = [
            "translation_x",
            "translation_y",
            "translation_z",
            "distance",
            "rotation_x",
            "rotation_y",
            "rotation_z",
            "two_theta_zero",
        ]

        for name in expected_transforms:
            assert name in trans
            # Each transformation should have required attributes
            assert "transformation_type" in trans[name].attrs
            assert "vector" in trans[name].attrs
            assert "depends_on" in trans[name].attrs

        # Verify depends_on chain
        # First transformation depends on '.'
        assert trans["translation_x"].attrs["depends_on"] == "."

        # Subsequent transformations form a chain
        assert trans["translation_y"].attrs["depends_on"] == "./transformations/translation_x"
        assert trans["translation_z"].attrs["depends_on"] == "./transformations/translation_y"
        assert trans["distance"].attrs["depends_on"] == "./transformations/translation_z"

        # The detector's depends_on is the chain's ENTRY POINT, so it must name the
        # LAST link -- traversal follows each field's own depends_on back to ".".
        # This previously asserted "translation_x", the first link, whose depends_on
        # is "." -- a chain that terminates immediately, leaving the other seven
        # transformations written but unreachable.
        assert detector["depends_on"] == "./transformations/two_theta_zero"

    # The instrument identity comes from config, not from the workspace: the Hidra
    # project format records no instrument name anywhere. Overriding it is what lets
    # this writer serve a beamline other than HB2B without a code change.

    def test_Instrument_name_from_config(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Verify instrument name and short_name are taken from configuration"""
        # Arrange
        monkeypatch.setattr(
            _instrument_module,
            "Config",
            {"nxstress.instrument_name": "HB2A", "nxstress.instrument_short_name": "PG3"},
        )
        ws = minimal_HidraWorkspace(with_instrument=True)

        # Act
        inst = _Instrument.init_group([ws])

        # Assert
        assert str(inst["name"].nxvalue) == "HB2A"
        assert inst["name"].attrs["short_name"] == "PG3"

    def test_Instrument_name_blank_falls_back(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ):
        """Verify a blank configured name falls back to HB2B, and says so"""
        # Arrange
        monkeypatch.setattr(
            _instrument_module,
            "Config",
            {"nxstress.instrument_name": "   ", "nxstress.instrument_short_name": ""},
        )
        ws = minimal_HidraWorkspace(with_instrument=True)

        # Act
        with caplog.at_level(logging.WARNING):
            inst = _Instrument.init_group([ws])

        # Assert
        assert str(inst["name"].nxvalue) == "HB2B"
        assert inst["name"].attrs["short_name"] == "HB2B"
        assert "unset or blank" in caplog.text

    def test_Instrument_all_transformations_reachable(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
    ):
        """Verify every transformation written is reached from the detector.

        A transformation the chain never reaches cannot affect the geometry, however
        faithfully it was written. The traversal rule is spelled out here rather than
        imported from the writer, so this fails if the writer changes rather than
        tracking it.
        """
        # Arrange
        ws = minimal_HidraWorkspace(with_instrument=True)
        inst = _Instrument.init_group([ws])
        detector = inst["DETECTOR"]
        trans = detector["transformations"]
        written = {name for name in trans}

        # Act: follow depends_on from the detector until '.'
        reached = []
        current = str(detector["depends_on"].nxvalue)
        while current and current != ".":
            name = current.rsplit("/", 1)[-1]
            assert name in trans, f"depends_on points outside the group: {current!r}"
            assert name not in reached, f"cycle in the depends_on chain at {name!r}"
            reached.append(name)
            current = str(trans[name].attrs.get("depends_on", "."))

        # Assert
        assert set(reached) == written, f"unreachable: {sorted(written - set(reached))}"


class TestMaskGroupHoldsOnlyRealMasks:
    """`masks/names` lists detector masks, and every one of them has an array.

    It used to list *diffractogram keys* too -- `_Masks.mask_keys` unioned
    `_diff_data_set` in -- so a texture entry advertised `eta_-5.0` as a mask and
    resolved it to nothing. The `NXlink` meant to patch that was never serialised,
    and had it worked it would have returned the default array under each composite
    key, inflating `_mask_dict` on read with entries the original workspace never
    had.
    """

    @staticmethod
    def _texture(ws):
        """Eta-only reductions: every one is the default mask ∩ an eta ROI."""
        sub_runs = ws.get_sub_runs().raw_copy()
        two_theta = np.tile(np.linspace(60.0, 120.0, 20), (len(sub_runs), 1))
        ones = np.ones((len(sub_runs), 20))
        keys = ("eta_-5.0", "eta_0.0", "eta_5.0")
        ws.set_reduced_diffraction_data_set(two_theta, {k: ones for k in keys}, {k: ones.copy() for k in keys})
        return keys

    def test_diffractogram_keys_are_not_listed_as_masks(self, minimal_HidraWorkspace: Callable[..., HidraWorkspace]):
        # Arrange
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        self._texture(ws)

        # Act
        masks = _Masks.init_group(ws)
        # `nxvalue` returns a bare `str` for a length-1 array, not a 1-element list.
        names = [str(n) for n in np.atleast_1d(masks["names"].nxvalue)]

        # Assert
        assert names == [DEFAULT_TAG]
        assert not any("eta" in name for name in names)

    def test_every_listed_mask_resolves_to_an_array(self, minimal_HidraWorkspace: Callable[..., HidraWorkspace]):
        """The property the old `NXlink` was trying and failing to provide."""
        # Arrange
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True, mask_names=("mask_a",))
        self._texture(ws)

        # Act
        masks = _Masks.init_group(ws)
        names = [str(n) for n in np.atleast_1d(masks["names"].nxvalue)]

        # Assert
        assert set(names) == {DEFAULT_TAG, "mask_a"}
        for name in names:
            assert name in masks["detector"] or name in masks["solid_angle"], name

    def test_a_solid_angle_shaped_mask_raises_rather_than_being_guessed(
        self, minimal_HidraWorkspace: Callable[..., HidraWorkspace]
    ):
        """Nothing loads one yet, so writing one is refused instead of approximated.

        The old heuristic filed a mask under `solid_angle/` whenever it was 1-D,
        even-length and floating -- which is every square detector's mask if it is
        ever stored as float.
        """
        # Arrange
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=True)
        ws.set_detector_mask(np.array([-5.0, 5.0]), False, "roi")

        # Act / Assert
        with pytest.raises(NotImplementedError, match=r"[Ss]olid-angle masks are not implemented"):
            _Masks.init_group(ws)

    def test_a_generated_default_mask_can_be_read_back(
        self,
        minimal_HidraWorkspace: Callable[..., HidraWorkspace],
        minimal_PeakCollection,
        tmp_path,
    ):
        """A workspace with no mask of its own wrote a file PyRS could not read.

        `_generate_default_mask` returned `np.ones(detector_size)` -- 2-D
        `(nrows, ncols)` -- while `set_detector_mask` refuses any 2-D array whose
        second axis is not 1. Every round-trip test used `with_masks=True`, so the
        generated-default path was never exercised.
        """
        # Arrange
        sub_runs = np.array([1, 2, 3])
        ws = minimal_HidraWorkspace(with_instrument=True, with_masks=False, sub_runs=sub_runs)
        peaks = [minimal_PeakCollection(N_subrun=3, sub_runs=sub_runs)]
        path = tmp_path / "generated_default.nxs"

        # Act
        with NXstress(path, "w") as nx:
            nx.write([ws], [peaks])
        with NXstress(path, "r") as nx:
            workspaces, _ = nx.read()

        # Assert
        recovered = np.asarray(workspaces[0].get_detector_mask(True))
        assert recovered.ndim == 1
        nrows, ncols = ws.get_instrument_setup().detector_size
        assert recovered.shape == (nrows * ncols,)
