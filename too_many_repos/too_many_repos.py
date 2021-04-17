#!/bin/python3.8
from typing import Optional, List, Dict

import click
from concurrent import futures as fut
from pathlib import Path
import sys
import subprocess as sp
import os
from rich.live import Live
from rich.spinner import Spinner
from rich.prompt import Confirm, IntPrompt

from rich import print
from datetime import timedelta
from datetime import datetime as dt

from too_many_repos import system
from too_many_repos.gist import get_file2gist_map, Gist
from too_many_repos.repo import Repo
from too_many_repos.tmrignore import tmrignore
from too_many_repos.tmrconfig import config
from too_many_repos.log import logger, console

THIS_FILE_STEM = Path(__file__).stem


def diff_gist(entry: Path, gist: Gist, live, quiet):
	logger.debug(f'[#]diffing {entry}...')
	tmp_stripped_gist_file_path = f'/tmp/{gist.id}'
	# gist_content = system.run(f"gh gist view '{gist.id}'", verbose=config.verbose).splitlines()
	# gist_description = id2props[gist.id].get('description', '')

	# stripped_gist_content = list(filter(bool, map(str.strip, gist.content)))
	# if gist.description:
	#     try:
	#         index_of_gist_description = next(i for i, line in enumerate(stripped_gist_content) if line.strip().startswith(gist.description))
	#     except StopIteration:
	#         pass
	#     else:
	#
	#         stripped_gist_content.pop(index_of_gist_description)
	#         stripped_gist_content = list(filter(bool, map(str.strip, stripped_gist_content)))
	with open(tmp_stripped_gist_file_path, mode='w') as tmp:
		tmp.write(gist.content)

	entry_lines = list(filter(bool, map(str.strip, entry.absolute().open().readlines())))
	tmp_stripped_file_path = f'/tmp/{entry.name}.gist{entry.suffix}'
	with open(tmp_stripped_file_path, mode='w') as tmp:
		tmp.write('\n'.join(entry_lines))
	# if '.git_status_subdirs_ignore' in str(entry):
	#     live.stop()
	diff = system.run(f'diff -ZbwBu --strip-trailing-cr --suppress-blank-empty "{tmp_stripped_gist_file_path}" "{tmp_stripped_file_path}"')
	if diff:
		# gist_date = id2props[gist_id].get('date')
		prompt = f"[warn][b]{entry.absolute()}[/b]: file and gist {gist.id} ('{gist.description[:32]}') are different"
		try:
			# noinspection PyUnresolvedReferences
			from dateutil.parser import parse as parsedate
		except ModuleNotFoundError:
			pass
		else:
			if gist.date.endswith('Z'):
				gist.date = parsedate(gist.date[:-1])
			else:
				gist.date = parsedate(gist.date)

			file_mdate = dt.fromtimestamp(entry.stat().st_mtime)
			if file_mdate > gist.date:
				local_is_newer = True
				td: timedelta = file_mdate - gist.date
			else:
				local_is_newer = False
				td: timedelta = gist.date - file_mdate

			if td.seconds > 5:
				if td.days:
					time_diff = f'{td.days} days'
				elif td.seconds >= 3600:
					time_diff = f'{td.seconds // 3600} hours and {(td.seconds % 3600) // 60} minutes'
				elif td.seconds >= 60:
					time_diff = f'{(td.seconds % 3600) // 60} minutes and {td.seconds} seconds'
				else:
					time_diff = f'{td.seconds} seconds'

				prompt += f"; [b]{'local' if local_is_newer else 'gist'}[/b] is newer by {time_diff}[/]"
			else:
				prompt += f"(less than 5 seconds apart)[/]"
		logger.info(prompt)
		if quiet:
			logger.info("[prompt]Would've prompted show diff, but quiet=True")
		else:
			live.stop()
			if Confirm.ask('[prompt]show diff?[/]'):
				# don't echo here because shell syntax errors sometimes
				# also don't add diff flags like above, and the overwrite is intentional
				with open(tmp_stripped_gist_file_path, mode='w') as tmp:
					tmp.write(gist.content)
				os.system(f'diff -ZuB --strip-trailing-cr "{tmp_stripped_gist_file_path}" "{entry.absolute()}" | delta')
			live.start()
	else:
		logger.info(f"[good][b]{entry.absolute()}[/b]: file and gist {gist.id[:16]} ('{gist.description[:32]}') file are identical[/]")



