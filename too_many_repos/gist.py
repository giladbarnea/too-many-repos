from collections import defaultdict
from concurrent import futures as fut
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any, Literal, Dict, NoReturn, ForwardRef

from too_many_repos import system
from too_many_repos.cache import cache
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore


class GistFile:
	content: str = ''
	diffs: Dict[Path, bool]
	gist: ForwardRef('Gist')

	def __init__(self):
		self.diffs = dict()

	def __repr__(self) -> str:
		rv = f"GistFile {{ \n\tcontent: "
		if self.content:
			rv += f'"{self.content[:16]}..."'
		else:
			rv += f'--'
		if self.gist:
			rv += f"\n\tgist: {self.gist.short()}"
		rv += f"\n\tdiffs: {self.diffs} }}"
		return rv

	def diff(self, path: Path) -> bool:
		"""Returns whether self.diff[path] with whether the stripped contents of `path` and this self are different."""
		logger.debug(f'[#]Gist: {self.gist.short()} diffing "{path}"...')
		# gist_file: GistFile = self.files.get(path.name)
		tmp_gist_path = f'/tmp/{self.gist.id}_{path.name}'
		with open(tmp_gist_path, mode='w') as tmp:
			tmp.write(self.content)

		# Strip the contents of the local file and save it to a tmp file
		tmp_file_path = f'/tmp/{path.name}.gist{path.suffix}'
		with open(tmp_file_path, mode='w') as tmp:
			tmp.write('\n'.join(filter(bool, map(str.strip, path.open().readlines()))))

		if path.open().readlines() == set(map(str.strip, path.open().readlines())) or \
				self.content.splitlines() == set(map(str.strip, self.content.splitlines())):
			breakpoint()
		diff = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{tmp_gist_path}" "{tmp_file_path}"')
		return bool(diff)
		# if not diff:
		# 	# logger.info(f"[good][b]Diff {path.absolute()}[/b]: and [b]{self.gist.short()}[/b] file are identical[/]")
		# 	self.diff = False
		# 	return False
		#
		# # prompt = f"[warn][b]Diff {path.absolute()}[/b]: and [b]{self.gist.short()}[/b] are [b]different[/]"
		# # logger.info(prompt)
		# self.diff = True
		# return True


