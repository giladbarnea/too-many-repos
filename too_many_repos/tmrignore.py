import re
import sys
from contextlib import suppress
from pathlib import Path
from typing import ForwardRef, Iterable, List, Set, Union

from rich.table import Table

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton

IgnorableType = Union[str, re.Pattern, Path, ForwardRef("Ignorable")]


def is_regexlike(string: str) -> bool:
    """Chars that can't be a file path and used often in regexps"""
    # Check for anchors at start or end
    if string.startswith("^") or string.endswith("$"):
        return True

    # Check for basic regex operators
    regex_syntax_characters = [
        "+",
        "?",
        "*",
        "|",
        "\\",
    ]
    if any(op in string for op in regex_syntax_characters):
        return True

    # Check for quantifier patterns
    quantifier_patterns = [
        r"\{[0-9]+\}",  # {n}
        r"\{[0-9]+,\}",  # {n,}
        r"\{[0-9]+,[0-9]+\}",  # {n,m}
        r"\{,[0-9]+\}",  # {,n}
    ]
    if any(re.search(pattern, string) for pattern in quantifier_patterns):
        return True

    # Check for character classes and groups
    if re.search(r"\[.+]", string, re.DOTALL) or re.search(
        r"\(.+\)", string, re.DOTALL
    ):
        return True

    # Check for special character classes
    special_classes = [
        # digits
        r"\d",
        r"\D",
        # whitespace
        r"\s",
        r"\S",
        r"\n",  # newline
        r"\r",  # carriage return
        r"\t",  # tab
        r"\f",  # form feed
        r"\v",  # vertical tab
        # word characters
        r"\w",
        r"\W",
        # word boundaries
        r"\b",
        r"\B",
        r"\A",
        # string boundaries
        r"\Z",
        r"\z",
    ]
    if any(special_class in string for special_class in special_classes):
        return True

    # Check for lookahead and lookbehind assertions
    if any(
        pattern in string
        for pattern in [
            "(?=",  # Positive lookahead
            "(?!",  # Negative lookahead
            "(?<=",  # Positive lookbehind
            "(?<!",  # Negative lookbehind
        ]
    ):
        return True

    # Check for capturing groups, named groups, and non-capturing groups
    if re.search(
        r"\([^?]", string
    ):  # Basic capturing groups (but not special groups starting with '(?')
        return True

    # Check for named capturing groups and their references
    if (
        re.search(r"\(\?P<[^>]+>[^)]+\)", string) or "(?P=" in string
    ):  # (?P<name>...) or (?P=name)
        return True

    # Check for non-capturing groups
    if "(?:" in string:  # (?:...)
        return True

    # Check for comment groups
    if "(?#" in string:  # (?#comment)
        return True

    # Check for mode-modifying groups
    if re.search(r"\(\?[iLmsux]+[:-]", string):  # (?i), (?im), (?i:...), etc.
        return True

    # Check for backreferences
    if re.search(r"\\[1-9][0-9]?", string):  # \1 through \99
        return True
    return False


