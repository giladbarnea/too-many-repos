import sys
from pathlib import Path
from typing import Optional, Literal, TypeVar, NoReturn, get_origin, get_args, Union, Type

from click import BadOptionUsage

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton

CacheMode = Optional[Literal['r', 'w']]
_O = TypeVar('_O')

from rich.traceback import install

install(extra_lines=5, show_locals=True)
NoneType = type(None)
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
	if isinstance(type_, type):
		# type_ is e.g. bool, NoneType
		if type_ is bool:
			if (val := val.lower()) in ('true', '1'):
				return True
			if val in ('false', '0'):
				return False
			raise ValueError(f"cast_type({val = }, {type_ = }) _type is bool, so val must be in ('true', 'false', '1', '0')")

		if type_ is str:
			return val

		if type_ is int or type_ is float:
			return type_(val)

		# if issubclass(type_, Iterable):
		# 	# list, tuple, dict, ...
		# 	val.split(',')
		breakpoint()
		raise NotImplementedError(f"is_valid({val = }, {type_ = })")
	if not hasattr(type_, '__args__'):
		# type_ is a primitive (e.g None, 'r', 5)
		if type_ is None:
			if val is not None:
				# This is probably redundant because is_valid check is made before calling this function
				raise ValueError(f"cast_type({val = }, {type_ = }) _type is None, so val must None")
			return None

		return type(type_)(val)

	# type_ is a typing.<Foo>
	if get_origin(type_) is Union:
		# e.g. Optional[Literal['r', 'w'], None]
		type_args = get_args(type_)
		if val is None and any(type_arg is type(None) for type_arg in type_args):
			# Already cast to None
			return None
	breakpoint()


def popopt(opt: str, type_: _O, also_short=False) -> _O:
	"""
	Tries to pop opt from sys.argv, validate its value and cast it by type_.

	:param opt: e.g '--verbose'
	:param type_: e.g. bool, Literal['r', 'w'], Optional[Literal[...]]
	:param also_short: look for e.g. '-v'
	:raises BadOptionUsage if is_valid returns False
	:return: The type-casted value.
	"""

	val = None
	if not opt.startswith('--'):
		raise ValueError(f"popopt({opt = }, ...) `opt` must start with '--'")

	shopt = opt[1:3] if also_short else None
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


class TmrConfig(Singleton):
	verbose: int
	cache_mode: CacheMode
	cache_path: Path
	max_threads: Optional[int]
	max_depth: int
	gitdir_size_limit_mb: int

	def __init__(self):
		super().__init__()
		self.verbose = 0
		self.cache_mode: CacheMode = None
		self.cache_path: Path = None
		self.max_threads: Optional[int] = None
		self.max_depth: Optional[int] = None
		self.gitdir_size_limit_mb: int = 100
		config_file = Path.home() / '.tmrrc.py'
		try:
			exec(compile(config_file.open().read(), config_file, 'exec'), dict(tmr=self))
		except FileNotFoundError as e:
			logger.warning(f"conifg: Did not find {Path.home() / '.tmrrc.py'}")
		else:
			logger.debug(f"[good]Loaded config file successfully: {config_file}[/]")

		# ** At this point, self.* attrs may have loaded values from file
		# * cache_path
		if self.cache_path is not None:
			self.cache_path = Path(self.cache_path)
			if not self.cache_path.is_dir():
				raise NotADirectoryError(f"config: specified cache_path = {self.cache_path} is not a directory")
		else:
			self.cache_path = Path.home() / '.cache/too-many-repos'
			if not self.cache_path.is_dir():
				self.cache_path.mkdir(parents=True)

		# * verbose
		verbose_from_sys_argv = TmrConfig._get_verbose_level_from_sys_argv()
		if verbose_from_sys_argv is not None:
			if self.verbose:
				logger.warning((f"verbose level was specified both in config and cmd args, and will be overridden "
								f"by the value passed via cmdline: {verbose_from_sys_argv}"))
			self.verbose = verbose_from_sys_argv

		# * cache_mode
		self._try_set_cache_mode_from_sys_args()

		# * max_threads
		self._try_set_max_threads_from_sys_args()

		# * max_depth
		self._try_set_max_depth_from_sys_args()

	def __str__(self):
		rv = f"TmrConfig()"
		for key, val in self.__dict__.items():
			rv += f'\n\tself.{key}: {val}'
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

	def _try_set_cache_mode_from_sys_args(self) -> NoReturn:
		mode = popopt('--cache-mode', CacheMode)
		if mode is not None:
			if self.cache_mode:
				logger.warning((f"cache mode was specified both in config and cmd args, and will be overridden "
								f"by the value passed via cmdline: {mode}"))
			self.cache_mode = mode

	def _try_set_max_threads_from_sys_args(self) -> NoReturn:
		max_threads = popopt('--max-threads', Optional[int])
		if max_threads is not None:
			if self.max_threads:
				logger.warning((f"max_threads was specified both in config and cmd args, and will be overridden "
								f"by the value passed via cmdline: {max_threads}"))
			self.max_threads = max_threads

	def _try_set_max_depth_from_sys_args(self) -> NoReturn:
		max_depth = popopt('--max-depth', Optional[int])
		if max_depth is not None:
			if self.max_depth:
				logger.warning((f"max_depth was specified both in config and cmd args, and will be overridden "
								f"by the value passed via cmdline: {max_depth}"))
			self.max_depth = max_depth


config = TmrConfig()
