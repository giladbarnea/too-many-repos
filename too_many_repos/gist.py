import os
import re
from collections import defaultdict
from concurrent import futures as fut
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any, Literal, Dict, NoReturn, ForwardRef

from pdbpp import break_on_exc

from too_many_repos import system
from too_many_repos.cache import cache
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore

Difference = Literal['whitespace', 'content', False]


class GistFile:
	content: str
	stripped_content: str
	tmp_path: str
	stripped_tmp_path: str
	diffs: Dict[Path, Difference]
	gist: ForwardRef('Gist')
	name: str

	def __init__(self, name: str, gist: ForwardRef('Gist')):
		self.content: str = ''
		self.stripped_content: str = ''
		self.diffs = dict()
		self.name = name
		self.gist = gist
		self.tmp_path = f'/tmp/{self.gist.id}__{name}'
		stem, ext = os.path.splitext(name)
		self.stripped_tmp_path = f'/tmp/{self.gist.id}__{stem}__stripped{ext}'

	def __repr__(self) -> str:
		rv = f"GistFile('{self.name}') {{ \n\tcontent: "
		if self.content:
			rv += rf'"{self.content[:16]}..."'
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
		with open(self.tmp_path, mode='w') as tmp:
			tmp.write(self.content)

		with open(self.stripped_tmp_path, mode='w') as tmp:
			tmp.write(self.stripped_content)

		# Strip the contents of the local file and save it to a tmp file
		stripped_against_path = f'/tmp/{against.stem}__stripped{against.suffix}'
		against_lines = against.open().read().splitlines()  # readlines() returns a list each ending with linebreak
		stripped_against_lines = list(filter(bool, map(str.rstrip, against_lines)))
		with open(stripped_against_path, mode='w') as tmp:
			tmp.write('\n'.join(stripped_against_lines))

		different_stripped = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{self.stripped_tmp_path}" "{stripped_against_path}"')
		different_as_is = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{self.tmp_path}" "{against}"')
		difference: Difference
		if different_stripped:
			difference = 'content'
		elif different_as_is:
			difference = 'whitespace'
		else:

			difference = False
		if difference and set(self.stripped_content.splitlines()) == set(filter(bool, self.content.splitlines())):
			# This means file is flat, like .tmrignore. Check if local and gist still different when content is sorted
			against_set = set(filter(bool, against_lines))
			self_set = set(filter(bool, self.content.splitlines()))
			if against_set == self_set:
				breakpoint()
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

	def _get_file_names(self) -> List[str]:
		"""Calls `gh gist view "{self.id}" --files` to get this gist's list of
		file names (e.g 'alpine.sh').
		May use cache."""
		if 'r' in config.cache.mode and \
				config.cache.gist_filenames and \
				(filenames := cache.get_gist_filenames(self.id)) is not None:
			return filenames
		filenames = system.run(f'gh gist view "{self.id}" --files').splitlines()
		if 'w' in config.cache.mode and config.cache.gist_filenames:
			cache.set_gist_filenames(self.id, filenames)
		return filenames

	def _get_file_content(self, file_name) -> str:
		"""Calls `gh gist view '{self.id}' -f '{file_name}'` to get the file's content.
		May use cache."""
		if 'r' in config.cache.mode and \
				config.cache.gist_content and \
				(file_content := cache.get_gist_file_content(self.id, file_name)) is not None:
			return file_content
		content = system.run(f"gh gist view '{self.id}' -f '{file_name}'")
		if 'w' in config.cache.mode and config.cache.gist_content:
			cache.set_gist_file_content(self.id, file_name, content)
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
		for name, file in self.files.items():
			content = self._get_file_content(name)
			file.content = content
			file.stripped_content = '\n'.join(filter(bool, map(str.rstrip, content.splitlines())))
		logger.debug(f"Gist | [b]{self.short()}[/b] populated files content")


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

	if 'r' in config.cache.mode and \
			config.cache.gist_list and \
			(gist_list := cache.gist_list) is not None:
		return gist_list
	gist_list = system.run('gh gist list -L 100').splitlines()  # not safe
	if 'w' in config.cache.mode and config.cache.gist_list:
		cache.gist_list = gist_list
	return gist_list


def build_filename2gistfiles() -> Dict[str, List[GistFile]]:
	"""
	Maps the names of the GistFiles to their actual GistFiles.
	"""
	logger.info('\nGist | Getting list of gists...')
	filename2gistfiles: Dict[str, List[GistFile]] = defaultdict(list)
	gists: List[Gist] = []
	gist_list: List[str] = get_gist_list()

	# * files = gh gist view ... --files
	logger.info('\nGist | Getting list of files for each gist...')
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
