import os
import shlex
import subprocess
import sys

from too_many_repos.log import logger
from too_many_repos.tmrconfig import config


def run(cmd: str, *args, **kwargs) -> str:
    """
    A wrapper to ``subprocess.run(cmd, stdout=subprocess.PIPE)``.

    Keyword Args:
        stdout (int): instead of default `subprocess.PIPE`
        verbose (bool): If True, prints 'Running: ...'

    Returns:
        str: decoded stdout (or empty string).
    """
    if "stdout" not in kwargs:
        kwargs.update(stdout=subprocess.PIPE)
    if kwargs.pop("verbose", None) is not None or config.verbose >= 2:
        logger.debug(f"Running: [code]{cmd}[/]")
    stdout = subprocess.run(shlex.split(cmd), *args, **kwargs).stdout
    if stdout:
        return stdout.strip().decode()
    return ""


def popen(
    cmd: str,
    *,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    verbose: bool = False,
    executable: str = "/opt/homebrew/bin/zsh",
    shell: bool = True,
    **kwargs,
) -> subprocess.Popen:
    if verbose or config.verbose >= 2:
        logger.debug(f"Process: [code]{cmd}[/]")
    return subprocess.Popen(
        cmd, stdout=stdout, stderr=stderr, executable=executable, shell=shell, **kwargs
    )


def is_macos() -> bool:
    return sys.platform == "darwin"


def diff_quiet(diff_args) -> bool:
    """True if same."""
    if is_macos():
        process = popen(
            f"diff --ignore-space-change --strip-trailing-cr -q --color=never {diff_args}",
            # stdout=subprocess.DEVNULL,
            # stderr=subprocess.DEVNULL,
        )
    else:
        process = popen(
            f"diff --ignore-trailing-space --quiet --ignore-all-space --strip-trailing-cr --suppress-blank-empty {diff_args}",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    stdout, stderr = process.communicate(timeout=20)
    return process.returncode == 0


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
