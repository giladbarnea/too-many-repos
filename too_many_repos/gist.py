import os
from collections import defaultdict
from concurrent import futures as fut
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any, Literal, Dict, NoReturn, ForwardRef, Iterable, Iterator

from too_many_repos import system
from too_many_repos.cache import cache
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore


def remove_empty_lines_and_rstrip(lines: Iterable[str]) -> Iterator[str]:
	return filter(bool, map(str.rstrip, lines))


Difference = Literal['whitespace', 'content', 'order', False]


class GistFile:
	content: List[str]
	stripped_content: List[str]
	tmp_path: str
	stripped_tmp_path: str
	diffs: Dict[Path, Difference]
	gist: ForwardRef('Gist')
	name: str

	def __init__(self, name: str, gist: ForwardRef('Gist')):
		# `content` and `stripped_content` are set by popuplate_files_content()
		self.content: List[str] = []
		self.stripped_content: List[str] = []
		self.diffs = dict()
		self.name = name
		self.gist = gist
		stem, ext = os.path.splitext(name)

		# gists/aa160cb1cc599ba71a4f634183a663b7/ripgrep.remote.rc
		self.tmp_path = f'/{config.cache.path}/gists/{self.gist.id}/{stem}.remote{ext}'

		# gists/aa160cb1cc599ba71a4f634183a663b7/ripgrep.remote.stripped.rc
		self.stripped_tmp_path = f'/{config.cache.path}/gists/{self.gist.id}/{stem}.remote.stripped{ext}'

		self._written_to_file = False

	def __repr__(self) -> str:
		rv = f"GistFile('{self.name}') {{ \n\tcontent: "
		if self.content:
			content_str = "\n".join(self.content[:16])
			rv += rf'"{content_str}..."'
		else:
			rv += f'--'
		if self.gist:
			rv += f"\n\tGist: {self.gist.short()}"
		rv += f"\n\tdiffs: {self.diffs} }}"
		return rv

	def diff(self, against: Path) -> NoReturn:
		"""Checks whether the stripped contents of `against` and this file's content are different."""
		# TODO: (bug) difference in 2 spaces vs 4 spaces vs tab count like 'content' diff
		#  because it's rstrip and not regular strip
		#  need to re.sub(r'\s\t',' ') and detect num of spaces
		# TODO (reuse files): write to ~/.cache/<SESSION>/ instead and check if exists before
		logger.debug(f'Gist | {self.gist.short()} diffing "{against}"...')

		# Save the content of this file to a tmp file
		if not self._written_to_file:
			with open(self.tmp_path, mode='w') as tmp:
				tmp.writelines(self.content)

			with open(self.stripped_tmp_path, mode='w') as tmp:
				tmp.writelines(self.stripped_content)

			self._written_to_file = True

		# Strip the contents of the local file and save it to a tmp file
		stripped_against_path = f'/{config.cache.path}/gists/{self.gist.id}/{against.stem}.local.stripped{against.suffix}'
		against_lines = against.open().read().splitlines()  # readlines() returns a list each ending with linebreak
		stripped_against_lines = list(remove_empty_lines_and_rstrip(against_lines))
		with open(stripped_against_path, mode='w') as tmp:
			tmp.writelines(stripped_against_lines)

		different_stripped = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{self.stripped_tmp_path}" "{stripped_against_path}"')
		different_as_is = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{self.tmp_path}" "{against}"')

		# If stripped versions are different, it's possible that the content
		# is the same, only the order of the lines is different.
		# If and only if stripped versions are the same, but `diff` is true
		# for the untouched files, it means they're only different in whitespace.
		difference: Difference
		if different_stripped:
			difference = 'content'
		elif different_as_is:
			difference = 'whitespace'
		else:
			difference = False

		# Check if local and gist still different when content is sorted
		if difference == 'content' and set(self.stripped_content) == set(stripped_against_lines):
			difference = 'order'
		self.diffs[against] = difference


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

	@cache
	def _get_file_names(self) -> List[str]:
		"""Calls `gh gist view "{self.id}" --files` to get this gist's list of
		file names (e.g 'alpine.sh').
		May use cache."""
		if 'r' in config.cache.mode and \
				config.cache.gist_filenames and \
				(filenames := cache.load_gist_filenames(self.id)) is not None:
			return filenames
		filenames = system.run(f'gh gist view "{self.id}" --files').splitlines()
		if 'w' in config.cache.mode and config.cache.gist_filenames:
			cache.dump_gist_filenames(self.id, filenames)
		return filenames

	def _get_file_content(self, file_name) -> List[str]:
		"""Calls `gh gist view '{self.id}' -f '{file_name}'` to get the file's content.
		May use cache."""
		if 'r' in config.cache.mode and \
				config.cache.gist_content and \
				(file_content := cache.load_gist_file_content(self.id, file_name)) is not None:
			return file_content
		content = system.run(f'gh gist view "{self.id}" -f "{file_name}"').splitlines()
		if 'w' in config.cache.mode and config.cache.gist_content:
			cache.dump_gist_file_content(self.id, file_name, content)
		return content

	def build_self_files(self, *, skip_ignored: bool) -> NoReturn:
		"""
		Popuplates self.files.

		Calls self._get_file_names() (GET req) which may use cache.

		Called by build_filename2gistfiles() in a threaded context."""
		filenames = self._get_file_names()
		for name in filenames:
			if tmrignore.is_ignored(name) and skip_ignored:
				logger.warning(f"Gist | file [b]'{name}'[/b] of {self.short()}: skipping; excluded")
				continue
			file = GistFile(name, self)
			self.files[name] = file
		logger.debug(f"Gist | [b]{self.short()}[/b] built {len(self.files)} files")

	def popuplate_files_content(self) -> NoReturn:
		"""
		For each file in self.files, sets its content.

		Calls self._get_file_content(self, file_name) which may use cache.

		Called by build_filename2gistfiles() in a threaded context.
		"""
		for name, gistfile in self.files.items():
			content = self._get_file_content(name)
			gistfile.content = content
			gistfile.stripped_content = list(remove_empty_lines_and_rstrip(gistfile.content))
		logger.debug(f"Gist | [b]{self.short()}[/b] populated files content")


