import typing
from collections.abc import Generator
from pathlib import Path

import click

from too_many_repos.log import logger


def exec_file(file: Path, _globals):
    try:
        exec(compile(file.open().read(), file, "exec"), _globals)
    except FileNotFoundError:
        logger.warning(f"exec_file: Did not find {file}")
    except Exception as e:
        logger.warning(
            f"exec_file({file}) had {e.__class__.__name__}: {e}. Using default values."
        )
    else:
        logger.good(f"Loaded config file successfully: {file}")


def option(*param_decls, **attrs):
    """`show_default = True`.

    If `default` in `attrs` and `type` is not, or vice versa, sets one based on the other.

    Unless `default = None`, in which case `type` isn't set.

    `type` can be either:
     - type, i.e. `str`
     - tuple, i.e. `(str, int)`
     - `typing.Literal['foo']`
     - `click.typing.<Foo>` (which includes click.Choice(...))
    """

    def _append_help(_s):
        if attrs.get("help", click.core._missing) is click.core._missing:
            attrs["help"] = _s
        else:
            if "\n" in attrs["help"]:
                _s = f"\n{_s}"
            if attrs["help"].endswith("."):
                attrs["help"] += f" {_s}"
            else:
                attrs["help"] += f". {_s}"

    attrs["show_default"] = True
    default = attrs.get("default", click.core._missing)
    default_is_missing = default is click.core._missing
    typeattr = attrs.get("type", click.core._missing)
    type_is_missing = typeattr is click.core._missing
    is_multiple = attrs.get("multiple", click.core._missing) is True

    if type_is_missing:
        # if default=None, it's probably just a placeholder and
        # doesn't tell us above the 'real' type
        if not default_is_missing and default is not None:
            attrs["type"] = type(default)
        elif is_multiple:
            attrs["type"] = tuple

    else:
        # type is not missing
        if typing.get_origin(typeattr) is typing.Literal:
            # type=typing.Literal['foo']. build a click.Choice from it
            typeattr_args = typing.get_args(typeattr)
            attrs["type"] = click.Choice(typeattr_args)
            if default_is_missing:
                # take first Literal arg
                attrs["default"] = typeattr_args[0]

        else:
            # not a typing.Literal (e.g. `type=str`)
            if default_is_missing:
                if is_multiple:
                    attrs["default"] = (typeattr(),)
                else:
                    attrs["default"] = typeattr()

    if is_multiple:
        _append_help("Can be specified multiple times.")
    elif attrs.get("is_flag", click.core._missing) is True:
        _append_help("Flag.")
    try:
        type_name = attrs["type"].__name__.upper()
    except (AttributeError, KeyError):
        return click.option(*param_decls, **attrs)

    if attrs.get("metavar", click.core._missing) is not click.core._missing:
        attrs["metavar"] += f": {type_name}"
    else:
        attrs["metavar"] = type_name
    return click.option(*param_decls, **attrs)


def unrequired_opt(*param_decls, **attrs):
    """`required = False, show_default = True`.

    If `default` in `attrs` and `type` is not, or vice versa, sets one based on the other.

    Unless `default = None`, in which case `type` isn't set.

    `type` can be either:
     - type, i.e. `str`
     - tuple, i.e. `(str, int)`
     - `typing.Literal['foo']`
     - `click.typing.<Foo>` (which includes click.Choice(...))
    """

    attrs["required"] = False
    return option(*param_decls, **attrs)


def required_opt(*param_decls, **attrs):
    """`required = True, show_default = True`.

    If `default` in `attrs` and `type` is not, or vice versa, sets one based on the other.

    Unless `default = None`, in which case `type` isn't set.

    `type` can be either:
     - type, i.e. `str`
     - tuple, i.e. `(str, int)`
     - `typing.Literal['foo']`
     - `click.typing.<Foo>` (which includes click.Choice(...))
    """

    attrs["required"] = True
    return option(*param_decls, **attrs)


def safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except PermissionError:
        return False


def safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except PermissionError:
        return False


def safe_glob(path: Path, pattern: str) -> Generator[Path, None, None]:
    """Wraps glob to skip paths that raise PermissionError, and resume iterating when this happens."""
    try:
        for subpath in path.glob(pattern):
            yield subpath
    except PermissionError:
        pass
