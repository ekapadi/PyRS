"""
pyrs/utilities/restorable_property.py

A read-only property whose backing attribute may be restored by I/O reconstruction.

A reader that rebuilds an object from a file has to put back every value the
object would normally have been given at construction. For a plain attribute
that is easy. For a **read-only property** it is not: the value is public and
readable, but there is no supported way to write it, so a round trip silently
loses it -- the reconstructed object answers with whatever its constructor
defaulted to, and nothing raises.

The usual escapes are both unattractive. Making the property read/write puts a
setter on the public API purely for the benefit of a deserializer, inviting
casual assignment that the class did not intend to allow. Adding a
`set_<name>()` method does the same thing in different spelling. Keeping a
registry of "property -> backing attribute" somewhere else works, but it is a
second place to edit and it drifts silently when someone adds a property and
forgets.

`restorable_property` instead puts the declaration **on the property itself**:

    class Thing:
        @restorable()                        # restores `_colour`
        def colour(self): return self._colour

        @restorable(restores="_file_path")   # when the names do not correspond
        def source_file(self): return self._file_path

The property stays read-only -- `thing.colour = "red"` still raises
`AttributeError` -- and because it subclasses `property`, every `isinstance(...,
property)` test elsewhere continues to see it. A reader restores through
`restore()`, and code that needs to know in advance whether a name can be
restored asks `is_restorable()`. Both are total: a sweep over `vars(cls)`
partitions properties into restorable and not, so a test can assert something
about *every* property without naming any of them.

Typical use, from `pyrs/utilities/NXstress/_discriminator.py`::

    if is_restorable(ws, name):
        restore(ws, name, value)
"""

from typing import Any, Callable, Optional


class restorable_property(property):
    """A read-only `property` that names a backing attribute an I/O reader may write.

    Subclasses `property` rather than replacing it, so a `restorable_property` is
    still a `property` to every `isinstance` check in the codebase and behaves
    identically on read. No setter is installed, so assignment through the
    property raises `AttributeError` exactly as it did before.

    Attributes:
        restores: Name of the instance attribute `restore()` writes. Defaults to
            the getter's name with a leading underscore.

    Example:
        >>> class Thing:
        ...     def __init__(self): self._colour = "blue"
        ...     @restorable_property
        ...     def colour(self): return self._colour
        >>> Thing().colour
        'blue'
        >>> type(Thing()).colour.restores
        '_colour'
    """

    def __init__(self, fget=None, fset=None, fdel=None, doc=None, *, restores: Optional[str] = None):
        super().__init__(fget, fset, fdel, doc)
        if restores is None:
            if fget is None:
                raise TypeError(
                    "`restorable_property` needs either a getter to derive the backing attribute "
                    "name from, or an explicit `restores=`."
                )
            restores = f"_{fget.__name__}"
        # Always a `str` from here: `restore()` passes it straight to `setattr`, and
        # an optional name would make that call unsound for no benefit.
        self.restores: str = restores

    def getter(self, fget):  # pragma: no cover - not used, but must not silently drop `restores`
        return type(self)(fget, self.fset, self.fdel, self.__doc__, restores=self.restores)

    def setter(self, fset):
        raise TypeError(
            "A `restorable_property` is read-only by construction: it exists so that a value can be "
            "restored by an I/O reader WITHOUT becoming publicly writable.\n"
            "  If the value should be publicly settable, use an ordinary read/write `property` instead."
        )


def restorable(restores: Optional[str] = None) -> Callable[[Callable], restorable_property]:
    """Decorator form of `restorable_property`, with an optional backing-attribute name.

    Args:
        restores: Instance attribute `restore()` should write. Defaults to the
            decorated function's name with a leading underscore, which is the
            common case; give it explicitly when the property and its backing
            attribute are not spelled alike.

    Returns:
        A decorator producing a `restorable_property`.

    Example:
        >>> class Thing:
        ...     def __init__(self): self._file_path = None
        ...     @restorable(restores="_file_path")
        ...     def source_file(self): return self._file_path
        >>> type(Thing()).source_file.restores
        '_file_path'
    """

    def decorate(fget: Callable) -> restorable_property:
        return restorable_property(fget, restores=restores)

    return decorate


def is_restorable(obj: Any, name: str) -> bool:
    """Whether `name` is a restorable property of `obj`.

    Args:
        obj: An instance, or a class.
        name: Attribute name to test.

    Returns:
        True when `name` resolves to a `restorable_property` on the type.
    """
    owner = obj if isinstance(obj, type) else type(obj)
    return isinstance(getattr(owner, name, None), restorable_property)


def restore(obj: Any, name: str, value: Any) -> None:
    """Write `value` to the backing attribute of `obj`'s restorable property `name`.

    Args:
        obj: Instance being reconstructed.
        name: Name of a `restorable_property` on its type.
        value: Value to restore.

    Raises:
        TypeError: If `name` is not a restorable property of `obj` -- restoring
            something that merely *looks* assignable is how a reconstruction
            quietly writes to the wrong place.

    Example:
        >>> class Thing:
        ...     def __init__(self): self._colour = "blue"
        ...     @restorable()
        ...     def colour(self): return self._colour
        >>> t = Thing(); restore(t, "colour", "red"); t.colour
        'red'
    """
    prop = getattr(type(obj), name, None)
    if not isinstance(prop, restorable_property):
        raise TypeError(
            f"'{type(obj).__name__}.{name}' is not a restorable property, so it cannot be restored.\n"
            f"  Mark it with `@restorable()` if an I/O reader is expected to put its value back."
        )
    setattr(obj, prop.restores, value)