class Ignorable:
    """
    `Ignorable` is constructed from either `str`, `re.Pattern` or `pathlib.Path`,
    and provides a common interface to interact with them.
    Used internally by `TmrIgnore`.
    """

    _val: Union[re.Pattern, str]

    def __new__(cls, ignorable: IgnorableType) -> ForwardRef("Ignorable"):
        """
        Normalizes the values the are passed to constructor to either str or re.Pattern.
        In case an `Ignorable` is passed to constructor, it itself is returned (avoiding recursion).
        """
        if isinstance(ignorable, Ignorable):
            return ignorable
        self = super().__new__(cls)
        if isinstance(ignorable, Path):
            self._init_(str(ignorable))
        elif isinstance(ignorable, re.Pattern) or not is_regexlike(ignorable):
            self._init_(ignorable)
        else:
            compiled_pattern = re.compile(ignorable)
            logger.info(f"Compiled regex {ignorable} -> {compiled_pattern}")
            self._init_(compiled_pattern)
        return self

    def __eq__(self, other) -> bool:
        if hasattr(other, "_val"):
            return self._val == other._val
        return self._val == other

    def __hash__(self) -> int:
        return hash(self._val)

    def __str__(self) -> str:
        return str(self._val)

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({self._val})"

    def _init_(self, value: Union[re.Pattern, str]) -> None:
        if isinstance(value, str):
            # todo: this is awkward, it's because __new__ is ok with accepting a re.Pattern. Should be normalized to one type by now.
            value.removesuffix("/")
        self._val = value

    def exists(self) -> bool:
        if isinstance(self._val, re.Pattern):
            logger.warning(
                f"{self.__class__.__qualname__}.exists() was called but self._val is a re.Pattern. not implemented."
            )
            return False
        else:
            return Path(self._val).exists()

    def matches(self, other: IgnorableType) -> bool:
        # TODO: bug: only full gist ids
        """self._val is a line in .tmrignore, 'other' is a path or gist id/description."""
        if isinstance(self._val, re.Pattern):
            return self._val.search(str(other)) is not None

        if str(self._val) in str(other).split():
            return True

        _valpath = Path(self._val)
        if _valpath.is_absolute():
            # self._val is an absolute path: '/home/gilad', so
            # 'other' is ignored if it's equal or longer than self._val, e.g other='/home/gilad/dev'
            return str(other).startswith(self._val)

        if len(_valpath.parts) > 1:
            # self._val is a few parts, but not an absolute path: 'gilad/dev', so
            # 'other' is ignored it if contains self._val (e.g. other='/home/gilad/dev')
            return self._val in str(other)

        # self._val is just a name: 'dev';
        # 'other' is ignored if any part of it equals self._val (e.g. other='gilad/dev/too-many-repos')
        for otherpart in Path(other).parts:
            if otherpart == self._val:
                return True
        return False


class TmrIgnore(Set[Ignorable], Singleton):
    def __init__(self) -> None:
        # for element in iterable:
        # 	self.add(element)
        super().__init__()
        self.exclusions = set()
        self.update_from_file(Path.home() / ".tmrignore")
        self.__cache__ = dict(items_stringed=[])

    def _items_stringed(self, *, refresh=False) -> List[str]:
        if not refresh:
            if self.__cache__.get("items_stringed"):
                return self.__cache__.get("items_stringed")

        items_stringed = []
        for ignored in sorted(self, key=lambda x: str(x)):
            s = str(ignored)
            if isinstance(ignored._val, re.Pattern):
                items_stringed.append(s)
            else:
                items_stringed.append(repr(s))

        self.__cache__["items_stringed"] = items_stringed
        return items_stringed

    def __repr__(self) -> str:
        items = ", \n    ".join(self._items_stringed())
        return f"{self.__class__.__qualname__}({{{items}\n}})"

    def table(self) -> Table:
        table = Table(show_header=False, highlight=True, title="Excluding:")
        items_stringed = self._items_stringed()
        for i in range(len(items_stringed) // 4 + 1):
            i *= 4
            row = items_stringed[i : i + 4]
            table.add_row(*row)
        return table

    def is_ignored(self, element: IgnorableType) -> bool:
        for exclusion in self.exclusions:
            # todo(bug): if both /my/path and !/my/path/subdir are in .tmrignore, the subdir WILL be ignored.
            if exclusion.matches(element):
                return False
        for ignorable in self:
            if ignorable.matches(element):
                return True
        return False

    def add(self, element: IgnorableType) -> None:
        if not element:
            return
        with suppress(AttributeError, TypeError):
            element = element.strip()
            if not element:
                return
            if element.startswith("#"):
                return
            if "#" in element:
                element = element.split("#", 1)[0].strip()
        if element.startswith("!"):
            self.exclusions.add(Ignorable(element[1:]))
            return
        ignorable = Ignorable(element)
        super().add(ignorable)

    def update(self, *s: Iterable[IgnorableType]) -> None:
        for element in s:
            self.add(element)

    def update_from_file(self, ignorefile: Path):
        def exception_format(_e: Exception) -> str:
            return f"TmrIgnore.update_from_file({ignorefile}) | {_e.__class__.__qualname__} : {_e}"

        entries = set()
        try:
            entries |= set(map(str.strip, ignorefile.open().readlines()))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(exception_format(e))
        else:
            logger.good(f"Loaded ignore file successfully: {ignorefile}")

        for exclude in entries:
            self.add(exclude)


if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
    tmrignore = None
else:
    tmrignore = TmrIgnore()
