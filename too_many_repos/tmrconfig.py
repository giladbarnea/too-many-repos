from typing import Optional, Literal, Iterable, TypeVar, NoReturn

from too_many_repos.singleton import Singleton
from too_many_repos.log import logger
from pathlib import Path
import sys
from click import BadOptionUsage

CacheMode = Optional[Literal['r', 'w']]
_O = TypeVar('_O')


def popopt(opt: str, type_: _O, also_short=False) -> _O:
	"""

	:param opt: e.g '--verbose'
	:param type_: e.g. `bool` or `Literal['r', 'r+w']`
	:param also_short: look for e.g. '-v'
	:return:
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
				specified_opt, _, val = arg.partition('=')[2]
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
	if val is not None and val and not isinstance(val, type_):
		BadOptionUsage(opt, (f"{specified_opt} opt was specified with invalid value: {repr(val)}. "
								 f"accepted values: {type_}"))
	return val


class TmrConfig(Singleton):
	verbose: int
	cache_mode: CacheMode
	cache_path: Path

	def __init__(self):
		super().__init__()
		self.verbose = 0
		self.cache_mode: CacheMode = None
		self.cache_path: Path = None
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
		mode = popopt('--cache', CacheMode)
		if mode is not None:
			if self.cache_mode:
				logger.warning((f"cache mode was specified both in config and cmd args, and will be overridden "
								f"by the value passed via cmdline: {mode}"))
			self.cache_mode = mode


config = TmrConfig()
