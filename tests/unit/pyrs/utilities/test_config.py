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
