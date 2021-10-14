import pickle
from typing import List, Optional

from too_many_repos.log import logger
from too_many_repos.singleton import Singleton
from too_many_repos.tmrconfig import config




class Cache(Singleton):
	"""Does safe pickling.
	Does not handle configured cache_mode."""
	
	@classmethod
	def safe_load(cls, path: str):
		try:
			with (config.cache.path / f'{path}.pickle').open(mode='r+b') as cached:
				return pickle.load(cached)
		except FileNotFoundError as e:
			return None
	
	@classmethod
	def safe_dump(cls, path: str, data):
		dump_path = (config.cache.path / f'{path}.pickle')
		if not dump_path.exists():
			dump_path.mkdir(parents=True)
		
		with dump_path.open(mode='w+b') as file:
			return pickle.dump(data, file)

	@property
	def gist_list(self) -> Optional[List[str]]:
		gist_list = self.safe_load('gists/gists')
		logger.debug(f'Cache | gists list → {"None" if gist_list is None else "OK"}')
		return gist_list

	@gist_list.setter
	def gist_list(self, gist_list: List[str]):
		logger.debug(f'Cache | writing gists list to file')
		self.safe_dump('gists/gists', gist_list)
		# with (config.cache.path / 'gists/gists.pickle').open(mode='w+b') as gist_list_cache:
		# 	pickle.dump(gist_list, gist_list_cache)

	@classmethod
	def get_gist_filenames(cls, gist_id: str) -> Optional[List[str]]:
		gist_filenames = cls.safe_load(f'gists/{gist_id}/filenames')
		logger.debug(f'Cache | filenames of {gist_id[:8]} → {"None" if gist_filenames is None else "OK"}')
		return gist_filenames

	@classmethod
	def set_gist_filenames(cls, gist_id: str, gist_filenames: List[str]):
		logger.debug(f'Cache | writing filenames of {gist_id[:8]} to file')
		cls.safe_dump(f'gists/{gist_id}/filenames', gist_filenames)
		# with (config.cache.path / f'gists/{gist_id}/filenames.pickle').open(mode='w+b') as gist_filenames_cache:
		# 	pickle.dump(gist_filenames, gist_filenames_cache)

	@classmethod
	def get_gist_file_content(cls, gist_id: str, file_name: str) -> Optional[str]:
		gist_file_content = cls.safe_load(f'gists/{gist_id}/{file_name}')
		logger.debug(f'Cache | file contents of [b]{file_name}[/b] of {gist_id[:8]} → {"None" if gist_file_content is None else "OK"}')
		return gist_file_content

	@classmethod
	def set_gist_file_content(cls, gist_id: str, file_name: str, gist_file_content: List[str]):
		logger.debug(f'Cache | writing file contents of [b]{file_name}[/b] of {gist_id[:8]} to file')
		cls.safe_dump(f'gists/{gist_id}/{file_name}', gist_file_content)
		# with (config.cache.path / f'gists/{gist_id}/{file_name}.pickle').open(mode='w+b') as gist_file_content_cache:
		# 	pickle.dump(gist_file_content, gist_file_content_cache)


cache = Cache()
