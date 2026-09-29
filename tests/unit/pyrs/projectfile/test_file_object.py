"""
Source-scan guarantees for pyrs/projectfile/file_object.py.

These do not exercise behaviour; they pin a property of the source itself. The
plan series that produced them scheduled an audit of two "legacy log name" FIXMEs
in this module, and that work turned out to have been done upstream already --
the silent fallback to a capitalized "2Theta" key was replaced by an explicit
RuntimeError telling the user to re-reduce. A whole planning cycle was spent
re-discovering that, which a test would have reported on the first commit after
the fix landed.
"""

import ast
import inspect
import re

import pyrs.projectfile.file_object as file_object_module


def test_no_legacy_log_name_fixme():
    """Verify no legacy log-name FIXME remains in file_object.py.

    The legacy path silently accepted a capitalized "2Theta" key written by an
    older reduction. It is now an explicit error, so any reappearance of a FIXME
    naming a legacy log key means that regression is back.
    """
    # Arrange
    source = inspect.getsource(file_object_module)

    # Act: a FIXME on a line that also mentions a log name or the legacy key
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "FIXME" in line and re.search(r"legacy|2Theta|log[ _]name", line, re.IGNORECASE)
    ]

    # Assert
    assert not offenders, f"legacy log-name FIXME(s) reintroduced: {offenders}"


def test_two_theta_key_is_canonical():
    """Verify the module reads two-theta through HidraConstants, not a literal.

    The legacy defect was a hard-coded capitalized key. Requiring the constant
    keeps a second spelling from creeping back in.

    Docstrings are excluded deliberately: the RuntimeError that *replaced* the
    legacy fallback names the old "2Theta" key in its own documentation, which is
    a description of the fix, not a reoccurrence of the defect. A plain text scan
    cannot tell those apart -- walking the AST can.
    """
    # Arrange
    source = inspect.getsource(file_object_module)
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    # Act: string constants in executable code, not documentation
    literal_keys = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value == "2Theta"
        and id(node) not in docstrings
    ]

    # Assert
    assert not literal_keys, f"capitalized legacy two-theta key present in code: {literal_keys}"
