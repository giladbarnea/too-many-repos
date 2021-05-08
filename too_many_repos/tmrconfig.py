import sys
from pathlib import Path
from typing import Optional, Literal, TypeVar, NoReturn, get_origin, get_args, Union, Type

from click import BadOptionUsage

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from too_many_repos.util import exec_file

CacheMode = Optional[Literal['r', 'w', 'r+w', 'w+r']]
_O = TypeVar('_O')

from rich.traceback import install

install(extra_lines=5, show_locals=True)
NoneType = type(None)
UNSET = object()
TYPE_VALUES = {
	bool:     ('true', 'false', 'yes', 'no'),
	NoneType: ('none', None)
	}


def isnum(s: str) -> bool:
	try:
		float(s)
		return True
	except ValueError:
		return False


def is_valid(val: Optional[str], type_: Union[Type[None], str, bool, float, int, None]) -> bool:
	"""
	val can be either a string representation of type_, or None.

	type_ can be:

	- type (e.g. bool)
	- type of type (e.g. NoneType)
	- value / instance (e.g. None, True, "5")
	- typing (e.g. Union[...], Literal[...], runs recursively on what they're made of)

	"""
	if isinstance(type_, type):
		# * type_ is not value / instance (e.g. bool, NoneType)

		if type_ is NoneType:
			# is_valid("None", NoneType) → True
			return val is None or val.lower() == 'none'

		if val is None or val.lower() == 'none':
			return type_ is NoneType

		# At this point, val is a str
		val = val.lower()
		if type_ is bool:
			return val in TYPE_VALUES[bool]

		if type_ in (int, float):
			try:
				# e.g int(2)
				type_(val)
				return True
			except (ValueError, TypeError):
				# ValueError when int("5.5")
				return False

		if not type_ is str:
			# collections (tuple etc)
			raise NotImplementedError(f"is_valid(val = {repr(val)}, type = {repr(type_)})")

		return not isnum(val) and not any(val in othervalues for othervalues in TYPE_VALUES.values())

	if not hasattr(type_, '__args__'):
		# * type_ is a value / instance (e.g None, 'r', 5)
		if type_ is None:
			# is_valid("None", None) → True
			return val is None or val.lower() == 'none'

		if val is None or val.lower() == 'none':
			return type_ is None

		# At this point, val is a str
		val = val.lower()

		if type_ is True:
			return val in ('true', 'yes')
		elif type_ is False:
			return val in ('false', 'no')

		# e.g. '5' == str(5)
		return val == str(type_)

	# * type_ is a typing.<Foo>
	for arg in get_args(type_):
		if is_valid(val, arg):
			return True
	return False


def cast_type(val: Optional[str], type_: _O) -> _O:
	"""Assumes val is valid"""
	if hasattr(type_, '__args__'):
		# * type_ is a typing.<Foo>
		type_origin = get_origin(type_)
		type_args = set(get_args(type_))
		if type_origin is Union:
			if NoneType in type_args:
				if val in (None, 'NONE', 'None', 'none'):
					return None

			type_args -= {NoneType}

		if len(type_args) == 1:
			# Was Optional[Literal['r', 'w']], now it's Literal['r', 'w']
			return cast_type(val, next(iter(type_args)))
		if val in type_args:
			return val
		raise NotImplementedError(f'{val = } not in {type_args = }')

	if type_ in (NoneType, None):
		return None
	if type_ in (bool, True, False, Literal[True], Literal[False]):
		if type_ in (True, Literal[True]):
			return True
		elif type_ in (False, Literal[False]):
			return False
		return True if val in ('true', 'True', 'TRUE', 'yes', 'Yes', 'YES') else False

	if type_ in (int, float, str):
		return type_(val)
	return type(type_)(val)


