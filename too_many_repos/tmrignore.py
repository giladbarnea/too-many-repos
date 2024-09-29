import re
import sys
from pathlib import Path
from typing import Iterable, Set, Union, ForwardRef, List
from contextlib import suppress

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from rich.table import Table

IgnorableType = Union[str, re.Pattern, Path, ForwardRef("Ignorable")]


def is_regexlike(val: str) -> bool:
	"""Chars that can't be a file path and used often in regexps"""
	# space because easy to match gist description without \s
	for re_char in ('*', '^', '$', '[', ']', '?', '+', '<', '>', '(', ')', '{', '}', '\\', ' '):
		if re_char in val:
			return True
	return False


class Ignorable:
	"""
	`Ignorable` is constructed from either `str`, `re.Pattern` or `pathlib.Path`,
	and provides a common interface to interact with them.
	Used internally by `TmrIgnore`.
	"""
	_val: Union[re.Pattern, str]

	def __new__(cls, value: IgnorableType) -> ForwardRef("Ignorable"):
		"""
		Normalizes the values the are passed to constructor to either str or re.Pattern.
		In case an `Ignorable` is passed to constructor, it itself is returned (avoiding recursion).
		"""
		if isinstance(value, Ignorable):
			return value
		self = super().__new__(cls)
		if isinstance(value, Path):
			self._init_(str(value))
		elif isinstance(value, re.Pattern) or not is_regexlike(value):
			self._init_(value)
		else:
			self._init_(re.compile(value))
		# if is_regexlike(value):
		# else:
		# 	self._init_(value)
		return self

	def __eq__(self, other) -> bool:
		if hasattr(other, '_val'):
			return self._val == other._val
		return self._val == other

	def __hash__(self) -> int:
		return hash(self._val)

	def __str__(self) -> str:
		return str(self._val)

	def __repr__(self) -> str:
		return f'{self.__class__.__qualname__}({self._val})'

	def _init_(self, value: Union[re.Pattern, str]) -> None:
		if isinstance(value, str):
			# todo: this is awkward, it's because __new__ is ok with accepting a re.Pattern.
			#  does it ever get called with re.Pattern anyway?
			value.removesuffix('/')
		self._val = value

	def exists(self) -> bool:
		if isinstance(self._val, re.Pattern):
			logger.warning(f"{self.__class__.__qualname__}.exists() was called but self._val is a re.Pattern. not implemented.")
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
		self.update_from_file(Path.home() / '.tmrignore')
		self.__cache__ = dict(items_stringed = [])

	def _items_stringed(self, *, refresh=False) -> List[str]:
		if not refresh:
			if self.__cache__.get('items_stringed'):
				return self.__cache__.get('items_stringed')

		items_stringed = []
		for ignored in sorted(self, key=lambda x: str(x)):
			s = str(ignored)
			if isinstance(ignored._val, re.Pattern):
				items_stringed.append(s)
			else:
				items_stringed.append(repr(s))

		self.__cache__['items_stringed'] = items_stringed
		return items_stringed

	def __repr__(self) -> str:
		items = ", \n    ".join(self._items_stringed())
		return f'{self.__class__.__qualname__}({{{items}\n}})'

	def table(self) -> Table:
		table = Table(show_header=False, highlight=True, title='Excluding:')
		items_stringed = self._items_stringed()
		for i in range(len(items_stringed) // 4 + 1):
			i *= 4
			row = items_stringed[i:i + 4]
			table.add_row(*row)
		return table

	def is_ignored(self, element: IgnorableType) -> bool:
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
			if element.startswith('#'):
				return
			if '#' in element:
				element = element.split('#', 1)[0].strip()
		ignorable = Ignorable(element)
		# ignorable_was_in_self = ignorable in self
		super().add(ignorable)
		# if ignorable_was_in_self:
		# 	breakpoint()
		# if config.verbose >= 2 and not ignorable.exists():
		# 	logger.warning(f"Does not exist: {ignorable}")

	def update(self, *s: Iterable[IgnorableType]) -> None:
		for element in s:
			self.add(element)

	def update_from_file(self, ignorefile: Path):
		def exception_format(_e: Exception) -> str:
			return f"TmrIgnore.update_from_file({ignorefile}) | {_e.__class__.__qualname__} : {_e}"

		entries = set()
		try:
			entries |= set(map(str.strip, ignorefile.open().readlines()))
		except FileNotFoundError as fnfe:
			pass
		except Exception as e:
			logger.warning(exception_format(e))
		else:
			logger.good(f"Loaded ignore file successfully: {ignorefile}")

		for exclude in entries:
			self.add(exclude)


if any(arg in ('-h','--help') for arg in sys.argv[1:]):
	tmrignore = None
else:
	tmrignore = TmrIgnore()
