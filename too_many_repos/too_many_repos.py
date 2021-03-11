#!/bin/python3.8

import click
from pathlib import Path
import sys
import subprocess as sp
import shlex
import os
from rich.live import Live
from rich.spinner import Spinner
from rich.prompt import Confirm
from rich.console import Console
from rich.theme import Theme
from rich import print
from random import randint
from datetime import timedelta
from datetime import datetime as dt
import re
from typing import Union, List, Set, Tuple
console=Console(theme=Theme({'#':'dim', 'warn':'yellow', 'good':'green', 'prompt':'b bright_magenta'}))
log=console.print
THIS_FILE_STEM = Path(__file__).stem


def is_regexlike(val: str) -> bool:
    """Chars that can't be a file path and used often in regexps"""
    # space because easy to match gist description without \s
    for re_char in ('*', '^', '$', '[', ']', '?', '+', '<', '>', '(', ')', '{', '}', '\\', ' '):
        if re_char in val:
            return True
    return False


def run(cmd: str, *args, **kwargs) -> str:
    if 'stdout' not in kwargs:
        kwargs.update(stdout=sp.PIPE)
    try:
        if kwargs.pop('verbose') is not None:
            log(f'[#]Running[/]: [rgb(125,125,125) i on rgb(25,25,25)]{cmd}[/]')
    except KeyError:
        pass
    stdout = sp.run(shlex.split(cmd), *args, **kwargs).stdout
    if stdout:
        return stdout.strip().decode()
    return ""


def should_skip_path(path: Path, exclude_these: Set[Union[re.Pattern, str]]) -> bool:
    for exclude in exclude_these:
        if isinstance(exclude, re.Pattern):
            if exclude.search(str(path)):
                return True
            continue
        exclude: str
        if '/' in exclude:
            if exclude.startswith('/'):
                # exclude is an absolute path: '/home/gilad'. dir has to equal exactly.
                comparefn = lambda: str(path).startswith(exclude)
            else:
                # exclude is a a few parts, but not an absolute path: 'gilad/dev'. dir has to contain substring.
                comparefn = lambda: exclude in str(path)
        else:
            # exclude is just a name: 'dev'. a part has to equal.
            comparefn = lambda: any(part == exclude for part in path.parts)
        if comparefn():
            return True
        # for part in directory.parts:
        #     if part == exclude:
        # return True
    return False


def should_skip_gist_file(exclude_these: Set[Union[re.Pattern, str]], gist_file: str) -> bool:
    for exclude in exclude_these:
        if isinstance(exclude, re.Pattern):
            if exclude.search(gist_file):
                return True
            continue
        exclude: str
        if gist_file == exclude:
            return True
    return False


def should_skip_gist(exclude_these: Set[Union[re.Pattern, str]], gist_id: str, gist_description: str) -> bool:
    for exclude in exclude_these:
        if isinstance(exclude, re.Pattern):
            if exclude.search(gist_id) or exclude.search(gist_description):
                return True
            continue
        exclude: str
        if gist_id == exclude:
            return True
    return False


def diff_gist(entry, gist_id, id2props, live, verbose, quiet):
    if verbose:
        log(f'[#]diffing {entry}...')
    tmp_stripped_gist_file_path = f'/tmp/{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}'
    gist_content = run(f"gh gist view {gist_id}", verbose=verbose).splitlines()
    gist_description = id2props[gist_id].get('description', '')
    
    stripped_gist_content = list(filter(bool, map(str.strip, gist_content)))
    if gist_description:
        try:
            index_of_gist_description = next(i for i, line in enumerate(stripped_gist_content) if line.strip().startswith(gist_description))
        except StopIteration:
            pass
        else:
            
            stripped_gist_content.pop(index_of_gist_description)
            stripped_gist_content = list(filter(bool, map(str.strip, stripped_gist_content)))
    with open(tmp_stripped_gist_file_path, mode='w') as tmp:
        tmp.write('\n'.join(stripped_gist_content))
    
    entry_lines = list(filter(bool, map(str.strip, entry.absolute().open().readlines())))
    tmp_stripped_file_path = f'/tmp/{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}{randint(0, 10)}'
    with open(tmp_stripped_file_path, mode='w') as tmp:
        tmp.write('\n'.join(entry_lines))
    # if '.git_status_subdirs_ignore' in str(entry):
    #     live.stop()
    #     from IPython import start_ipython
    #     start_ipython(argv=[], user_ns={**locals(), **globals()})
    diff = run(f'diff -ZbwBu --strip-trailing-cr "{tmp_stripped_gist_file_path}" "{tmp_stripped_file_path}"')
    if diff:
        gist_date = id2props[gist_id].get('date')
        prompt = f"[warn][b]{entry.absolute()}[/b]: file and gist {gist_id} ('{gist_description[:32]}') are different"
        try:
            from dateutil.parser import parse as parsedate
        except ModuleNotFoundError as e:
            pass
        else:
            if gist_date.endswith('Z'):
                gist_date = parsedate(gist_date[:-1])
            else:
                gist_date = parsedate(gist_date)
            
            file_mdate = dt.fromtimestamp(entry.stat().st_mtime)
            if file_mdate > gist_date:
                local_is_newer = True
                td: timedelta = file_mdate - gist_date
            else:
                local_is_newer = False
                td: timedelta = gist_date - file_mdate
            
            
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
        log(prompt)
        if quiet:
            log("[prompt]Would've prompted show diff, but quiet=True")
        else:
            live.stop()
            if Confirm.ask('[prompt]show diff?[/]'):
                # don't echo here because shell syntax errors sometimes
                # also don't add diff flags like above, and the overwrite is intentional
                with open(tmp_stripped_gist_file_path, mode='w') as tmp:
                    tmp.write('\n'.join(gist_content))
                os.system(f'diff -ZuB --strip-trailing-cr "{tmp_stripped_gist_file_path}" "{entry.absolute()}" | delta')
            live.start()
    else:
        log(f"[good][b]{entry.absolute()}[/b]: file and gist {gist_id[:16]} ('{gist_description[:32]}') file are identical[/]")