def popopt(opt: str, type_: _O, *, check_short=False) -> _O:
	"""
	Tries to pop opt from sys.argv, validate its value and cast it by type_.

	:param opt: e.g '--verbose'
	:param type_: e.g. bool, Literal['r', 'w'], Optional[Literal[...]]
	:param check_short: look for e.g. '-v'
	:return: The type-casted value.

	:raises BadOptionUsage if is_valid returns False
	"""

	val = None
	if not opt.startswith('--'):
		raise ValueError(f"popopt({opt = }, ...) `opt` must start with '--'")

	shopt = opt[1:3] if check_short else None
	specified_opt = None  # For exceptions

	def found_it(_arg: str) -> bool:
		if shopt is not None:
			return _arg.startswith(opt) or _arg.startswith(shopt)
		else:
			return _arg.startswith(opt)

	for i, arg in enumerate(sys.argv):
		# Handle 2 situations:
		# 1) --opt=foo
		# 2) --opt foo
		if found_it(arg):
			if '=' in arg:
				# e.g. --opt=foo
				specified_opt, _, val = arg.partition('=')
				sys.argv.pop(i)
				break

			# e.g. --opt foo, -o foo
			specified_opt = arg
			sys.argv.pop(i)
			try:
				val = sys.argv[i]
				sys.argv.pop(i)
			except IndexError:
				# e.g. --opt (no value)
				if isinstance(type_, bool):
					# --opt is a flag
					val = True
				else:
					raise BadOptionUsage(opt, (f"{specified_opt} opt was specified without value. "
											   f"accepted values: {type_}")) from None

	if not is_valid(val, type_):
		BadOptionUsage(opt, (f"{specified_opt} opt was specified with invalid value: {repr(val)}. "
							 f"accepted values: {type_}"))
	cast = cast_type(val, type_)
	return cast


def annoying_setattr(obj, attr, val):
	self_value = getattr(obj, attr, UNSET)
	if self_value is not UNSET:
		logger.warning((f"[b]{attr}[/b] was specified both in config and cmd args."
						f" config val ({repr(self_value)}) will be overwritten "
						f"by the value passed via cmdline: {repr(val)}"))
	setattr(obj, attr, val)


class CacheConfig:
	"""
	Mode dictates what to do with individual settings.
	If unspecified (default), cache is completely disabled.

	If mode is specified ('r' or 'w'), individual settings that were
	unspecified (default) are set to True.
	"""
	gist_list: Optional[bool] = None
	gist_filenames: Optional[bool] = None
	gist_content: Optional[bool] = None
	_mode: CacheMode
	_path: Path

	def __init__(self) -> None:
		self.path = Path.home() / '.cache/too-many-repos'
		_try_set_opt_from_sys_args(self, 'mode', '--cache-mode',
								   type_=CacheMode, default=None)

	def __repr__(self):
		rv = f"CacheConfig(path='{self.path}', mode='{self.mode}', "
		for key, val in self.__dict__.items():
			if key.startswith('_'):
				continue
			rv += f'{key}={repr(val) if isinstance(val, str) else val}, '
		return rv[:-2]+')'

	@property
	def path(self):
		return self._path

	@path.setter
	def path(self, path: Union[str, Path]):
		self._path = Path(path)
		if not self._path.is_dir():
			self._path.mkdir(parents=True)

	@property
	def mode(self):
		return self._mode

	@mode.setter
	def mode(self, mode: CacheMode):
		self._mode = mode
		if self._mode is None:
			self.gist_list = None
			self.gist_filenames = None
			self.gist_content = None
		else:
			if self.gist_list is None:
				self.gist_list = True
			if self.gist_filenames is None:
				self.gist_filenames = True
			if self.gist_content is None:
				self.gist_content = True


