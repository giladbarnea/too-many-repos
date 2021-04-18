from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any, Literal, Dict, NoReturn
from collections import defaultdict
from concurrent import futures as fut
from too_many_repos import system
from too_many_repos.cache import cache
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore


class File:
	ignored: bool = False
	content: str = ''
	diff: bool


@dataclass
class Gist:
	id: str
	description: str
	filecount: Any
	permissions: Literal['secret', 'public']
	date: str
	files: Dict[str, File] = field(default_factory=dict)

	def __str__(self):
		return f"{self.id[:16]} '{self.description}' ({self.filecount} files)"

	def short(self) -> str:
		return f"{self.id[:8]} '{self.description[:32]}'"

	def __post_init__(self):
		self.filecount = int(self.filecount.partition(' ')[0])

	def _get_file_names(self) -> List[str]:
		"""Calls `gh gist view "{self.id}" --files` to get this gist's list of file names.
		May use cache."""
		if config.cache_mode == 'r' and (filenames := cache.get_gist_filenames(self.id)) is not None:
			return filenames
		view_process = system.popen(f'gh gist view "{self.id}" --files', verbose=config.verbose)
		filenames = view_process.communicate()[0].decode().splitlines()
		if config.cache_mode == 'w':
			cache.set_gist_filenames(self.id, filenames)
		return filenames

	def _get_file_content(self, file_name) -> str:
		"""Calls `gh gist view '{self.id}' -f '{file_name}'` to get the file's content.
		May use cache."""
		if config.cache_mode == 'r' and (file_content := cache.get_gist_file_content(self.id, file_name)) is not None:
			return file_content
		content = system.run(f"gh gist view '{self.id}' -f '{file_name}'", verbose=config.verbose)
		if config.cache_mode == 'w':
			cache.set_gist_file_content(self.id, file_name, content)
		return content

	def build_files(self) -> NoReturn:
		"""
		Popuplates self.files.

		Calls self._get_file_names(self) which may use cache.

		Called by get_file2gist_map() in a threaded fashion."""
		filenames = self._get_file_names()
		for name in filenames:
			file = File()
			file.ignored = tmrignore.is_ignored(name)
			self.files[name] = file
		logger.debug(f"[#][b]{self.short()}[/b] built {len(self.files)} files[/]")

	def popuplate_files_content(self) -> NoReturn:
		"""
		For each file in self.files, sets its content.

		Calls self._get_file_content(self, file_name) which may use cache.

		Called by get_file2gist_map() in a threaded fashion.
		"""
		for name, file in self.files.items():
			if file.ignored:
				continue
			content = self._get_file_content(name)
			file.content = content
		logger.debug(f"[#][b]{self.short()}[/b] populated files content[/]")

	def diff(self, path: Path) -> bool:
		"""Returns Whether the stripped contents of `path` and this gist's respective file are different.

		Sets `file.diff` attribute."""
		logger.debug(f'[#]diffing {path}...')
		gist_file: File = self.files.get(path.name)
		tmp_gist_path = f'/tmp/{self.id}_{path.name}'
		with open(tmp_gist_path, mode='w') as tmp:
			tmp.write(gist_file.content)

		# Strip the contents of the local file and save it to a tmp file
		tmp_file_path = f'/tmp/{path.name}.gist{path.suffix}'
		with open(tmp_file_path, mode='w') as tmp:
			tmp.write('\n'.join(filter(bool, map(str.strip, path.open().readlines()))))

		diff = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{tmp_gist_path}" "{tmp_file_path}"')
		if not diff:
			logger.info(f"[good][b]Diff {path.absolute()}[/b]: file and [b]{self.short()}[/b] file are identical[/]")
			gist_file.diff = False
			return False

		prompt = f"[warn][b]Diff {path.absolute()}[/b]: file and [b]{self.short()}[/b] are different"
		logger.info(prompt)
		gist_file.diff = True
		return True

# @property
# def content(self) -> str:
# 	# TODO: this doesnt work when multiple files!
# 	if self._content is not None:
# 		return self._content
# 	stripped_content = system.run(f"gh gist view '{self.id}'", verbose=config.verbose).splitlines()
# 	if self.description:
# 		try:
# 			index_of_description = next(i for i, line in enumerate(stripped_content) if line.strip().startswith(self.description))
# 		except StopIteration:
# 			pass
# 		else:
# 			stripped_content.pop(index_of_description)
# 			stripped_content = "\n".join(list(filter(bool, map(str.strip, stripped_content))))
# 		finally:
# 			self._content = stripped_content
# 	return self._content
def get_gh_gist_list()-> List[str]:
	"""Calls `gh gist list -L 100` to get the list of gists.
	May use cache."""
	if config.cache_mode == 'r' and (gh_gist_list := cache.gh_gist_list) is not None:
		return gh_gist_list
	gh_gist_list = system.run('gh gist list -L 100', verbose=config.verbose).splitlines()  # not safe
	if config.cache_mode == 'w':
		cache.gh_gist_list = gh_gist_list
	return gh_gist_list


def get_file2gist_map() -> Dict[str, List[Gist]]:
	logger.debug('[#]Getting gists...[/]')
	# if config.cache_mode == 'r' and (file2gist_map := cache.file2gist_map) is not None:
	# 	return file2gist_map
	file2gist: Dict[str, List[Gist]] = defaultdict(list)
	gists: List[Gist] = []
	gh_gist_list: List[str] = get_gh_gist_list()


	# * gist.build_files()
	if config.max_threads:
		max_workers = min(config.max_threads, len(gh_gist_list))
	else:
		max_workers= len(gh_gist_list)
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist_str in gh_gist_list:
			gist = Gist(*gist_str.split('\t'))

			# There shouldn't be many false positives, because description includes
			# spaces which means pattern.search(gist.description), and id is specific
			if tmrignore.is_ignored(gist.id) or tmrignore.is_ignored(gist.description):
				logger.warning(f"skipping [b]{gist.id} ('{gist.description[:32]}')[/b]: excluded")
				continue

			executor.submit(gist.build_files)
			gists.append(gist)

	# * file.content = gh gist view ... -f <NAME>
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist in gists:

			for name, file in gist.files.items():
				if file.ignored:
					logger.warning(f"gist file [b]'{name}'[/b] of {gist.id} ('{gist.description[:32]}'): skipping; excluded")
					continue
				executor.submit(gist.popuplate_files_content)
				file2gist[name].append(gist)
			if config.verbose >= 2:
				logger.debug(gist)

	return file2gist
