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

        inst = _Instrument.init_group(ws)

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

        inst = _Instrument.init_group(ws)

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
        inst = _Instrument.init_group(ws)

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
            inst = _Instrument.init_group(ws)

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
        inst = _Instrument.init_group(ws)
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
