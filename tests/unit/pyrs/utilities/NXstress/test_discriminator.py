"""Unit tests for `pyrs/utilities/NXstress/_discriminator.py`.

Covers the two halves of the discriminator resolver, the configuration it reads,
and the reserved-column guard that keeps a configured field from shadowing an
`NXreflections` column. The multi-workspace I/O these support is exercised in
`test_multi_workspace.py`.
"""

import numpy as np
import yaml
import pytest

from pyrs.core.workspaces import HidraWorkspace
from pyrs.dataobjects.sample_logs import SampleLogs, SubRuns
from pyrs.utilities.restorable_property import is_restorable
from pyrs.utilities.NXstress import _discriminator
from pyrs.utilities.NXstress._peaks import _Peaks


def configure(config_override, yaml_text: str) -> None:
    """Apply an `nxstress` config override that production modules can actually see.

    Goes through `config_override` rather than `config_override`: the latter swaps
    the `Config` singleton, leaving every module that bound it the documented way
    reading the previous instance. See that fixture's docstring.
    """
    config_override(yaml.safe_load(yaml_text))


def workspace_with_logs(**logs) -> HidraWorkspace:
    ws = HidraWorkspace("discriminator-test")
    sub_runs = np.array([1, 2, 3])
    for name, values in logs.items():
        ws.set_sample_log(name, sub_runs, np.asarray(values))
    return ws


class TestReservedColumns:
    def test_reserved_columns_matches_peaks_init(self):
        """The guard's reserved set must be exactly what `_Peaks._init` writes.

        Stated as an iteration over the real group rather than as a second
        hand-maintained list: a column added to `_init` without being added to
        `RESERVED_PEAK_COLUMNS` would otherwise silently become assignable as a
        discriminator name, and shadow itself on disk.
        """
        logs = SampleLogs()
        logs.subruns = SubRuns([1, 2, 3])

        written = set(_Peaks._init(logs))

        assert written == set(_discriminator.RESERVED_PEAK_COLUMNS)

    def test_field_colliding_with_reserved_column_raises(self, config_override, tmp_path):
        configure(config_override, "nxstress:\n  discriminator_fields: ['mask']\n")

        with pytest.raises(ValueError, match="collides with the reserved"):
            _discriminator.field_names()

    def test_only_a_reserved_name_encodes_onto_a_reserved_column(self):
        """Why checking the *encoded* name is sufficient, and not merely cautious.

        The guard compares `allowed_identifier(field)` against the reserved set,
        which only catches everything because the encoding is injective: no
        field spelled differently from a reserved column can encode onto one.
        Asserting that here means the guard stays sufficient if the encoding is
        ever changed -- a many-to-one encoding would let an innocuous field name
        silently land on a reserved column, the same class of collision
        Decisions row 23 removed from `allowed_identifier` itself.
        """
        for reserved in _discriminator.RESERVED_PEAK_COLUMNS:
            assert _discriminator.column_name(reserved) == reserved

        candidates = {"direction", "run_number", "HB2B:direction", "2theta", "a.b", "_x_"}
        encoded = {name: _discriminator.column_name(name) for name in candidates}

        assert not set(encoded.values()) & set(_discriminator.RESERVED_PEAK_COLUMNS)
        assert len(set(encoded.values())) == len(candidates), f"encoding is not injective: {encoded}"


class TestFieldNames:
    def test_default_is_empty(self, config_override, tmp_path):
        assert _discriminator.field_names() == ()
        assert _discriminator.merge_workspaces() is False

    def test_configured_names_are_returned_in_order(self, config_override, tmp_path):
        configure(config_override, "nxstress:\n  discriminator_fields: ['b_field', 'a_field']\n")

        assert _discriminator.field_names() == ("b_field", "a_field")

    def test_blank_name_raises(self, config_override, tmp_path):
        configure(config_override, "nxstress:\n  discriminator_fields: ['  ']\n")

        with pytest.raises(ValueError, match="non-blank strings"):
            _discriminator.field_names()

    def test_repeated_name_raises(self, config_override, tmp_path):
        configure(config_override, "nxstress:\n  discriminator_fields: ['direction', 'direction']\n")

        with pytest.raises(ValueError, match="more than once"):
            _discriminator.field_names()

    def test_merge_workspaces_override(self, config_override, tmp_path):
        configure(config_override, "nxstress:\n  merge_workspaces: true\n")

        assert _discriminator.merge_workspaces() is True


class TestResolve:
    def test_property_is_preferred_over_a_log(self):
        ws = workspace_with_logs(name=np.array(["from-the-log"] * 3))

        assert _discriminator.resolve(ws, "name") == "discriminator-test"

    def test_unrelated_method_name_falls_through_to_the_log(self):
        """A bare `hasattr` would return the bound method instead of a value."""
        ws = workspace_with_logs(save_experimental_data=np.array(["11"] * 3))

        assert _discriminator.resolve(ws, "save_experimental_data") == "11"

    def test_constant_log_resolves_to_its_single_value(self):
        ws = workspace_with_logs(direction=np.array(["22"] * 3))

        assert _discriminator.resolve(ws, "direction") == "22"

    def test_log_varying_across_scan_points_raises(self):
        ws = workspace_with_logs(direction=np.array(["11", "22", "33"]))

        with pytest.raises(AssertionError, match="multiple items"):
            _discriminator.resolve(ws, "direction")

    def test_name_in_neither_place_raises(self):
        ws = workspace_with_logs(direction=np.array(["11"] * 3))

        with pytest.raises(ValueError, match="not found in allowed value list"):
            _discriminator.resolve(ws, "absent_field")


