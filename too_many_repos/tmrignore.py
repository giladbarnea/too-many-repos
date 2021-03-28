from typing import Iterable, TypeVar, Set, Union
import re
from pathlib import Path
from too_many_repos.log import logger
from too_many_repos.singleton import Singleton


class TmrIgnore(Set[Union[re.Pattern, str]], Singleton):
    
    def add_to_ignored(self, ignorefile: Path):
        entries = set()
        try:
            entries |= set(map(str.strip, ignorefile.open().readlines()))
        except FileNotFoundError as fnfe:
            if verbose >= 2:
                log(f"[warn]FileNotFoundError when handling {ignorefile}: {', '.join((map(str, fnfe.args)))}[/]")
        except Exception as e:
            log(f"[warn]{e.__class__} when handling {ignorefile}: {', '.join((map(str, e.args)))}[/]")
        else:
            if verbose:
                log(f"[good]found {ignorefile}[/]")
        
        exclude_these: TmrIgnore = set()
        for exclude in entries:
            if is_regexlike(exclude):
                exclude_these.add(re.compile(exclude, re.DOTALL))
            else:
                exclude_these.add(exclude)