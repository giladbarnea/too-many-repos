from too_many_repos.singleton import Singleton
from too_many_repos.log import logger
from pathlib import Path
import sys
def get_verbose_level_from_sys_argv()->int:
    for i, arg in enumerate(sys.argv):
        if arg in ('-v', '-vv', '-vvv'):
            level = arg.count('v')
            sys.argv.pop(i)
            return level
        
        # Handle 3 situations:
        # 1) --verbose=2
        # 2) --verbose 2
        # 3) --verbose
        if arg.startswith('--verbose'):
            if '=' in arg:
                # e.g. --verbose=2
                level = int(arg.partition('=')[2])
                sys.argv.pop(i)
                return level
            
            sys.argv.pop(i)
            try:
                level = sys.argv[i]
            except IndexError:
                # e.g. --verbose (no value)
                return 1
            else:
                if level.isdigit():
                    # e.g. --verbose 2
                    level = int(level)
                    
                    # pop 2nd time for arg value
                    sys.argv.pop(i)
                else:
                    # e.g. --verbose --other-arg
                    level = 1
            return level
    return 0


verbose_level = get_verbose_level_from_sys_argv()

class TmrConfig(Singleton):
    verbose: int
    
    def __init__(self, verbose=verbose_level):
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