def get_matching_gist(file_name: str, matching_gists: List[Gist]) -> Gist:
	if len(matching_gists) == 1:
		gist = matching_gists[0]
	else:
		prompt = f"[i]{file_name}[/i] | What gist?\n"
		for i, gist in enumerate(matching_gists, start=1):
			prompt += f"[{i}] {gist}\n"
		gist_idx = IntPrompt.ask(prompt, choices=list(map(str, range(1, len(matching_gists) + 1))), console=console)
		gist = matching_gists[gist_idx - 1]
	return gist


def get_direct_subdirs(path:Path)->List[Path]:
	direct_subdirs = []
	for subdir in path.glob('*'):
		if not subdir.is_dir():
			continue
		if tmrignore.is_ignored(subdir):
			if config.verbose >= 2:  # keep >=2 because prints for all subdirs of excluded
				logger.warning(f"[b]{subdir}[/b]: skipping; excluded")
		direct_subdirs.append(subdir)
	return direct_subdirs

def diff_recursively_with_gists(path: Path, file2gist:Dict[str, List[Gist]]):
	# TODO: this is where the planned "--maxdepth" opt will take effect
	for file in filter(Path.is_file, path.glob('**/*')):
		# Skip if ignored
		if tmrignore.is_ignored(file):
			if config.verbose >= 2:  # keep >=2 because prints for all subdirs of excluded
				logger.warning(f"[b]{file}[/b]: skipping; excluded")
			continue
		matching_gists = file2gist.get(file.name)
		if not matching_gists:
			continue
		matching_gist = get_matching_gist(file.name, matching_gists)
		matching_gist.diff(file)

@click.command(context_settings=dict(show_default=True))
@click.argument('parent_path', required=False, default=Path.cwd(),
				type=click.Path(exists=True, dir_okay=True, readable=True))
@click.option('-g', '--glob', metavar='GLOB',
			  required=False, default='*',
			  help='Script iterates PARENT_PATH.glob(GLOB)')
@click.option('-e', '--exclude', 'exclude_these', metavar='STRING_OR_ADV_REGEX',
			  required=False, type=str, multiple=True,
			  help='\n'.join(('\b',
							  'Filters directories and gists.',
							  'To exclude dirs:',
							  'Can be bare ("myprojects"), which skips a dir if any of its parts match; ',
							  'Composed ("myprojects/myrepo"), which skips a dir if a substring matches; ',
							  'Absolute ("/home/myself/myprojects"), which skips a a dir if it startswith.',
							  'To exclude gists, a full gist id or a file name can be specified.',
							  'To exclude directories or gists with regex:',
							  "`re.search` is used against the gist id, description and file names, and against the dir's abs path.",)
							 ))
@click.option('--gitdir-size-limit', required=False, default=100, metavar='SIZE_MB',
			  help='A dir is skipped if its .git dir size >= SIZE_MB')
