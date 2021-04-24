from typing import Iterable, TypeVar, Set, Union, Type, ForwardRef, Any
import re
from pathlib import Path
from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from too_many_repos.tmrconfig import config

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
		# print(f"__new__({value = })")
		if isinstance(value, Ignorable):
			return value
		self = super().__new__(cls)
		if isinstance(value, Path):
			self._init_(str(value))
		if is_regexlike(value):
			self._init_(re.compile(value))
		else:
			self._init_(value)
		return self

	def __str__(self) -> str:
		return str(self._val)

	def __repr__(self) -> str:
		return f'{self.__class__.__qualname__}({self._val})'

	def _init_(self, value: Union[re.Pattern, str]) -> None:
		# print(f'_init_({value = })')
		self._val = value

	def exists(self) -> bool:
		if isinstance(self._val, re.Pattern):
			logger.warning(f"{repr(self)}.exists() was called but self._val is a re.Pattern. not implemented.")
		else:
			return Path(self._val).exists()

	def matches(self, other: IgnorableType) -> bool:
		# TODO: bug: only full gist ids are matched here
		if isinstance(self._val, re.Pattern):
			return self._val.search(str(other)) is not None
		_valpath = Path(self._val)
		if _valpath.is_absolute():
			# `self._val` is an absolute path: '/home/gilad';
			# `other` has to be >= `self._val`, e.g '/home/gilad[/Code]'
			return str(other).startswith(self._val)
		if len(_valpath.parts) > 1:
			# `self._val` is a few parts, but not an absolute path: 'gilad/dev';
			# `other` has to contain it (e.g. '/home/gilad/dev[/...]')
			return self._val in str(other)

		# `self._val` is just a name: 'dev';
		# any part of `other` has to equal (e.g. 'gilad/dev/too-many-repos')
		for otherpart in Path(other).parts:
			if otherpart == self._val:
				return True
		return False


class TmrIgnore(Set[Ignorable], Singleton):

	def __init__(self, iterable: Iterable[IgnorableType] = ()) -> None:
		for element in iterable:
			self.add(element)
		self.update_from_file(Path.home() / '.tmrignore')

	def __repr__(self) -> str:
		items_str = []
		for ignored in sorted(self, key=lambda x:str(x)):
			s = str(ignored)
			if isinstance(ignored._val, re.Pattern):
				items_str.append(s)
			else:
				items_str.append(repr(s))
		items = ", \n\t".join(items_str)
		return f'{self.__class__.__qualname__}({{{items}\n}})'

	def is_ignored(self, element: IgnorableType):
		for ignorable in self:
			if ignorable.matches(element):
				return True
		return False

	def add(self, element: IgnorableType) -> None:
		ignorable = Ignorable(element)
		if not ignorable:
			# Shouldn't happen
			breakpoint()
		super().add(ignorable)
		if config.verbose >= 2 and not ignorable.exists():
			logger.warning(f"Does not exist: {ignorable}")

	def update(self, *s: Iterable[IgnorableType]) -> None:
		for element in s:
			self.add(element)

	def update_from_file(self, ignorefile: Path):
		entries = set()
		try:
			entries |= set(map(str.strip, ignorefile.open().readlines()))
		except FileNotFoundError as fnfe:
			if config.verbose >= 2:
				logger.warning(f"FileNotFoundError when handling {ignorefile}: {', '.join((map(str, fnfe.args)))}")
		except Exception as e:
			logger.warning(f"{e.__class__.__qualname__} when handling {ignorefile}: {', '.join((map(str, e.args)))}")
		else:
			logger.info(f"[good]Loaded ignore file successfully: {ignorefile}[/]")

		for exclude in entries:
			self.add(exclude)


tmrignore = TmrIgnore()
