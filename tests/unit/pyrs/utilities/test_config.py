"""
Tests for `pyrs/utilities/config.py`.

Every test here requests the `default_config` fixture (see
`tests/unit/pyrs/utilities/conftest.py`) and imports `pyrs.utilities.config` only
*inside* the test body -- never at module level. A module-level import would run
`pyrs.utilities.config`'s side effects (writing a backup file under `~/.pyrs/`)
against the real home directory at test-collection time, before the fixture has had
a chance to redirect `HOME` to a `tmp_path`.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type-checking -- see tests/unit/pyrs/utilities/conftest.py's
    # `default_config` fixture for why a real runtime import here is unsafe.
    from neutrons_standard.config import _Config


def test_default_config_loads_shipped_defaults(default_config: "_Config") -> None:
    """Test that the shipped `pyrs/resources/application.yml` values load unmodified."""
    # Arrange / Act
    config = default_config

    # Assert
    assert config["nxstress.enable"] is True
    assert config["nxstress.extension"] == ".nxs"
    assert config["nxstress.use_production_names"] is False
    assert config["legacy_io.enable"] is True
    assert config["legacy_io.extension"] == ".h5"


def test_default_config_env_override_merges_on_top_of_default(default_config: "_Config", tmp_path: Path) -> None:
    """Test that an `env`-named override file deep-merges onto the shipped default.

    Only `nxstress.enable` is overridden; `legacy_io.*` (untouched by the override
    file) must still come through from the shipped default -- confirming a merge,
    not a wholesale replacement.
    """
    # Arrange
    override_file = tmp_path / "override.yml"
    override_file.write_text("nxstress:\n  enable: false\n")

    # Act
    config = default_config
    config.loadEnv(str(override_file))

    # Assert
    assert config["nxstress.enable"] is False
    assert config["legacy_io.enable"] is True  # unaffected key survives the merge


def test_validate_config_passes_with_shipped_defaults(default_config: "_Config") -> None:
    """Test that `validate_config()` raises nothing when both formats are enabled."""
    # Arrange
    import pyrs.utilities.config as config_module

    # Act / Assert
    config_module.validate_config()  # no exception


def test_validate_config_raises_when_both_formats_disabled(default_config: "_Config", tmp_path: Path) -> None:
    """Test that `validate_config()` rejects a config with no output format enabled."""
    # Arrange
    import pytest

    import pyrs.utilities.config as config_module

    override_file = tmp_path / "override.yml"
    override_file.write_text("nxstress:\n  enable: false\nlegacy_io:\n  enable: false\n")
    default_config.loadEnv(str(override_file))

    # Act / Assert
    with pytest.raises(ValueError, match="At least one of nxstress.enable or legacy_io.enable must be true"):
        config_module.validate_config()


def test_validate_nxstress_enable_not_bool(default_config: "_Config", tmp_path: Path) -> None:
    """Test that a non-bool `nxstress.enable` (e.g. a quoted YAML string) is rejected
    up front, rather than silently passing the truthiness check (`bool("false")` is
    `True` in Python).
    """
    # Arrange
    import pytest

    import pyrs.utilities.config as config_module

    override_file = tmp_path / "override.yml"
    override_file.write_text('nxstress:\n  enable: "false"\n')  # quoted -- stays a str, not a bool
    default_config.loadEnv(str(override_file))

    # Act / Assert
    with pytest.raises(RuntimeError, match='Config\\["nxstress.enable"\\] must be a bool'):
        config_module.validate_config()


def test_validate_legacy_io_enable_not_bool(default_config: "_Config", tmp_path: Path) -> None:
    """Test that a non-bool `legacy_io.enable` (e.g. an int) is rejected up front."""
    # Arrange
    import pytest

    import pyrs.utilities.config as config_module

    override_file = tmp_path / "override.yml"
    override_file.write_text("legacy_io:\n  enable: 1\n")  # int, not a bool
    default_config.loadEnv(str(override_file))

    # Act / Assert
    with pytest.raises(RuntimeError, match='Config\\["legacy_io.enable"\\] must be a bool'):
        config_module.validate_config()


class TestDiscriminatorConfigKeys:
    """`nxstress.discriminator_fields` and `nxstress.merge_workspaces`.

    Both are typed, and neither type is one YAML gets right by accident:
    `discriminator_fields: direction` (no list) parses as a string, and a
    string is iterable, so an unchecked value would be read one character at a
    time as five one-letter field names.
    """

    def test_shipped_defaults(self, default_config: "_Config") -> None:
        assert default_config["nxstress.discriminator_fields"] == []
        assert default_config["nxstress.merge_workspaces"] is False

    def test_validate_config_rejects_a_bare_string(self, default_config: "_Config", tmp_path: Path) -> None:
        import pytest

        import pyrs.utilities.config as config_module

        override_file = tmp_path / "override.yml"
        override_file.write_text("nxstress:\n  discriminator_fields: direction\n")
        default_config.loadEnv(str(override_file))

        with pytest.raises(RuntimeError, match="must be a list of field names"):
            config_module.validate_config()

    def test_validate_config_rejects_a_blank_entry(self, default_config: "_Config", tmp_path: Path) -> None:
        import pytest

        import pyrs.utilities.config as config_module

        override_file = tmp_path / "override.yml"
        override_file.write_text("nxstress:\n  discriminator_fields: ['direction', '  ']\n")
        default_config.loadEnv(str(override_file))

        with pytest.raises(RuntimeError, match="non-blank strings"):
            config_module.validate_config()

    def test_validate_config_rejects_a_repeated_field(self, default_config: "_Config", tmp_path: Path) -> None:
        import pytest

        import pyrs.utilities.config as config_module

        override_file = tmp_path / "override.yml"
        override_file.write_text("nxstress:\n  discriminator_fields: ['direction', 'direction']\n")
        default_config.loadEnv(str(override_file))

        with pytest.raises(RuntimeError, match="more than once"):
            config_module.validate_config()

    def test_validate_config_rejects_non_bool_merge_workspaces(
        self, default_config: "_Config", tmp_path: Path
    ) -> None:
        import pytest

        import pyrs.utilities.config as config_module

        override_file = tmp_path / "override.yml"
        override_file.write_text('nxstress:\n  merge_workspaces: "true"\n')
        default_config.loadEnv(str(override_file))

        with pytest.raises(RuntimeError, match="must be a bool"):
            config_module.validate_config()

    def test_validate_config_accepts_a_well_formed_field_list(self, default_config: "_Config", tmp_path: Path) -> None:

        import pyrs.utilities.config as config_module

        override_file = tmp_path / "override.yml"
        override_file.write_text("nxstress:\n  discriminator_fields: ['direction']\n  merge_workspaces: true\n")
        default_config.loadEnv(str(override_file))

        config_module.validate_config()  # must not raise


class TestConfigOverrideReachesBoundNames:
    """`config_override` must be visible to modules that bound `Config` the documented way.

    `config.py`'s docstring instructs `from pyrs.utilities.config import Config`,
    which binds the singleton *by value*. `default_config` reloads the module and
    so replaces that singleton, leaving every such module reading the previous
    instance -- which silently made config-dependent behaviour untestable:
    `_Instrument._instrument_names()` returned the shipped default no matter what
    a test configured.

    These pin the fix. They deliberately exercise **production** modules rather
    than reading `Config` directly, because reading it directly is the one access
    pattern that was never broken.
    """

    def test_production_modules_share_the_live_singleton(self):
        """The invariant underneath all of this, asserted directly.

        Requests no config fixture on purpose: it checks the *ambient* session
        state, so it fails if any fixture earlier in the run swapped the
        singleton without putting it back -- which `default_config` used to do,
        orphaning every consumer for the remainder of the session.
        """
        import pyrs.utilities.config as config_module
        from pyrs.utilities.NXstress._discriminator import Config as discriminator_bound
        from pyrs.utilities.NXstress._instrument import Config as instrument_bound

        assert instrument_bound is config_module.Config
        assert discriminator_bound is config_module.Config

    def test_override_reaches_a_module_that_bound_config(self, config_override):
        # Arrange
        from pyrs.utilities.NXstress._instrument import _Instrument

        assert _Instrument._instrument_names() == ("HB2B", "HB2B")

        # Act
        config_override({"nxstress": {"instrument_name": "OVERRIDDEN"}})

        # Assert
        assert _Instrument._instrument_names() == ("OVERRIDDEN", "HB2B")

    def test_override_reaches_the_discriminator_module(self, config_override):
        # Arrange
        from pyrs.utilities.NXstress import _discriminator

        assert _discriminator.field_names() == ()

        # Act
        config_override({"nxstress": {"discriminator_fields": ["direction"]}})

        # Assert
        assert _discriminator.field_names() == ("direction",)

    def test_the_override_is_undone_afterwards(self, config_override):
        """Guards the teardown: a leaked override would make later tests lie."""
        from pyrs.utilities.config import Config

        assert Config["nxstress.instrument_name"] == "HB2B"
        config_override({"nxstress": {"instrument_name": "LEAKED"}})
        assert Config["nxstress.instrument_name"] == "LEAKED"

    def test_sibling_keys_survive_a_partial_override(self, config_override):
        """A shallow assignment would drop every key the override does not mention."""
        # Arrange
        from pyrs.utilities.config import Config

        enabled = Config["nxstress.enable"]

        # Act
        config_override({"nxstress": {"instrument_name": "OVERRIDDEN"}})

        # Assert
        assert Config["nxstress.instrument_name"] == "OVERRIDDEN"
        assert Config["nxstress.enable"] == enabled
