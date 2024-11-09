import os
import subprocess as sp
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from too_many_repos import system
from too_many_repos.log import logger
from too_many_repos.system import run
from too_many_repos.tmrconfig import config

Remotes = namedtuple("Remotes", ["origin", "upstream", "tracking", "current_branch"])


@contextmanager
def visit_dir(path) -> Generator[None, Any, None]:
    prev_cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev_cwd)


def is_repo(path: Path) -> bool:
    """Checks for existence of .git dir, and does light arbitrary checks inside it"""
    gitdir = path / ".git"
    try:
        if not gitdir.is_dir():
            return False
    except PermissionError:
        logger.warning(f"[b]{gitdir}[/b]: PermissionError")
        return False
    for subdir in ("info", "refs"):
        if not (gitdir / subdir).is_dir():
            return False
    for file in ("config", "HEAD"):
        if not (gitdir / file).is_file():
            return False
    return True


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.gitdir = self.path / ".git"
        self.status = None
        self.remotes = self.get_remotes()

    def __repr__(self) -> str:
        return f"Repo({self.path})"

    def fetch(self) -> None:
        with visit_dir(self.path):
            config.verbose >= 2 and logger.debug(f"git fetch in {self.path}...")
            system.run(
                "git fetch --all --prune --jobs=10",
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
            )

    def popuplate_status(self) -> None:
        with visit_dir(self.path):
            config.verbose >= 2 and logger.debug(f"git status in {self.path}...")
            status = system.run("git status")
        self.status = status

    def is_gitdir_too_big(self) -> bool:  # Slow (10ms~100ms)
        gitdir_size_limit_byte = config.gitdir_size_limit_mb * 1_000_000
        return _dir_is_bigger_than(self.gitdir, gitdir_size_limit_byte)

    def get_remotes(self) -> Remotes:
        """origin, upstream, tracking"""
        config.verbose >= 2 and logger.debug(f"{self.path}: getting remotes...")
        origin = "/".join(
            run("git remote get-url origin", stderr=sp.DEVNULL).split("/")[-2:]
        )
        upstream = "/".join(
            run("git remote get-url upstream", stderr=sp.DEVNULL).split("/")[-2:]
        )
        tracking = run(
            "git rev-parse --abbrev-ref --symbolic-full-name @{u}", stderr=sp.DEVNULL
        )
        current_branch = run("git rev-parse --abbrev-ref HEAD", stderr=sp.DEVNULL)
        return Remotes(origin, upstream, tracking, current_branch)


def _dir_is_bigger_than(path: os.PathLike, size_bytes: int) -> bool:
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _dir_is_bigger_than(entry.path, size_bytes)
                    if total > size_bytes:
                        return True
            except (PermissionError, FileNotFoundError):
                continue
    return total > size_bytes
