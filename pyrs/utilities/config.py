"""
NXstress / legacy-IO output configuration, backed by `neutrons_standard.Config`.

Import `Config` from *this* module -- never `from neutrons_standard...import Config`
directly anywhere else in this codebase. `neutrons_standard.init("pyrs")` must run
before `neutrons_standard.config` is first imported (that module captures its
`package_name` once, at that moment, from `neutrons_standard.Spec.client_package_name`);
this module is the only place that ordering is guaranteed. A stray direct import
elsewhere would race `init()` and silently pin `package_name` to `None` for the rest of
the process (confirmed: this raises `ModuleNotFoundError: No module named 'None'` in
practice, from the `_Config` singleton's constructor).

The default configuration ships at `pyrs/resources/application.yml` -- this exact
filename and location (a genuine `pyrs.resources` subpackage) is a hard requirement of
`neutrons_standard`, not a PyRS convention. Override a value by setting the `env` OS
environment variable to a `.yml` file name or path; its contents are deep-merged on top
of the shipped default. See `neutrons_standard.config._Config.refresh` for the merge
mechanics.

`neutrons_standard.Config` provides no schema validation of its own (`_Config.validate`
is a no-op) -- `validate_config` below is PyRS's own rule.
"""

import neutrons_standard

neutrons_standard.init("pyrs")
from neutrons_standard.config import Config  # noqa: E402  (import must follow init())


#: Keys whose value must be a real YAML boolean.
BOOL_KEYS = (
    "nxstress.enable",
    "nxstress.use_production_names",
    "nxstress.merge_workspaces",
    "legacy_io.enable",
)

#: Keys whose value must be a non-blank string.
TEXT_KEYS = (
    "nxstress.instrument_name",
    "nxstress.instrument_short_name",
)

#: Keys whose value must be a filename suffix -- non-blank and leading-dot.
EXTENSION_KEYS = (
    "nxstress.extension",
    "legacy_io.extension",
)

#: Keys whose value must be a list of distinct non-blank strings.
LIST_KEYS = ("nxstress.discriminator_fields",)

#: Every key `validate_config` checks. `test_config.py` asserts this covers every
#: key `application.yml` ships, so adding one there without adding it here fails a
#: test rather than shipping an unchecked key.
VALIDATED_KEYS = BOOL_KEYS + TEXT_KEYS + EXTENSION_KEYS + LIST_KEYS


def validate_config() -> None:
    """Raise unless every key in `application.yml` holds the type it declares.

    `neutrons_standard.Config` performs no schema validation of its own
    (`_Config.validate` is a no-op), so nothing else will. A malformed override
    is not inert: `enable: "false"` is a YAML *string* and therefore truthy; a
    bare `discriminator_fields: direction` is a string, and a string is
    iterable, so it would be read one character at a time as five field names;
    and an `extension` without its leading dot reaches
    `pathlib.Path.with_suffix`, which raises `ValueError: Invalid suffix` from
    inside a save dialog.

    The keys are listed in `VALIDATED_KEYS` rather than checked inline so that a
    test can compare them against what `application.yml` actually ships -- the
    previous version checked four of nine while its docstring claimed all of
    them, which is the kind of gap prose cannot keep closed.

    Raises:
        RuntimeError: If any key holds the wrong type -- a non-bool for a
            boolean key, a blank or non-string for a text key, an extension that
            is blank or lacks its leading dot, or a `discriminator_fields` that
            is not a list of distinct non-blank strings.
        ValueError: If both `nxstress.enable` and `legacy_io.enable` are false --
            PyRS must be able to write at least one output format.
    """
    for key in BOOL_KEYS:
        value = Config[key]
        if not isinstance(value, bool):
            raise RuntimeError('Config["{}"] must be a bool, got {!r} ({})'.format(key, value, type(value).__name__))

    for key in TEXT_KEYS:
        value = Config[key]
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                'Config["{}"] must be a non-blank string, got {!r} ({})'.format(key, value, type(value).__name__)
            )

    for key in EXTENSION_KEYS:
        value = Config[key]
        if not isinstance(value, str) or not value.startswith("."):
            raise RuntimeError(
                'Config["{}"] must be a filename suffix beginning with ".", got {!r}.\n'
                "  It is passed to `pathlib.Path.with_suffix`, which raises on a suffix without "
                "one, and silently strips the extension when given an empty string.".format(key, value)
            )

    fields = Config["nxstress.discriminator_fields"]
    if not isinstance(fields, list):
        raise RuntimeError(
            'Config["nxstress.discriminator_fields"] must be a list of field names, got {!r} ({})'.format(
                fields, type(fields).__name__
            )
        )
    for field in fields:
        if not isinstance(field, str) or not field.strip():
            raise RuntimeError(
                'Config["nxstress.discriminator_fields"] entries must be non-blank strings, got {!r} in {}'.format(
                    field, fields
                )
            )
    if len(set(fields)) != len(fields):
        raise RuntimeError(
            'Config["nxstress.discriminator_fields"] names the same field more than once: {}'.format(fields)
        )

    if not (Config["nxstress.enable"] or Config["legacy_io.enable"]):
        raise ValueError("At least one of nxstress.enable or legacy_io.enable must be true")


# Fail fast at import time, rather than at the first NXstress-I/O callsite that
# happens to need a valid config.
validate_config()
