import os
import subprocess as sp
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from too_many_repos import system
from too_many_repos.log import logger
from too_many_repos.system import run
from too_many_repos.tmrconfig import config

Remotes = namedtuple('Remotes', ['origin', 'upstream', 'tracking', 'current_branch'])


@contextmanager
def visit_dir(path):
	prev_cwd = os.getcwd()
	try:
		os.chdir(path)
		yield
	finally:
		os.chdir(prev_cwd)


def is_repo(path: Path) -> bool:
	"""Checks for existence of .git dir, and does light arbitrary checks inside it"""
	gitdir = path / '.git'
	try:
		if not gitdir.is_dir():
			return False
	except PermissionError:
		logger.warning(f"[b]{gitdir}[/b]: PermissionError")
		return False
	for subdir in ('info', 'refs'):
		if not (gitdir / subdir).is_dir():
			return False
	for file in ('config', 'HEAD'):
		if not (gitdir / file).is_file():
			return False
	return True


class Repo:
	def __init__(self, path: Path):
		self.path = path
		self.gitdir = self.path / '.git'
		self.status = None
		self.remotes = None

	def __repr__(self) -> str:
		return f"Repo({self.path})"

	def fetch(self) -> NoReturn:
		with visit_dir(self.path):
			config.verbose >= 2 and logger.debug(f'git fetch in {self.path}...')
			system.run('git fetch --all --prune --jobs=10', stdout=sp.DEVNULL, stderr=sp.DEVNULL)

	def popuplate_status(self) -> NoReturn:
		with visit_dir(self.path):
			config.verbose >= 2 and logger.debug(f'git status in {self.path}...')
			status = system.run('git status')
		self.status = status

	def is_gitdir_too_big(self) -> bool:	# Slow (10ms~100ms)
		gitdir_size = 0
		gitdir_size_limit_byte = config.gitdir_mb_limit * 1_000_000
		for entry in self.gitdir.glob('**/*'):
			gitdir_size += entry.stat().st_size
			if gitdir_size >= gitdir_size_limit_byte:
				return True
		return False

	def popuplate_remotes(self) -> NoReturn:
		"""origin, upstream, tracking"""
		config.verbose >= 2 and logger.debug(f'{self.path}: getting remotes...')
		origin = '/'.join(run('git remote get-url origin', stderr=sp.DEVNULL).split('/')[-2:])
		upstream = '/'.join(run('git remote get-url upstream', stderr=sp.DEVNULL).split('/')[-2:])
		tracking = run('git rev-parse --abbrev-ref --symbolic-full-name @{u}', stderr=sp.DEVNULL)
		current_branch = run('git rev-parse --abbrev-ref HEAD', stderr=sp.DEVNULL)
		self.remotes = Remotes(origin, upstream, tracking, current_branch)