@dataclass
class Gist:
	id: str
	description: str
	filecount: Any
	permissions: Literal['secret', 'public']
	date: str
	files: Dict[str, GistFile] = field(default_factory=dict)

	def __str__(self):
		return f"{self.id[:16]} '{self.description}' ({self.filecount} files)"

	def short(self) -> str:
		return f"{self.id[:8]} '{self.description[:32]}'"

	def __post_init__(self):
		self.filecount = int(self.filecount.partition(' ')[0])

	def _get_file_names(self) -> List[str]:
		"""Calls `gh gist view "{self.id}" --files` to get this gist's list of file names.
		May use cache."""
		if config.cache.mode in ('r', 'r+w') and \
				config.cache.gist_filenames and \
				(filenames := cache.get_gist_filenames(self.id)) is not None:
			return filenames
		filenames = system.run(f'gh gist view "{self.id}" --files').splitlines()
		if config.cache.mode in ('w', 'r+w') and config.cache.gist_filenames:
			cache.set_gist_filenames(self.id, filenames)
		return filenames

	def _get_file_content(self, file_name) -> str:
		"""Calls `gh gist view '{self.id}' -f '{file_name}'` to get the file's content.
		May use cache."""
		if config.cache.mode in ('r', 'r+w') and \
				config.cache.gist_content and \
				(file_content := cache.get_gist_file_content(self.id, file_name)) is not None:
			return file_content
		content = system.run(f"gh gist view '{self.id}' -f '{file_name}'")
		if config.cache.mode in ('w', 'r+w') and config.cache.gist_content:
			cache.set_gist_file_content(self.id, file_name, content)
		return content

	def build_self_files(self, *, skip_ignored: bool) -> NoReturn:
		"""
		Popuplates self.files.

		Calls self._get_file_names() (GET req) which may use cache.

		Called by build_filename2gistfiles() in a threaded context."""
		filenames = self._get_file_names()
		for name in filenames:
			file = GistFile()
			if tmrignore.is_ignored(name) and skip_ignored:
				logger.warning(f"Gist: file [b]'{name}'[/b] of {self.short()}: skipping; excluded")
				continue
			file.gist = self
			self.files[name] = file
		logger.debug(f"[#]Gist: [b]{self.short()}[/b] built {len(self.files)} files[/]")

	def popuplate_files_content(self) -> NoReturn:
		"""
		For each file in self.files, sets its content.

		Calls self._get_file_content(self, file_name) which may use cache.

		Called by build_filename2gistfiles() in a threaded context.
		"""
		for name, file in self.files.items():
			content = self._get_file_content(name)
			file.content = content
		logger.debug(f"[#]Gist: [b]{self.short()}[/b] populated files content[/]")

	# def diff(self, path: Path) -> bool:
	# 	"""Returns Whether the stripped contents of `path` and this gist's respective file are different.
	#
	# 	Sets `file.diff` attribute."""
	# 	logger.debug(f'[#]Gist: diffing {path}...')
	# 	gist_file: GistFile = self.files.get(path.name)
	# 	tmp_gist_path = f'/tmp/{self.id}_{path.name}'
	# 	with open(tmp_gist_path, mode='w') as tmp:
	# 		tmp.write(gist_file.content)
	#
	# 	# Strip the contents of the local file and save it to a tmp file
	# 	tmp_file_path = f'/tmp/{path.name}.gist{path.suffix}'
	# 	with open(tmp_file_path, mode='w') as tmp:
	# 		tmp.write('\n'.join(filter(bool, map(str.strip, path.open().readlines()))))
	#
	# 	if path.open().readlines() == list(map(str.strip, path.open().readlines())) or \
	# 			gist_file.content.splitlines() == list(map(str.strip, gist_file.content.splitlines())):
	# 		breakpoint()
	# 	diff = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{tmp_gist_path}" "{tmp_file_path}"')
	# 	if not diff:
	# 		logger.info(f"[good][b]Diff {path.absolute()}[/b]: and [b]{self.short()}[/b] file are identical[/]")
	# 		gist_file.diff = False
	# 		return False
	#
	# 	prompt = f"[warn][b]Diff {path.absolute()}[/b]: and [b]{self.short()}[/b] are [b]different[/]"
	# 	logger.info(prompt)
	# 	gist_file.diff = True
	# 	return True


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
def get_gist_list() -> List[str]:
	"""Calls `gh gist list -L 100` to get the list of gists.
	May use cache."""
	if config.cache.mode in ('r', 'r+w') and \
			config.cache.gist_list and \
			(gist_list := cache.gist_list) is not None:
		return gist_list
	gist_list = system.run('gh gist list -L 100').splitlines()  # not safe
	if config.cache.mode in ('w', 'r+w') and config.cache.gist_list:
		cache.gist_list = gist_list
	return gist_list


def build_filename2gistfiles() -> Dict[str, List[GistFile]]:
	"""
	Maps the names of the GistFiles to their actual GistFiles.
	"""
	logger.info('\nGeting list of gists...')
	filename2gistfiles: Dict[str, List[GistFile]] = defaultdict(list)
	gists: List[Gist] = []
	gist_list: List[str] = get_gist_list()

	# * files = gh gist view ... --files
	logger.info('\nGeting list of files for each gist...')
	max_workers = min((gist_list_len := len(gist_list)), config.max_workers or gist_list_len)
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist_str in gist_list:
			gist = Gist(*gist_str.split('\t'))

			# There shouldn't be many false positives, because description includes
			# spaces which means pattern.search(gist.description), and id is specific.
			# Note: don't check for file names here
			if tmrignore.is_ignored(gist.id) or tmrignore.is_ignored(gist.description):
				logger.warning(f"Gist | [b]{gist.short()}[/b]: skipping; excluded")
				continue

			executor.submit(gist.build_self_files, skip_ignored=True)
			gists.append(gist)

	# * file.content = gh gist view ... -f <NAME>
	logger.info('\nPopulating contents of all files...')
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist in gists:
			for name, gistfile in gist.files.items():
				executor.submit(gist.popuplate_files_content)
				filename2gistfiles[name].append(gistfile)
			config.verbose >= 2 and logger.debug(gist)

	return filename2gistfiles