@click.option('-h', '--help', is_flag=True)
@click.option('-q', '--quiet', is_flag=True)
@click.option('--gists', 'should_check_gists', is_flag=True, help='Look for local files that match files in own gists and diff them')
@click.option('--repos/--no-repos', 'should_check_repos', default=True)
@click.pass_context
def main(ctx,
		 parent_path: Path,
		 glob: str,
		 exclude_these: tuple,
		 gitdir_size_limit: int,
		 help: bool,
		 should_check_gists: bool = False,
		 should_check_repos: bool = True,
		 quiet: bool = False):
	"""
	Runs `git fetch --all --prune --jobs=10; git status` in each subdir of PARENT_PATH that:

	\b
	1. is a git repo;
	2. '.git' dir is less than SIZE_MB;
	3. is not excluded due to EXCLUDE args.

	\b
	Without args, iterates subdirs / repos in PWD with depth of 1.
	Examples:

	\b
	git_status_subdirs.py
	git_status_subdirs.py $HOME -g '**/*' -e dev -vv
	"""
	# TODO: practice asyncio or threads when git fetching simult
	# TODO: if upstream exists, always show it in green

	parent_path = Path(parent_path).absolute()
	if help:
		usage(ctx, parent_path)
		sys.exit()
	tmrignore.update(*exclude_these)
	tmrignore.update_from_file(parent_path)

	logger.debug((f"{parent_path = }, {glob = },\n"
				  f"{gitdir_size_limit = }, {config.verbose = },\n"
				  f"{should_check_gists = },\n"
				  f"{should_check_repos = },\n"
				  f"{quiet = }"))
	print('\n[b]Excluding:[/]')
	print(tmrignore)

	# ** main loop
	with Live(Spinner('dots9'), refresh_per_second=16) as live:
		live.stop()
		repos: List[Repo] = []
		# * parse gists
		if should_check_gists:
			file2gist = get_file2gist_map()
			logger.debug(f'[#]Got {len(file2gist)} gists[/]')

		print()


		direct_subdirs = get_direct_subdirs(parent_path)
		if should_check_gists:
			logger.debug(f'[#]Diffing gists recursively in {len(direct_subdirs)} threads...[/]')
			with fut.ThreadPoolExecutor(max_workers=len(direct_subdirs)) as xtr:
				for subdir in direct_subdirs:
					xtr.submit(diff_recursively_with_gists,subdir,file2gist)

		if not should_check_repos:
			return

		for repo in filter(Repo.is_repo, map(Repo, parent_path.glob(glob))):

			# * Repo
			# Skip if .git dir size is too big
			if repo.is_gitdir_too_big():
				logger.warning(f"[b]{repo.path}[/b]: skipping; .git dir size is above {config.gitdir_size_limit_mb}MB")
				continue

			repos.append(repo)

		logger.debug(f'[#]Fetching {len(repos)} repos in {len(repos)} threads...[/]')
		with fut.ThreadPoolExecutor(max_workers=len(repos)) as xtr:
			xtr.submit(repo.fetch)
			xtr.submit(repo.popuplate_status)


			# os.chdir(repo.path)
			# logger.debug(f'\n[b bright_white u]{repo.path.absolute()}[/]\n')
			# # * fetch and parse status
			# system.run('git fetch --all --prune --jobs=10', stdout=sp.DEVNULL, stderr=sp.DEVNULL, verbose=config.verbose if config.verbose >= 2 else None)
			# status = system.run('git status')
		for repo in repos:
			has_local_modified_files = not repo.status.endswith('nothing to commit, working tree clean')
			if not has_local_modified_files and 'behind' not in repo.status and 'have diverged' not in repo.status:
				# nothing modified,
				msg = f"[good][b]{repo.path}[/b]: nothing modified, "
				if 'ahead' in repo.status:
					# nothing modified, but upstream is behind.
					msg += f"but {repo.status.splitlines()[1]}\n\t"
				else:
					# nothing modified, everything up-to-date.
					msg += "everything up-to-date."

				repo.popuplate_remotes()
				remotes = repo.remotes

				if remotes.origin:
					msg += f' [b]origin[/b]: [i]{remotes.origin}[/i].'
				if remotes.upstream:
					# I forked it
					msg += f' [b]upstream[/b]: [i]{remotes.upstream}[/i].'
				if remotes.tracking:
					msg += f' [b]tracking[/b]: [i]{remotes.tracking}[/i]'

				msg += '[/]'
				logger.info(msg)
				# if 'ahead' in status:
				#     # TODO: in this case there's nothing to push; origin is up to date, upstream isn't
				#     live.stop()
				#     currentbranch = run('git rev-parse --abbrev-ref HEAD')
				#     if Confirm.ask(f'[b bright_magenta]git push origin {currentbranch}?[/]'):
				#         live.start()
				#         print('pushing...')
				#         os.system(f'git push origin {currentbranch}')
				#         print()
				#     else:
				#         live.start()
				#         print('[warn]not pushing[/]')
				continue

			# * Either something modified, or we're behind/ahead, or mine and upstream diverged

			# Just to display in terminal
			os.chdir(repo.path)
			os.system(f'git status')
			print()

			if has_local_modified_files and 'behind' in repo.status:  # TODO: don't think there needs to be an 'ahead' check here? not sure
				# something modified and we're behind/ahead. don't want handle stash etc
				logger.info(f'[b]{repo.path}[/b]: has local modifications, and is behind')
				continue

			# nothing modified, can be pulled
			if 'ahead' not in repo.status and ('behind' in repo.status or 'have diverged' in repo.status):
				# TODO: is it always true that no local modified files here?
				if quiet:
					logger.info("[prompt]Would've prompted git pull, but quiet=True")
				else:
					live.stop()

					if Confirm.ask('[prompt]git pull?[/]'):
						# live.start()
						logger.info('pulling...')
						os.system('git pull')
						print()
					else:
						# live.start()
						logger.warning('not pulling')

			# * end of main loop
			os.chdir(parent_path)



def usage(ctx, parent_path):
	helpstr = main.get_help(ctx)
	helpstr += f"""\n\n.tmrignore Files:
    Honors .tmrignore files in {parent_path} and {Path.home()} (if exist).
    Each line is processed as if passed via EXCLUDE option.
    """

	from rich import inspect
	main.callback.__doc__ = helpstr
	inspect(main.callback, docs=True, help=True, title=f'{THIS_FILE_STEM}.py main(...)')


if __name__ == '__main__':
	main()