def get_gists_to_check(exclude_these: Set[Union[re.Pattern, str]], verbose: int):
    if verbose:
        log('[#]Getting gists...[/]')
    skip_gist_files = set()
    gists_list = run('gh gist list -L 100', verbose=verbose).splitlines()  # not safe
    gistid2gist_view_proc = dict()
    gistid2gistprop = dict()
    gistfile2gistid = dict()
    # create processes
    for gist_str in gists_list:
        gist_id, description, filecount, perm, date = gist_str.split('\t')
        if should_skip_gist(exclude_these, gist_id, description):
            if verbose:
                log(f"[warn]skipping [b]{gist_id} ('{description[:32]}')[/b]: excluded[/]")
            continue
        gistid2gistprop[gist_id] = dict(description=description, filecount=filecount, perm=perm, date=date)
        if verbose:
            log(f"[#]Getting files of {gist_id[:8]} ('{description[:32]}')...[/]")
        gist_view_proc = sp.Popen(shlex.split(f'gh gist view {gist_id} --files'), stdout=sp.PIPE, stderr=sp.PIPE)
        gistid2gist_view_proc[gist_id] = gist_view_proc
    
    # populate file2id with processes results
    for gist_id in gistid2gist_view_proc:
        gist_view_proc = gistid2gist_view_proc[gist_id]
        gist_props = gistid2gistprop[gist_id]
        gist_files = gist_view_proc.communicate()[0].decode().splitlines()
        for gist_file in gist_files:
            if gist_file in gistfile2gistid:
                # gist_file already existed in file2id (different gists, same file name)
                # if >1 gists have the same file name, we ignore all its gists completely
                # so not only do we not set file2id[gist_file] = id, but we also mark gist_file to be skipped
                description = gist_props.get('description')
                existing_id = gistfile2gistid[gist_file]
                log((f"[warn]skipping [b]{gist_file}: '{gistid2gistprop[existing_id]['description'][:64]}' ({existing_id[:8]})[/b] "
                       f"because same file name: [b]'{description[:64]}' ({gist_id[:8]})[/]"
                       ))
                
                skip_gist_files.add(gist_file)
            elif should_skip_gist_file(exclude_these, gist_file):
                # don't add gist_file to gistfile2gistid
                if verbose:
                    description = gist_props.get('description')
                    log(f"[warn]gist file [b]'{gist_file}'[/b] of {gist_id} ('{description[:32]}'): skipping; excluded[/]")
            else:
                gistfile2gistid[gist_file] = gist_id
    # remove any entries that had duplicates
    for gist_file in skip_gist_files:
        gistfile2gistid.pop(gist_file)
    if verbose >= 2:
        log('file2id: ', gistfile2gistid, 'id2props: ', gistid2gistprop)
    return gistfile2gistid, gistid2gistprop


