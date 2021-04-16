import subprocess as sp
from typing import Tuple

from too_many_repos.system import run


def get_remotes(verbose: int) -> Tuple[str, str, str]:
    """origin, upstream, tracking"""
    origin = '/'.join(run('git remote get-url origin', stderr=sp.DEVNULL, verbose=verbose).split('/')[-2:])
    upstream = '/'.join(run('git remote get-url upstream', stderr=sp.DEVNULL, verbose=verbose).split('/')[-2:])
    tracking = run('git rev-parse --abbrev-ref --symbolic-full-name @{u}', stderr=sp.DEVNULL, verbose=verbose)
    return origin, upstream, tracking