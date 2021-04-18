from typing import List, Optional

from too_many_repos.singleton import Singleton
from too_many_repos.tmrconfig import config
import pickle
def safe_load(file_name:str):
	try:
		with (config.cache_path / f'{file_name}.pickle').open(mode='r+b') as cached:
			return pickle.load(cached)
	except FileNotFoundError as e:
		return None

class Cache(Singleton):
	"""Does safe pickling.
	Does not care about configured cache_mode."""
	@property
	def gh_gist_list(self) -> Optional[List[str]]:
		gh_gist_list = safe_load('gh_gist_list')
		return gh_gist_list

	@gh_gist_list.setter
	def gh_gist_list(self, gh_gist_list: List[str]):
		with (config.cache_path / 'gh_gist_list.pickle').open(mode='w+b') as gh_gist_list_cache:
			pickle.dump(gh_gist_list, gh_gist_list_cache)


	@staticmethod
	def get_gist_filenames(gist_id: str)->Optional[List[str]]:
		gist_filenames = safe_load(f'gh_gist_{gist_id}_files')
		return gist_filenames

	@staticmethod
	def set_gist_filenames(gist_id: str, gist_filenames: List[str]):
		with (config.cache_path / f'gh_gist_{gist_id}_files.pickle').open(mode='w+b') as gist_filenames_cache:
			pickle.dump(gist_filenames, gist_filenames_cache)

	@staticmethod
	def get_gist_file_content(gist_id: str, file_name: str) -> Optional[str]:
		gist_file_content = safe_load(f'gh_gist_{gist_id}_{file_name}')
		return gist_file_content

	@staticmethod
	def set_gist_file_content(gist_id: str, file_name:str, gist_file_content: List[str]):
		with (config.cache_path / f'gh_gist_{gist_id}_{file_name}.pickle').open(mode='w+b') as gist_file_content_cache:
			pickle.dump(gist_file_content, gist_file_content_cache)

cache = Cache()