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
	__cache__ = dict()
	@property
	def gist_list(self) -> Optional[List[str]]:
		if gist_list := self.__cache__.get('gist_list'):
			return gist_list
		gist_list = safe_load_pickle('gist_list')
		logger.debug(f'Cache | gists list → {"None" if gist_list is None else "OK"}')
		self.__cache__['gist_list'] = gist_list
		return gist_list

	@gist_list.setter
	def gist_list(self, gist_list: List[str]):
		logger.debug(f'Cache | WRITING gists list to file')
		with (config.cache.path / 'gist_list.pickle').open(mode='w+b') as gist_list_cache:
			pickle.dump(gist_list, gist_list_cache)

	@classmethod
	def get_gist_filenames(cls, gist_id: str) -> Optional[List[str]]:
		if gist_filenames := cls.__cache__.get(f'gist_{gist_id}_filenames'):
			return gist_filenames
		gist_filenames = safe_load_pickle(f'gist_{gist_id}_filenames')
		logger.debug(f'Cache | Loaded cached filenames of {gist_id[:8]} → {"None" if gist_filenames is None else "OK"}')
		cls.__cache__[f'gist_{gist_id}_filenames'] = gist_filenames
		return gist_filenames

	@classmethod
	def set_gist_filenames(cls, gist_id: str, gist_filenames: List[str]):
		logger.debug(f'Cache | WRITING filenames of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_filenames.pickle').open(mode='w+b') as gist_filenames_cache:
			pickle.dump(gist_filenames, gist_filenames_cache)

	@classmethod
	def get_gist_file_content(cls, gist_id: str, file_name: str) -> Optional[str]:
		if gist_file_content := cls.__cache__.get(f'gist_{gist_id}_{file_name}'):
			return gist_file_content
		gist_file_content = safe_load_pickle(f'gist_{gist_id}_{file_name}')
		logger.debug(f'Cache | Loaded cached file contents of [b]{file_name}[/b] of {gist_id[:8]} → {"None" if gist_file_content is None else "OK"}')
		cls.__cache__[f'gist_{gist_id}_{file_name}'] = gist_file_content
		return gist_file_content

	@classmethod
	def set_gist_file_content(cls, gist_id: str, file_name: str, gist_file_content: List[str]):
		logger.debug(f'Cache | WRITING file contents of [b]{file_name}[/b] of {gist_id[:8]} to file')
		with (config.cache.path / f'gist_{gist_id}_{file_name}.pickle').open(mode='w+b') as gist_file_content_cache:
			pickle.dump(gist_file_content, gist_file_content_cache)


cache = Cache()
