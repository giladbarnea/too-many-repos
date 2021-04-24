from pathlib import Path

from too_many_repos.log import logger


def exec_file(file: Path, _globals):
	try:
		exec(compile(file.open().read(), file, 'exec'), _globals)
	except FileNotFoundError as e:
		logger.warning(f"exec_file: Did not find {file}")
	else:
		logger.debug(f"[good]Loaded config file successfully: {file}[/]")