def get_gists_list() -> List[str]:
	"""Calls `gh gist list -L 100` to get the list of gists.
	May use cache."""

	if 'r' in config.cache.mode and \
			config.cache.gists_list and \
			(gists_list := cache.gists_list) is not None:
		return gists_list
	gists_list = system.run('gh gist list -L 100').splitlines()  # not safe
	if 'w' in config.cache.mode and config.cache.gists_list:
		cache.gists_list = gists_list
	return gists_list


def build_filename2gistfiles() -> Dict[str, List[GistFile]]:
	"""
	Maps the names of the GistFiles to their actual GistFiles.
	"""
	logger.info('\nGist | Getting list of gists...')
	filename2gistfiles: Dict[str, List[GistFile]] = defaultdict(list)
	gists: List[Gist] = []
	gists_list: List[str] = get_gists_list()

	# * files = gh gist view ... --files
	logger.info('\nGist | Getting list of files for each gist...')
	max_workers = min((gists_list_len := len(gists_list)), config.max_workers or gists_list_len)
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist_str in gists_list:
			gist = Gist(*gist_str.split('\t'))

			# There shouldn't be many false positives, because description includes
			# spaces which means pattern.search(gist.description), and id is specific.
			# Note: don't check for file names here
			if tmrignore.is_ignored(gist.id) or tmrignore.is_ignored(gist.description):
				logger.warning(f"Gist | [b]{gist.short()}[/b]: skipping; excluded")
				continue

			future = executor.submit(gist.build_self_files, skip_ignored=True)
			# if exc := future.exception():
			# 	raise exc
			gists.append(gist)

	# * file.content = gh gist view ... -f <NAME>
	logger.info('\nGist | Populating contents of all gist files...')
	with fut.ThreadPoolExecutor(max_workers) as executor:
		for gist in gists:
			for name, gistfile in gist.files.items():
				future = executor.submit(gist.popuplate_files_content)
				# if exc := future.exception():
				# 	raise exc
				filename2gistfiles[name].append(gistfile)
			config.verbose >= 2 and logger.debug(gist)

	return filename2gistfiles
