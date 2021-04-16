#!/bin/python3.8

import click
import pickle
from pathlib import Path
import sys
import subprocess as sp
import shlex
import os
from rich.live import Live
from rich.spinner import Spinner
from rich.prompt import Confirm, IntPrompt

from rich import print
from random import randint
from datetime import timedelta
from datetime import datetime as dt
import re

from too_many_repos import repo, system
from too_many_repos.gist import get_file2gist_map, Gist
from too_many_repos.tmrignore import tmrignore
from too_many_repos.tmrconfig import config
from too_many_repos.log import logger, console

THIS_FILE_STEM = Path(__file__).stem


def should_skip_gist_file(gist_file: str) -> bool:
    for exclude in tmrignore:
        if isinstance(exclude, re.Pattern):
            if exclude.search(gist_file):
                return True
            continue
        exclude: str
        if gist_file == exclude:
            return True
    return False


def should_skip_gist(gist_id: str, gist_description: str) -> bool:
    for exclude in tmrignore:
        if isinstance(exclude, re.Pattern):
            if exclude.search(gist_id) or exclude.search(gist_description):
                return True
            continue
        exclude: str
        if gist_id == exclude:
            return True
    return False


def diff_gist(entry:Path, gist: Gist, live, quiet):
    if config.verbose:
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


