from too_many_repos.singleton import Singleton
from too_many_repos.log import logger
from pathlib import Path


class TmrConfig(Singleton):
    verbose: int
    
    def __init__(self, verbose=0):
        super().__init__()
        self.verbose = verbose
        try:
            config_file = Path.home() / '.tmrrc.py'
        except FileNotFoundError as e:
            if self.verbose >= 1:
                logger.warning(f"Did not find {Path.home() / '.tmrrc.py'}")
        else:
            exec(compile(config_file.open().read(), config_file, 'exec'), dict(tmr=self))
            if self.verbose >= 2:
                logger.info(f"[good]Loaded config file successfully: {config_file}[/]")