class TestApply:
    def test_log_fallback_round_trips_through_resolve(self):
        ws = workspace_with_logs(direction=np.array(["11"] * 3))

        _discriminator.apply(ws, "written_back", "22")

        assert _discriminator.resolve(ws, "written_back") == "22"

    def test_settable_property_is_used_by_both_halves(self):
        """The shape spec 05 will take, with `direction` as a real property.

        `HidraWorkspace` defines no settable property today, so the subject is
        stubbed rather than asserted of a class that has none.
        """

        class _Stubbed(HidraWorkspace):
            @property
            def direction(self):
                return self._stub_direction

            @direction.setter
            def direction(self, value):
                self._stub_direction = value

        ws = _Stubbed("stub")
        ws.set_sample_log("direction", np.array([1, 2, 3]), np.array(["11"] * 3))

        _discriminator.apply(ws, "direction", "33")

        assert _discriminator.resolve(ws, "direction") == "33"

    def test_read_only_property_falls_back_to_the_log(self):
        """`prop.fset is not None` is what stops `setattr` raising here."""
        ws = workspace_with_logs(direction=np.array(["11"] * 3))

        # `name` is a read-only property on HidraWorkspace.
        _discriminator.apply(ws, "name", "written-to-the-log")

        assert ws.name == "discriminator-test"
        assert ws.get_sample_log_value("name") == "written-to-the-log"


class TestKey:
    def test_key_is_name_ordered_regardless_of_configured_order(self):
        ws = workspace_with_logs(
            b_field=np.array(["beta"] * 3),
            a_field=np.array(["alpha"] * 3),
        )

        forward = _discriminator.key(ws, ("a_field", "b_field"))
        reversed_ = _discriminator.key(ws, ("b_field", "a_field"))

        assert forward == reversed_
        assert _discriminator.sort_values(forward) == ("alpha", "beta")

    def test_empty_names_give_an_empty_key(self):
        ws = workspace_with_logs(direction=np.array(["11"] * 3))

        assert _discriminator.key(ws, ()) == ()


class TestEveryPropertyRoundTripsOrIsRefused:
    """No `HidraWorkspace` property may be readable as a discriminator but not restorable.

    `resolve` prefers a property over a sample log, so a field naming a read-only
    property was read from the property and written back to a *log*: the value
    went to the file correctly and came back as the constructor's default, with
    nothing raising. `write(read(f))` then stored something different from `f`.

    This sweeps `vars(HidraWorkspace)` rather than naming properties, so a
    property added later is covered without editing this test -- which is the
    whole point, since the original defect was a property nobody thought about.
    The partition is exhaustive: every property must be in exactly one branch.
    """

    @staticmethod
    def _properties():
        return {name: prop for name, prop in vars(HidraWorkspace).items() if isinstance(prop, property)}

    def test_the_sweep_finds_properties(self):
        """A sweep that matched nothing would pass both branches vacuously."""
        assert self._properties(), "no properties found; the sweep's heuristic has drifted"

    def test_restorable_properties_round_trip(self, minimal_HidraWorkspace):
        # Arrange
        restorable_names = [n for n in self._properties() if is_restorable(HidraWorkspace, n)]
        assert restorable_names, "no restorable properties; expected at least `direction`"

        for name in restorable_names:
            ws = minimal_HidraWorkspace(with_instrument=False)

            # Act
            _discriminator.apply(ws, name, "sentinel-value")

            # Assert
            assert _discriminator.resolve(ws, name) == "sentinel-value", name

    def test_settable_or_restorable_properties_are_accepted_as_fields(self, config_override):
        for name, prop in self._properties().items():
            if prop.fset is None and not is_restorable(HidraWorkspace, name):
                continue
            config_override({"nxstress": {"discriminator_fields": [name]}})
            assert _discriminator.field_names() == (name,), name

    def test_plain_read_only_properties_are_refused_as_fields(self, config_override):
        """Refused at configuration time, before any file exists to be written wrong."""
        # Arrange
        refusable = [
            n
            for n, p in self._properties().items()
            if p.fset is None
            and not is_restorable(HidraWorkspace, n)
            and _discriminator.column_name(n) not in _discriminator.RESERVED_PEAK_COLUMNS
        ]
        assert refusable, "expected at least `name` to be a plain read-only property"

        for name in refusable:
            # Act / Assert
            config_override({"nxstress": {"discriminator_fields": [name]}})
            with pytest.raises(ValueError, match=r"read-only `HidraWorkspace` property"):
                _discriminator.field_names()