# def get_gists_to_check():
#     if config.verbose:
#         logger.debug('[#]Getting gists...[/]')
#     skip_gist_files = set()
#     gists_list = system.run('gh gist list -L 100', verbose=config.verbose).splitlines()  # not safe
#     gistid2gist_view_proc = dict()
#     gistid2gistprop = dict()
#     gistfile2gistid = dict()
#     # create processes
#     for gist_str in gists_list:
#         gist_id, description, filecount, perm, date = gist_str.split('\t')
#         if should_skip_gist(gist_id, description):
#             if config.verbose:
#                 logger.warning(f"skipping [b]{gist_id} ('{description[:32]}')[/b]: excluded")
#             continue
#         gistid2gistprop[gist_id] = dict(description=description, filecount=filecount, perm=perm, date=date)
#         if config.verbose:
#             logger.debug(f"[#]Getting files of {gist_id[:8]} ('{description[:32]}')...[/]")
#         gist_view_proc = sp.Popen(shlex.split(f'gh gist view "{gist_id}" --files'), stdout=sp.PIPE, stderr=sp.PIPE)
#         gistid2gist_view_proc[gist_id] = gist_view_proc
#
#     # populate file2id with processes results
#     for gist_id in gistid2gist_view_proc:
#         gist_view_proc = gistid2gist_view_proc[gist_id]
#         gist_props = gistid2gistprop[gist_id]
#         gist_files = gist_view_proc.communicate()[0].decode().splitlines()
#         for gist_file in gist_files:
#             if gist_file in gistfile2gistid:
#                 # gist_file already existed in file2id (different gists, same file name)
#                 # if >1 gists have the same file name, we ignore all its gists completely
#                 # so not only do we not set file2id[gist_file] = id, but we also mark gist_file to be skipped
#                 description = gist_props.get('description')
#                 existing_id = gistfile2gistid[gist_file]
#                 logger.warning((f"skipping [b]{gist_file}: '{gistid2gistprop[existing_id]['description'][:64]}' ({existing_id[:8]})[/b] "
#                        f"because same file name: [b]'{description[:64]}' ({gist_id[:8]})[/]"
#                        ))
#
#                 skip_gist_files.add(gist_file)
#             elif should_skip_gist_file(gist_file):
#                 # don't add gist_file to gistfile2gistid
#                 if config.verbose:
#                     description = gist_props.get('description')
#                     logger.warning(f"gist file [b]'{gist_file}'[/b] of {gist_id} ('{description[:32]}'): skipping; excluded")
#             else:
#                 gistfile2gistid[gist_file] = gist_id
#     # remove any entries that had duplicates
#     for gist_file in skip_gist_files:
#         gistfile2gistid.pop(gist_file)
#     if config.verbose >= 2:
#         logger.debug('file2id: ', gistfile2gistid, 'id2props: ', gistid2gistprop)
#     return gistfile2gistid, gistid2gistprop


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

    if config.verbose:
        logger.debug(f"{parent_path = }, {glob = },\n{gitdir_size_limit = }, {config.verbose = },\n{should_check_gists = },\n{should_check_repos = },\n{quiet = }")
        print('\n[b]Excluding:[/]')
        print(tmrignore)

    # ** main loop
    with Live(Spinner('dots9'), refresh_per_second=16) as live:
        live.stop()
        # * parse gists
        if should_check_gists:
            file2gist = get_file2gist_map()
            with open('/tmp/file2gist.pickle', mode='w+b') as file2gist_pickle:
                pickle.dump(file2gist, file2gist_pickle)
            # with open('/tmp/file2gist.pickle', mode='r+b') as file2gist_pickle:
            #     file2gist = pickle.load(file2gist_pickle)
            if config.verbose:
                logger.debug(f'[#]Got {len(file2gist)} gists[/]')
            # gistfile2gistid, gistid2gistprop = get_gists_to_check()
        
        print()
        
        for entry in parent_path.glob(glob):

            # Skip if ignored
            if tmrignore.is_ignored(entry):
                if config.verbose >= 2:  # keep >=2 because prints for all subdirs of excluded
                    logger.warning(f"[b]{entry}[/b]: skipping; excluded")
                continue

            if config.verbose >= 2:
                logger.debug(f'[#]in {entry}...[/]')

            # Diff against gist
            # if should_check_gists and (gist_id := gistfile2gistid.get(entry.name)) and entry.is_file():
            if should_check_gists and (matching_gists:= file2gist.get(entry.name)) and entry.is_file():
                if len(matching_gists) == 1:
                    gist = matching_gists[0]
                    # gist_file = gist.files.get(entry.name)
                else:
                    prompt = f"[i]{entry.name}[/i] | What gist?\n"
                    for i, gist in enumerate(matching_gists, start=1):
                        prompt+=f"[{i}] {gist}\n"
                    gist_idx = IntPrompt.ask(prompt, choices=list(map(str, range(1, len(matching_gists)+1))),console=console)
                    gist = matching_gists[gist_idx-1]
                    # gist_file = gist.files.get(entry.name)
                # diff_gist(entry, gist, live, quiet)
                gist.diff(entry)

            elif entry.is_dir() and should_check_repos:
                
                directory = entry
                
                # look for .git dir
                gitdir = directory / '.git'
                try:
                    if not gitdir.is_dir():
                        continue
                except PermissionError:
                    if config.verbose:
                        logger.warning(f"[b]{directory}[/b]: skipping; PermissionError[/]")
                    continue
                
                # Skip if .git dir size is too big
                gitdir_size_mb = sum(map(lambda p: p.stat().st_size, gitdir.glob('**/*'))) / 1000000
                if gitdir_size_mb >= gitdir_size_limit:
                    if config.verbose:
                        logger.warning(f"[b]{directory}[/b]: skipping; .git dir is {int(gitdir_size_mb)}MB")
                    continue
                
                os.chdir(directory)
                
                # * fetch and parse status
                system.run('git fetch --all --prune --jobs=10', stdout=sp.DEVNULL, stderr=sp.DEVNULL, verbose=config.verbose if config.verbose >= 2 else None)
                status = system.run('git status')
                has_local_modified_files = not status.endswith('nothing to commit, working tree clean')
                if not has_local_modified_files and 'behind' not in status and 'have diverged' not in status:
                    # nothing modified, we're up-to-date.
                    if not config.verbose:
                        continue
                    msg = f"[good][b]{directory}[/b]: nothing modified, "
                    if 'ahead' in status:
                        # nothing modified, we're up-to-date, but upstream is behind.
                        msg += f"but {status.splitlines()[1]}\n\t"
                    else:
                        msg += "everything up-to-date."
                    origin, upstream, tracking = repo.get_remotes(config.verbose if config.verbose >= 2 else None)
                    if origin:
                        msg += f' [b]origin[/b]: [i]{origin}[/i].'
                    if upstream:
                        # I forked it
                        msg += f' [b]upstream[/b]: [i]{upstream}[/i].'
                    if tracking:
                        msg += f' [b]tracking[/b]: [i]{tracking}[/i]'
                    
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
                logger.log(10, f'\n[b bright_white u]{directory.absolute()}[/]\n')
                os.system(f'git status')
                print()
                
                if has_local_modified_files and 'behind' in status:  # TODO: don't think there needs to be an 'ahead' check here? not sure
                    # something modified and we're behind/ahead. don't want handle stash etc
                    continue

                # nothing modified, can be pulled
                if 'ahead' not in status and ('behind' in status or 'have diverged' in status):
                    # TODO: is it always true that no local modified files here?
                    if quiet:
                        logger.info("[prompt]Would've prompted git pull, but quiet=True")
                    else:
                        live.stop()
                        
                        if Confirm.ask('[prompt]git pull?[/]'):
                            live.start()
                            logger.info('pulling...')
                            os.system('git pull')
                            print()
                        else:
                            live.start()
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
