import subprocess as sp
from collections import namedtuple
from pathlib import Path
from typing import Tuple, NoReturn
import os
from contextlib import contextmanager

from too_many_repos import system
from too_many_repos.log import logger
from too_many_repos.system import run
from too_many_repos.tmrconfig import config

Remotes = namedtuple('Remotes',['origin','upstream','tracking'])

@contextmanager
def visit_dir(path):
    prev_cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev_cwd)

class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.gitdir = self.path / '.git'
        self.status = None
        self.remotes = None

    def fetch(self) -> NoReturn:
        with visit_dir(self.path):
            system.run('git fetch --all --prune --jobs=10', stdout=sp.DEVNULL, stderr=sp.DEVNULL, verbose=config.verbose)

    def popuplate_status(self) -> NoReturn:
        with visit_dir(self.path):
            status = system.run('git status', verbose=config.verbose)
        self.status = status


    def is_gitdir_too_big(self) -> bool:
        gitdir_size = 0
        for entry in self.gitdir.glob('**/*'):
            gitdir_size += entry.stat().st_size / 1000000
            if gitdir_size >= config.gitdir_size_limit_mb:
                return True
        return False


    def is_repo(self) -> bool:
        """Checks for existence of .git dir, and does light arbitrary checks inside it"""
        try:
            if not self.gitdir.is_dir():
                return False
        except PermissionError:
            logger.warning(f"[b]{self.gitdir}[/b]: PermissionError[/]")
            return False
        for subdir in ('info','refs'):
            if not (self.gitdir / subdir).is_dir():
                return False
        for file in ('config', 'HEAD'):
            if not (self.gitdir / file).is_file():
                return False
        return True

    def popuplate_remotes(self) -> NoReturn:
        """origin, upstream, tracking"""
        logger.debug(f'[#]{self.path}: getting remotes...[/]')
        origin = '/'.join(run('git remote get-url origin', stderr=sp.DEVNULL).split('/')[-2:])
        upstream = '/'.join(run('git remote get-url upstream', stderr=sp.DEVNULL).split('/')[-2:])
        tracking = run('git rev-parse --abbrev-ref --symbolic-full-name @{u}', stderr=sp.DEVNULL)
        self.remotes = Remotes(origin, upstream, tracking)