class TmrConfig(Singleton):
	verbose: int
	cache: CacheConfig
	max_workers: Optional[int]
	max_depth: int
	gitdir_size_limit_mb: int
	difftool: str

	def __init__(self):
		super().__init__()
		self.verbose: int
		self.cache: CacheConfig = CacheConfig()
		self.max_workers: Optional[int]
		self.max_depth: int
		self.gitdir_size_limit_mb: int = 100
		tmrrc = Path.home() / '.tmrrc.py'
		exec_file(tmrrc, dict(config=self))

		# ** At this point, self.* attrs may have loaded values from file

		self._try_set_verbose_level_from_sys_args(default=0)

		# self._try_set_cache_mode_from_sys_args(default=None)

		self._try_set_max_workers_from_sys_args(default=None)

		self._try_set_max_depth_from_sys_args(default=1)

		_try_set_opt_from_sys_args(self, 'difftool', type_=Optional[str], default='diff')

	def __repr__(self):
		rv = f"TmrConfig()"
		for key, val in self.__dict__.items():
			rv += f'\n\tself.{key}: {repr(val) if isinstance(val, str) else val}'
		return rv

	@staticmethod
	def _get_verbose_level_from_sys_argv() -> Optional[int]:
		for i, arg in enumerate(sys.argv):
			if arg in ('-v', '-vv', '-vvv'):
				level = arg.count('v')
				sys.argv.pop(i)
				return level

			# Handle 3 situations:
			# 1) --verbose=2
			# 2) --verbose 2
			# 3) --verbose
			if arg.startswith('--verbose'):
				if '=' in arg:
					# e.g. --verbose=2
					level = int(arg.partition('=')[2])
					sys.argv.pop(i)
					return level

				sys.argv.pop(i)
				try:
					level = sys.argv[i]
				except IndexError:
					# e.g. --verbose (no value)
					return 1
				else:
					if level.isdigit():
						# e.g. --verbose 2
						level = int(level)

						# pop 2nd time for arg value
						sys.argv.pop(i)
					else:
						# e.g. --verbose --other-arg
						level = 1
				return level
		return None

	def _try_set_verbose_level_from_sys_args(self, default=UNSET) -> NoReturn:
		level = TmrConfig._get_verbose_level_from_sys_argv()
		if level is None and default is not UNSET:
			annoying_setattr(self, 'verbose', default)
		if level is not None:
			annoying_setattr(self, 'verbose', level)

	# def _try_set_cache_mode_from_sys_args(self, default=UNSET) -> NoReturn:
	# 	mode = popopt('--cache-mode', CacheMode)
	# 	if mode is None and default is not UNSET:
	# 		annoying_setattr(self.cache, 'mode', default)
	# 	if mode is not None:
	# 		annoying_setattr(self.cache, 'mode', mode)

	def _try_set_max_workers_from_sys_args(self, default=UNSET) -> NoReturn:
		_try_set_opt_from_sys_args(self, 'max_workers', type_=Optional[int], default=default)
		# max_workers = popopt('--max-workers', Optional[int])
		# if max_workers is None and default is not UNSET:
		# 	annoying_setattr(self, 'max_workers', default)
		#
		# if max_workers is not None:
		# 	annoying_setattr(self, 'max_workers', max_workers)

	def _try_set_max_depth_from_sys_args(self, default=UNSET) -> NoReturn:
		_try_set_opt_from_sys_args(self, 'max_depth', type_=Optional[int], default=default)
		# max_depth = popopt('--max-depth', Optional[int])
		# if max_depth is None and default is not UNSET:
		# 	annoying_setattr(self, 'max_depth', default)
		#
		# if max_depth is not None:
		# 	annoying_setattr(self, 'max_depth', max_depth)


def _try_set_opt_from_sys_args(obj, attr, optname=None, *, type_, default=UNSET) -> NoReturn:
	if not optname:
		optname = f'--{attr.replace("_", "-")}'
	val = popopt(optname, type_)
	if val is None and default is not UNSET:
		annoying_setattr(obj, attr.replace('-', '_'), default)

	if val is not None:
		annoying_setattr(obj, attr.replace('-', '_'), val)


if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
	config = None
else:
	config = TmrConfig()
