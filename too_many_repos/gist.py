from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Any, Literal, Dict, NoReturn
from collections import defaultdict
from concurrent import futures as fut
import pickle
from too_many_repos import system
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore

class File:
	ignored: bool = False
	content: str = ''


@dataclass
class Gist:
	id: str
	description: str
	filecount: Any
	permissions: Literal['secret','public']
	date: str
	files: Dict[str, File] = field(default_factory=dict)
	def __str__(self):
		return f"{self.id[:16]} '{self.description}' ({self.filecount} files)"

	def __post_init__(self):
		self.filecount = int(self.filecount.partition(' ')[0])

	def build_files(self) -> NoReturn:
		view_process = system.popen(f'gh gist view "{self.id}" --files', verbose=config.verbose)
		files = view_process.communicate()[0].decode().splitlines()
		for name in files:
			file = File()
			file.ignored = tmrignore.is_ignored(name)
			self.files[name] = file
		if config.verbose:
			logger.debug(f"[#]{self.id[:16]} ('{self.description[:16]}') built {len(self.files)} files[/]")

	def diff(self, path: Path) -> bool:
		if config.verbose:
			logger.debug(f'[#]diffing {path}...')
		gist_file = self.files.get(path.name)
		tmp_gist_path = f'/tmp/{self.id}-{path.name}'
		with open(tmp_gist_path, mode='w') as tmp:
			tmp.write("\n".join(gist_file.content))

		tmp_file_path= f'/tmp/{path.name}.gist{path.suffix}'
		with open(tmp_file_path, mode='w') as tmp:
			tmp.write('\n'.join(filter(bool, map(str.strip, path.open().readlines()))))

		diff = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{tmp_gist_path}" "{tmp_file_path}"')
		if not diff:
			logger.info(f"[good][b]{path.absolute()}[/b]: file and gist {self.id[:16]} ('{self.description[:32]}') file are identical[/]")
			return False

		prompt = f"[warn][b]{path.absolute()}[/b]: file and gist {self.id} ('{self.description[:32]}') are different"
		logger.info(prompt)


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

def get_file2gist_map() -> Dict[str, List[Gist]]:
	file2gist: Dict[str, List[Gist]] = defaultdict(list)
	gists: List[Gist] = []
	if config.verbose:
		logger.debug('[#]Getting gists...[/]')
	# gists_list = system.run('gh gist list -L 100', verbose=config.verbose).splitlines()  # not safe
	# with open('/tmp/gists.pickle', mode='w+b') as gpickle:
	# 	pickle.dump(gists_list,gpickle)
	with open('/tmp/gists.pickle', mode='r+b') as gpickle:
		gists_list = pickle.load(gpickle)
	with fut.ThreadPoolExecutor(max_workers=len(gists_list)) as executor:
		for gist_str in gists_list:
			gist = Gist(*gist_str.split('\t'))

			# There shouldn't be many false positives, because description includes
			# spaces which means pattern.search(gist.description), and id is specific
			if tmrignore.is_ignored(gist.id) or tmrignore.is_ignored(gist.description):
				if config.verbose:
					logger.warning(f"skipping [b]{gist.id} ('{gist.description[:32]}')[/b]: excluded")
				continue

			executor.submit(gist.build_files)
			gists.append(gist)

	with fut.ThreadPoolExecutor(max_workers=len(gists_list)) as executor:
		for gist in gists:

			for name, file in gist.files.items():
				if file.ignored:
					if config.verbose:
						logger.warning(f"gist file [b]'{name}'[/b] of {gist.id} ('{gist.description[:32]}'): skipping; excluded")
					continue
				file2gist[name].append(gist)
				file.content = executor.submit(system.run, f"gh gist view '{gist.id}' -f '{name}'", verbose=config.verbose)
				# file.content = system.run(f"gh gist view '{gist.id}' -f '{name}'", verbose=config.verbose).splitlines()
			if config.verbose >= 2:
				logger.debug(gist)
	for gist in gists:
		for name, file in gist.files.items():
			file.content = list(filter(bool, map(str.strip, file.content.result().splitlines())))
			logger.debug(f'[#]Got {name} content[/]')
	return file2gist