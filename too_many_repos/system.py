import shlex
import subprocess as sp

from too_many_repos.log import logger


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
    try:
        if kwargs.pop('verbose') is not None:
            logger.debug(f'[#]Running[/]: [rgb(125,125,125) i on rgb(25,25,25)]{cmd}[/]')
    except KeyError:
        pass
    stdout = sp.run(shlex.split(cmd), *args, **kwargs).stdout
    if stdout:
        return stdout.strip().decode()
    return ""

def popen(cmd: str, *args, **kwargs) -> sp.Popen:
    if 'stdout' not in kwargs:
        kwargs.update(stdout=sp.PIPE)
    if 'stderr' not in kwargs:
        kwargs.update(stderr=sp.PIPE)
    try:
        if kwargs.pop('verbose') is not None:
            logger.debug(f'[#]Process[/]: [rgb(125,125,125) i on rgb(25,25,25)]{cmd}[/]')
    except KeyError:
        pass
    return sp.Popen(shlex.split(cmd), *args, **kwargs)