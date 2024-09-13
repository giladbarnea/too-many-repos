import os
import shlex
import subprocess as sp
import sys

from too_many_repos.log import logger
from too_many_repos.tmrconfig import config


def run(cmd: str, *args, **kwargs) -> str:
    """
    A wrapper to ``subprocess.run(cmd, stdout=sp.PIPE)``.

    Keyword Args:
        stdout (int): instead of default `sp.PIPE`
        verbose (bool): If True, prints 'Running: ...'

    Returns:
        str: decoded stdout (or empty string).
    """
    if 'stdout' not in kwargs:
        kwargs.update(stdout=sp.PIPE)
    if kwargs.pop('verbose', None) is not None or config.verbose >= 2:
        logger.debug(f'Running: [code]{cmd}[/]')
    stdout = sp.run(shlex.split(cmd), *args, **kwargs).stdout
    if stdout:
        return stdout.strip().decode()
    return ""

def popen(cmd: str, *args, **kwargs) -> sp.Popen:
    if 'stdout' not in kwargs:
        kwargs.update(stdout=sp.PIPE)
    if 'stderr' not in kwargs:
        kwargs.update(stderr=sp.PIPE)
    if kwargs.pop('verbose', None) is not None or config.verbose >= 2:
        logger.debug(f'Process: [code]{cmd}[/]')
    return sp.Popen(shlex.split(cmd), *args, **kwargs)

def is_macos() -> bool:
    return sys.platform == "darwin"


def diff_quiet(diff_args) -> bool:
    "True if same."
    if is_macos():
        process = popen(
            f"diff --ignore-blank-lines --ignore-space-change --strip-trailing-cr --quiet {diff_args}",
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )
    else:
        process = popen(
            f"diff --ignore-trailing-space --quiet --ignore-all-space --ignore-blank-lines --strip-trailing-cr --suppress-blank-empty {diff_args}",
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )
    return process.wait() == 0


def diff_interactive(diff_args) -> int:
    """Side-by-side, colors, os.system."""
    if is_macos():
        # with -u (unified?)
        return os.system(
            f"diff --side-by-side -u --ignore-blank-lines --ignore-space-change --strip-trailing-cr --algorithm=patience {diff_args}"
        )
    return os.system(
        f"diff --ignore-trailing-space -u --quiet --strip-trailing-cr {diff_args}"
    )
