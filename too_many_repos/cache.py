import pickle
from typing import List, Optional, Any

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from too_many_repos.tmrconfig import config


def safe_load_pickle(file_name: str) -> Optional[Any]:
	"""Loads config.cache.path / {file_name}.pickle, or None if doesn't exist"""
	try:
		with (config.cache.path / f'{file_name}.pickle').open(mode='r+b') as cached:
			return pickle.load(cached)
	except FileNotFoundError:
		return None


class Cache(Singleton):
	"""Does safe pickling.
	Does not care about configured cache_mode."""

	@property
	def gist_list(self) -> Optional[List[str]]:
		gist_list = safe_load_pickle('gist_list')
		logger.debug(f'Cache | gists list → {"None" if gist_list is None else "OK"}')
		return gist_list

	@gist_list.setter
	def gist_list(self, gist_list: List[str]):
		logger.debug(f'Cache | writing gists list to file')
		with (config.cache.path / 'gist_list.pickle').open(mode='w+b') as gist_list_cache:
			pickle.dump(gist_list, gist_list_cache)

	@staticmethod
	def get_gist_filenames(gist_id: str) -> Optional[List[str]]:
		gist_filenames = safe_load_pickle(f'gist_{gist_id}_filenames')
		logger.debug(f'Cache | filenames of {gist_id[:8]} → {"None" if gist_filenames is None else "OK"}')
		return gist_filenames

	@staticmethod
	def set_gist_filenames(gist_id: str, gist_filenames: List[str]):
		logger.debug(f'Cache | writing filenames of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_filenames.pickle').open(mode='w+b') as gist_filenames_cache:
			pickle.dump(gist_filenames, gist_filenames_cache)

	@staticmethod
	def get_gist_file_content(gist_id: str, file_name: str) -> Optional[str]:
		gist_file_content = safe_load_pickle(f'gist_{gist_id}_{file_name}')
		logger.debug(f'Cache | file contents of [b]{file_name}[/b] of {gist_id[:8]} → {"None" if gist_file_content is None else "OK"}')
		return gist_file_content

	@staticmethod
	def set_gist_file_content(gist_id: str, file_name: str, gist_file_content: List[str]):
		logger.debug(f'Cache | writing file contents of [b]{file_name}[/b] of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_{file_name}.pickle').open(mode='w+b') as gist_file_content_cache:
			pickle.dump(gist_file_content, gist_file_content_cache)


cache = Cache()