def get_remotes(verbose: int) -> Tuple[str, str, str]:
    """origin, upstream, tracking"""
    origin = '/'.join(run('git remote get-url origin', stderr=sp.DEVNULL, verbose=verbose if verbose >= 2 else None).split('/')[-2:])
    upstream = '/'.join(run('git remote get-url upstream', stderr=sp.DEVNULL, verbose=verbose if verbose >= 2 else None).split('/')[-2:])
    tracking = run('git rev-parse --abbrev-ref --symbolic-full-name @{u}', stderr=sp.DEVNULL, verbose=verbose if verbose >= 2 else None)
    return origin, upstream, tracking


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
@click.option('-v', '--verbose', count=True, type=int, metavar="VERBOSITY", help="Verbosity level")
@click.option('-h', '--help', is_flag=True)
@click.option('-q', '--quiet', is_flag=True)
@click.option('--gists', 'should_check_gists', is_flag=True, help='Also look for local files that match files in own gists and diff them')
@click.pass_context
def main(ctx, parent_path: Path, glob: str, exclude_these: tuple, gitdir_size_limit: int, verbose: int, help: bool, should_check_gists: bool = False, quiet: bool = False):
    """Runs `git fetch --all --prune --jobs=10; git status` in each subdir of PARENT_PATH that:
    
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
    
    # * merge .tmrignore files, gists_re into exclude_these
    exclude_set = set(exclude_these)
    for root in (Path.home(), parent_path):
        ignorefile = root / f".tmrignore"
        try:
            exclude_set |= set(map(str.strip, ignorefile.open().readlines()))
        except FileNotFoundError as fnfe:
            if verbose >= 2:
                log(f"[warn]FileNotFoundError when handling {ignorefile}: {', '.join((map(str, fnfe.args)))}[/]")
        except Exception as e:
            log(f"[warn]{e.__class__} when handling {ignorefile}: {', '.join((map(str, e.args)))}[/]")
        else:
            if verbose:
                log(f"[good]found {ignorefile}[/]")
    
    exclude_these: Set[Union[re.Pattern, str]] = set()
    for exclude in exclude_set:
        if is_regexlike(exclude):
            exclude_these.add(re.compile(exclude, re.DOTALL))
        else:
            exclude_these.add(exclude)
    
    if verbose:
        log(f"{parent_path = }, {glob = },\n{exclude_these = },\n{gitdir_size_limit = }, {verbose = },\n{should_check_gists = }, {quiet = }", width=120)
    
    # * main loop
    with Live(Spinner('dots9'), refresh_per_second=16) as live:
        # * parse gists
        if should_check_gists:
            gistfile2gistid, gistid2gistprop = get_gists_to_check(exclude_these, verbose)
        
        print()
        
        for entry in parent_path.glob(glob):
            
            if should_skip_path(entry, exclude_these):
                if verbose >= 2:  # keep >=2 because prints for all subdirs of excluded
                    log(f"[warn][b]{entry}[/b]: skipping; excluded[/]")
                continue
            if verbose >= 2:
                log(f'[#]in {entry}...[/]')
            if should_check_gists and (gist_id := gistfile2gistid.get(entry.name)) and entry.is_file():
                diff_gist(entry, gist_id, gistid2gistprop, live, verbose, quiet)
            
            elif entry.is_dir():
                
                directory = entry
                
                # look for .git dir
                gitdir = directory / '.git'
                try:
                    if not gitdir.is_dir():
                        continue
                except PermissionError:
                    if verbose:
                        log(f"[warn][b]{directory}[/b]: skipping; PermissionError[/]")
                    continue
                
                # .git dir size
                gitdir_size_mb = sum(map(lambda p: p.stat().st_size, gitdir.glob('**/*'))) / 1000000
                if gitdir_size_mb >= gitdir_size_limit:
                    if verbose:
                        log(f"[warn][b]{directory}[/b]: skipping; .git dir is {int(gitdir_size_mb)}MB[/]")
                    continue
                
                os.chdir(directory)
                
                # fetch and parse status
                run('git fetch --all --prune --jobs=10', stdout=sp.DEVNULL, stderr=sp.DEVNULL, verbose=verbose if verbose >= 2 else None)
                status = run('git status')
                has_local_modified_files = not status.endswith('nothing to commit, working tree clean')
                if not has_local_modified_files and 'behind' not in status and 'have diverged' not in status:
                    # nothing modified, we're up-to-date.
                    if not verbose:
                        continue
                    msg = f"[good][b]{directory}[/b]: nothing modified, "
                    if 'ahead' in status:
                        # nothing modified, we're up-to-date, but upstream is behind.
                        msg += f"but {status.splitlines()[1]}\n\t"
                    else:
                        msg += "everything up-to-date."
                    origin, upstream, tracking = get_remotes(verbose)
                    if origin:
                        msg += f' [b]origin[/b]: [i]{origin}[/i].'
                    if upstream:
                        # I forked it
                        msg += f' [b]upstream[/b]: [i]{upstream}[/i].'
                    if tracking:
                        msg += f' [b]tracking[/b]: [i]{tracking}[/i]'
                    
                    msg += '[/]'
                    log(msg)
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
                    
                # either something modified, or we're behind/ahead, or mine and upstream diverged
                log(f'\n[b bright_white u]{directory.absolute()}[/]\n')
                os.system(f'git status')
                print()
                
                if has_local_modified_files and 'behind' in status:  # TODO: don't think there needs to be an 'ahead' check here? not sure
                    # something modified and we're behind/ahead. don't want handle stash etc
                    continue
                
                if 'ahead' not in status and ('behind' in status or 'have diverged' in status):  # nothing modified, can be pulled
                    # TODO: is it always true that no local modified files here?
                    if quiet:
                        log("[prompt]Would've prompted git pull, but quiet=True")
                    else:
                        live.stop()
                        
                        if Confirm.ask('[prompt]git pull?[/]'):
                            live.start()
                            log('pulling...')
                            os.system('git pull')
                            print()
                        else:
                            live.start()
                            log('[warn]not pulling[/]')
                
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
