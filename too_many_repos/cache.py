import pickle
from typing import List, Optional, Any

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from too_many_repos.tmrconfig import config


def safe_load(file_name: str) -> Optional[Any]:
	# TODO: in config.cache.path/bin
	try:
		with (config.cache.path / f'{file_name}.pickle').open(mode='r+b') as cached:
			return pickle.load(cached)
	except FileNotFoundError as e:
		return None


class Cache(Singleton):
	"""Does safe pickling.
	Does not care about configured cache_mode."""

	@property
	def gists_list(self) -> Optional[List[str]]:
		gists_list = safe_load('gists_list')
		logger.debug(f'Cache | Loaded gists list → {"None" if gists_list is None else "OK"}')
		return gists_list

	@gists_list.setter
	def gists_list(self, gists_list: List[str]):
		logger.debug(f'Cache | Dumping gists list to file')
		with (config.cache.path / 'gists_list.pickle').open(mode='w+b') as gists_list_cache:
			pickle.dump(gists_list, gists_list_cache)

	@staticmethod
	def load_gist_filenames(gist_id: str) -> Optional[List[str]]:
		gist_filenames = safe_load(f'gist_{gist_id}_filenames')
		logger.debug(f'Cache | Loaded filenames of {gist_id[:8]} → {"None" if gist_filenames is None else "OK"}')
		return gist_filenames

	@staticmethod
	def dump_gist_filenames(gist_id: str, gist_filenames: List[str]):
		logger.debug(f'Cache | Dumping filenames of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_filenames.pickle').open(mode='w+b') as gist_filenames_cache:
			pickle.dump(gist_filenames, gist_filenames_cache)

	@staticmethod
	def load_gist_file_content(gist_id: str, file_name: str) -> Optional[str]:
		gist_file_content = safe_load(f'gist_{gist_id}_{file_name}')
		logger.debug(f'Cache | Loaded file contents of [b]{file_name}[/b] of {gist_id[:8]} → {"None" if gist_file_content is None else "OK"}')
		return gist_file_content

	@staticmethod
	def dump_gist_file_content(gist_id: str, file_name: str, gist_file_content: List[str]):
		logger.debug(f'Cache | Dumping file contents of [b]{file_name}[/b] of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_{file_name}.pickle').open(mode='w+b') as gist_file_content_cache:
			pickle.dump(gist_file_content, gist_file_content_cache)


cache = Cache()
