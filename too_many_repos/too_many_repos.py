#!/bin/python3.8
import os
import re
import sys
from collections import defaultdict
from concurrent import futures as fut
from datetime import datetime as dt
from datetime import timedelta
from multiprocessing import Pool as ProcPool
from pathlib import Path
from typing import Dict, List, Optional

import click
from rich import print
from rich.prompt import Confirm, Prompt

from too_many_repos import system
from too_many_repos.gist import Gist, GistFile, build_filename2gistfiles_parallel
from too_many_repos.log import logger
from too_many_repos.repo import Repo, is_repo
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore
from too_many_repos.util import safe_glob, safe_is_dir, safe_is_file, unrequired_opt

THIS_FILE_STEM = Path(__file__).stem


# noinspection PyUnresolvedReferences,PyTypeChecker
def diff_gist(entry: Path, gist: Gist, live, quiet):
    logger.debug(f"diffing {entry}...")
    tmp_stripped_gist_file_path = f"/tmp/{gist.id}"
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
    with open(tmp_stripped_gist_file_path, mode="w") as tmp:
        tmp.write(gist.content)

    entry_lines = list(
        filter(bool, map(str.strip, entry.absolute().open().readlines()))
    )
    tmp_stripped_file_path = f"/tmp/{entry.name}.gist{entry.suffix}"
    with open(tmp_stripped_file_path, mode="w") as tmp:
        tmp.write("\n".join(entry_lines))
    # if '.git_status_subdirs_ignore' in str(entry):
    #     live.stop()
    same = system.diff_quiet(
        f'"{tmp_stripped_gist_file_path}" "{tmp_stripped_file_path}"'
    )
    if not same:
        # gist_date = id2props[gist_id].get('date')
        prompt = f"[b]{entry.absolute()}[/b]: file and gist {gist.id} ('{gist.description[:32]}') are different"
        try:
            # noinspection PyUnresolvedReferences
            from dateutil.parser import parse as parsedate
        except ModuleNotFoundError:
            pass
        else:
            if gist.date.endswith("Z"):
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
                    time_diff = f"{td.days} days"
                elif td.seconds >= 3600:
                    time_diff = f"{td.seconds // 3600} hours and {(td.seconds % 3600) // 60} minutes"
                elif td.seconds >= 60:
                    time_diff = (
                        f"{(td.seconds % 3600) // 60} minutes and {td.seconds} seconds"
                    )
                else:
                    time_diff = f"{td.seconds} seconds"

                prompt += f"; [b]{'local' if local_is_newer else 'gist'}[/b] is newer by {time_diff}"
            else:
                prompt += "(less than 5 seconds apart)"
        logger.info(prompt)
        if quiet:
            logger.info("[prompt]Would've prompted show diff, but quiet=True")
        else:
            live.stop()
            if Confirm.ask("[prompt]Show diff?[/]"):
                # don't echo here because shell syntax errors sometimes
                # also don't add diff flags like above, and the overwrite is intentional
                with open(tmp_stripped_gist_file_path, mode="w") as tmp:
                    tmp.write(gist.content)
                # os.system(f'diff -ZuB --strip-trailing-cr "{tmp_stripped_gist_file_path}" "{entry.absolute()}" | delta')
                # os.system(f'diff --ignore-trailing-space -u --quiet --strip-trailing-cr "{tmp_stripped_gist_file_path}" "{entry.absolute()}" | delta')
                system.diff_interactive(
                    f'"{tmp_stripped_gist_file_path}" "{entry.absolute()}" | delta'
                )

            live.start()
    else:
        logger.good(
            f"[b]{entry.absolute()}[/b]: file and gist {gist.id[:16]} ('{gist.description[:32]}') file are identical"
        )


def reduce_to_single_gist_by_filename(
    file: Path, matching_gists: List[Gist]
) -> Optional[Gist]:
    if len(matching_gists) == 1:
        gist = matching_gists[0]
    else:
        prompt = f"[i]{file.absolute()}[/i] | What gist?\n"
        for i, gist in enumerate(matching_gists, start=1):
            prompt += f"{i}] {gist}\n"
        prompt += "s] skip\n"
        answer = Prompt.ask(
            prompt, choices=list(map(str, range(1, len(matching_gists) + 1))) + ["s"]
        )
        if answer == "s":
            return None
        gist = matching_gists[int(answer) - 1]
    return gist


def get_direct_subdirs(path: Path) -> List[Path]:
    direct_subdirs = []
    if tmrignore.is_ignored(path.absolute()):
        if config.verbose >= 2:
            logger.warning(f"Main | [b]{path}[/b]: skipping; excluded")
        return direct_subdirs
    for subdir in filter(Path.is_dir, path.glob("*")):
        if tmrignore.is_ignored(subdir.absolute()):
            if (
                config.verbose >= 2
            ):  # keep >=2 because prints for all subdirs of excluded
                logger.warning(f"Main | [b]{subdir}[/b]: skipping; excluded")
            continue
        direct_subdirs.append(subdir)
    return direct_subdirs


def diff_recursively_with_gists(
    path: Path, filename2gistfiles: Dict[str, List[GistFile]], *, max_depth
) -> Dict[Path, List[GistFile]]:
    """
    Goes over files inside path and diffs them against any matching gist.

    Called in a multiprocess context.
    """
    if tmrignore.is_ignored(path.absolute()):
        config.verbose >= 2 and logger.warning(
            f"Main | [b]{path}[/b]: skipping; excluded"
        )
        return defaultdict(list)
    need_user: Dict[Path, List[GistFile]] = defaultdict(list)
    if safe_is_file(path):
        file = path
        config.verbose >= 3 and logger.debug(
            f"Main | Checking if there a matching gist to {file}..."
        )
        gistfiles = filename2gistfiles.get(file.name)
        if not gistfiles:
            return defaultdict(list)
        if len(gistfiles) > 1:
            need_user[file].extend(gistfiles)
            return defaultdict(list)
        gistfile = gistfiles[0]
        gistfile.diff(file)
    if max_depth == 0:
        config.verbose >= 2 and logger.debug(f"Main | Reached {max_depth = } in {path}")
        return defaultdict(list)
    config.verbose >= 3 and logger.debug(
        f"Main | Looking for gists to diff inside {path}..."
    )

    if safe_is_dir(path):
        for subpath in path.glob("*"):
            update = diff_recursively_with_gists(
                subpath, filename2gistfiles, max_depth=max_depth - 1
            )
            if update:
                need_user.update(update)
    return need_user


def populate_repos_recursively(path: Path, repos: List[Repo], *, max_depth) -> None:
    config.verbose >= 3 and logger.debug(f"Main | Populating repos inside {path}...")

    if safe_is_file(path):
        config.verbose >= 3 and logger.debug(f"Main | {path} is a file")
        return

    if tmrignore.is_ignored(path.absolute()):
        config.verbose >= 2 and logger.warning(
            f"Main | [b]{path}[/b]: skipping; excluded"
        )
        return

    if is_repo(path):
        repo = Repo(path)

        if repo.is_gitdir_too_big():
            logger.warning(
                f"Main | [b]{repo.path}[/b]: skipping; .git dir size is above {config.gitdir_size_limit_mb}MB"
            )
        else:
            repos.append(repo)
    if max_depth == 0:
        config.verbose >= 3 and logger.debug(f"Main | Reached {max_depth = } in {path}")
        return
    for subpath in safe_glob(path, "*"):
        populate_repos_recursively(subpath, repos, max_depth=max_depth - 1)


# matching_gist = reduce_to_single_gist_by_filename(file, gistfiles)
# if not matching_gist:
# 	continue
# matching_gist.diff(file)
# from pdbpp import break_on_exc


@click.command()
@click.argument(
    "parent_path",
    required=False,
    default=Path.cwd(),
    type=click.Path(exists=True, dir_okay=True, readable=True),
)
@unrequired_opt(
    "-e",
    "--exclude",
    "exclude_these",
    metavar="STRING_OR_ADV_REGEX",
    multiple=True,
    type=str,
    help="\n".join(
        [
            "\b",
            "Filters out directories and gists.",
            "[b]Excluding PATHS by specifying:[/b]",
            '- Can be bare ("myprojects"), which skips a dir if any of its parts match; ',
            '- Composed ("myprojects/myrepo"), which skips a dir if a substring matches; ',
            '- Absolute ("/home/myself/myprojects"), which skips a a dir if it startswith.',
            "[b]Excluding GISTS by specifying:[/b]",
            "- File name (will not ignore other files in same gist)",
            "- Gist id",
            "- Gist description (or part of it)",
            "To exclude directories or gists with REGEX:",
            "See [b]Ignore and configuration files section[/b] for examples.",
        ]
    ),
)
@unrequired_opt("-q", "--quiet", is_flag=True)
@unrequired_opt(
    "--gists",
    "should_check_gists",
    is_flag=True,
    help="Look for local files that match files in own gists and diff them",
)
@unrequired_opt(
    "--repos/--no-repos",
    "should_check_repos",
    default=True,
    help="Don't do any work with git repositories",
)
@unrequired_opt("--no-fetch", is_flag=True, help="Don't fetch before working on a repo")
@click.option("-h", "--help", is_flag=True, help="Show this message and exit.")
@click.pass_context
# @break_on_exc(ValueError)
def main(
    ctx,
    parent_path: Path,
    exclude_these: tuple,
    should_check_gists: bool = False,
    should_check_repos: bool = True,
    quiet: bool = False,
    no_fetch: bool = False,
    help: bool = False,
):
    """
    Fetches, gets remotes, and parses output of `git status` in each subdir of PARENT_PATH that:

    \b
    1. is a git repo;
    2. '.git' dir is less than SIZE_MB;
    3. is not excluded due to EXCLUDE args.

    \b
    Without args, iterates subdirs / repos in PWD with depth of 1.
    Examples:

    \b
    `git_status_subdirs.py`
    `git_status_subdirs.py $HOME -g '**/*' -e dev -vv`
    """
    parent_path = Path(parent_path).absolute()
    if help:
        usage(ctx, parent_path)
        sys.exit()
    tmrignore.update(*exclude_these)
    tmrignore.update_from_file(parent_path / ".tmrignore")

    logger.debug(
        (
            f"{parent_path = },\n"
            f"{should_check_gists = },\n"
            f"{should_check_repos = },\n"
            f"{quiet = }"
        )
    )
    print("\n[b]Excluding:[/]")
    print(tmrignore.table())
    print("\n[b]Configuration:[/]")
    print(config)
    if not Confirm.ask("Continue?", default=False):
        return
    # *** main loop

    # ** gists
    if should_check_gists:
        # * get gists
        filename2gistfiles = build_filename2gistfiles_parallel()
        logger.info(f"\nMain | Built {len(filename2gistfiles)} gists\n")

        # * populate gist.files
        direct_subdirs = get_direct_subdirs(parent_path)
        max_workers = (
            min(
                (direct_subdirs_len := len(direct_subdirs)),
                config.max_workers or direct_subdirs_len,
            )
            or 1
        )
        max_workers: int = min(max_workers, 32)
        logger.info(f"\nMain | Diffing gists recursively in {max_workers} threads...")
        need_user: Dict[Path, List[GistFile]] = defaultdict(list)
        futures: Dict[Path, fut.Future] = {}
        with fut.ThreadPoolExecutor(max_workers) as xtr:
            for subdir in direct_subdirs:
                future = xtr.submit(
                    diff_recursively_with_gists,
                    subdir,
                    filename2gistfiles,
                    max_depth=config.max_depth,
                )
                futures[subdir] = future

        for subdir, future in futures.items():
            current_need_user = future.result()
            current_need_user and logger.debug(
                f"Got {len(current_need_user)} paths that need user from {subdir}"
            )
            need_user.update(current_need_user)
        current_need_user = diff_recursively_with_gists(
            parent_path, filename2gistfiles, max_depth=1
        )
        current_need_user and logger.debug(
            f"Main | Got {len(current_need_user)} paths that need user from {parent_path}"
        )
        need_user.update(current_need_user)
        logger.debug(f"Main | In total, {len(need_user)} paths need user")

        for filename, gistfiles in filename2gistfiles.items():
            for gistfile in gistfiles:
                for path, difference in gistfile.diffs.items():
                    if difference:
                        logger.info(
                            f"[b]Diff '{path.absolute()}'[/b] and [b]{gistfile.gist.short()}[/b] are [b yellow]different in {difference}[/]"
                        )
                        if Confirm.ask("Show diff?"):
                            # Break down e.g `code --disable-extensions --diff` to `"code" --disable-extensions --diff`
                            difftool, *difftool_args = config.difftool.split()
                            if re.match(r"^(meld|code|pycharm)", config.difftool):
                                os.system(
                                    f'nohup "{difftool}" {" ".join(difftool_args)} "{path}" "{gistfile.gist_file_temp_path}" 2>1 1>/dev/null &'
                                )
                            else:
                                os.system(
                                    f'"{difftool}" {" ".join(difftool_args)} "{path}" "{gistfile.gist_file_temp_path}"'
                                )
                    else:
                        logger.info(
                            f"[b]Diff '{path.absolute()}'[/b] and [b]{gistfile.gist.short()}[/b] are [b green]identical[/]"
                        )

    # if need_user:
    # 	breakpoint()

    # ** repos
    if not should_check_repos:
        return

    repos: List[Repo] = []
    # * populate repos list
    populate_repos_recursively(parent_path, repos, max_depth=config.max_depth)
    if not repos:
        logger.warning("No repos found!")
        return

    # * fetch
    max_workers = min((repos_len := len(repos)), config.max_workers or repos_len)
    max_workers: int = min(max_workers, 32)
    if not no_fetch:
        logger.info(f"Main | Fetching {len(repos)} repos in {max_workers} processes...")
        with ProcPool(max_workers) as pool:
            pool.map(Repo.fetch, repos)

    # * status
    logger.info(f"Main | Git status {len(repos)} repos serially...")
    for repo in repos:
        repo.popuplate_status()

    logger.info("Main | Done fetching and git statusing")

    for repo in repos:
        has_local_modified_files = not repo.status.endswith(
            "nothing to commit, working tree clean"
        )
        remotes = repo.remotes
        if (
            not has_local_modified_files
            and "behind" not in repo.status
            and "have diverged" not in repo.status
        ):
            # * Non-actionable; print current state and continue to next repo (no prompts)
            # nothing modified,
            msg = f"[b]{repo.path}[/b]: nothing modified, "
            if "ahead" in repo.status:
                # nothing modified, but upstream is behind.
                msg += f"but {repo.status.splitlines()[1]}\n\t".replace(
                    "ahead", "[b]ahead[/b]"
                )
            else:
                # nothing modified, everything up-to-date.
                msg += "everything up-to-date."

            if remotes.origin:
                msg += f" [b]origin[/b]: [i]{remotes.origin}[/i]."
            if remotes.upstream:
                # I forked it
                msg += f" [b]upstream[/b]: [i]{remotes.upstream}[/i]."
            if remotes.tracking:
                msg += f" [b]tracking[/b]: [i]{remotes.tracking}[/i]"

            logger.good(msg)
            continue

        # * Interact whether to pull etc; either something modified, or we're behind/ahead, or mine and upstream diverged
        os.chdir(repo.path)
        logger.info(f"\n[prompt]{repo.path}[/]")
        os.system("git status")  # Just to display in terminal
        print()

        if has_local_modified_files:
            if "behind" in repo.status:
                if Confirm.ask(
                    f"[prompt][b]{repo.path}[/b]: has local modifications, and is behind. "
                    f"Launch a temporary [b]{config.shell}[/b] console?[/]"
                ):
                    os.system(f"{config.shell} -l")
                continue

            if "ahead" in repo.status:
                prompt = (
                    f"[b]{repo.path}[/b]: \[p]ush origin {remotes.current_branch}, "
                    f"launch a temporary [b]{config.shell}[/b] \[c]onsole, "
                    f"or do \[n]othing?"
                )
                answer = Prompt.ask(prompt, choices=["p", "c", "n"])
                if answer == "p":
                    logger.info("Pushing...")
                    os.system(f'git push origin "{remotes.current_branch}"')
                    print()
                elif answer == "c":
                    os.system(f"{config.shell} -l")
                continue

            # has local modifications, not ahead and not behind. can be pushed
            if Confirm.ask(
                f"[prompt][b]{repo.path}[/b]: has local modifications. Launch a temporary [b]{config.shell}[/b] console?[/]"
            ):
                os.system(f"{config.shell} -l")
            continue

        # nothing modified, can be pulled
        if "ahead" not in repo.status and (
            "behind" in repo.status or "have diverged" in repo.status
        ):
            # TODO: is it always true that no local modified files here?
            if quiet:
                logger.info("[prompt]Would've prompted git pull, but quiet=True")
            else:
                prompt = (
                    f"[b]{repo.path}[/b]: git \[p]ull, "
                    f"launch a temporary [b]{config.shell}[/b] \[c]onsole, "
                    f"or do \[n]othing?"
                )
                answer = Prompt.ask(prompt, choices=["p", "c", "n"])
                if answer == "p":
                    logger.info("Pulling...")
                    os.system("git pull")
                    print()
                elif answer == "c":
                    os.system(f"{config.shell} -l")
            continue

        # * end of main loop: go back to parent directory
        os.chdir(parent_path)


def usage(ctx, parent_path: Path):
    helpstr = main.get_help(ctx)
    helplines = helpstr.splitlines()
    title = helplines[0]
    rest = "\n".join(helplines[1:])
    h1 = lambda x: f"[b rgb(200,150,255)]{x}[/b rgb(200,150,255)]"
    h2 = lambda x: f"[b rgb(150,200,255)]{x}[/]"
    h3 = lambda x: f"[b]{x}[/b]"
    code = (
        lambda x: f"[rgb(180,180,180) on rgb(30,30,30)]{x}[/rgb(180,180,180) on rgb(30,30,30)]"
    )
    kw = lambda x: f"[i rgb(180,180,180)]{x}[/i rgb(180,180,180)]"
    arg = lambda x: f"[rgb(180,180,180)]{x}[/rgb(180,180,180)]"
    d = lambda x: f"[dim]{x}[/dim]"
    ta = lambda x: f"[dim i]{x}[/dim i]"
    helpstr = "\n".join(
        [
            "\n" + h1(title),
            rest,
            # Arguments / Options that are parsed manually (not by click)
            "  -v, --verbose LEVEL: INT\t  Can be specified e.g -vvv [default: 0]",
            '  --cache-mode MODE: STR\t  "r", "w", or "r+w" to write only if none was read [default: None]',
            "  --max-workers LIMIT: INT\t  Limit threads and processes [default: None]",
            "  --max-depth DEPTH: INT\t  [default: 1]",
            '  --difftool PATH: STR\t\t  [default: "diff"]',
            "  --gitdir-size-limit SIZE_MB: INT\t A dir is skipped if its .git dir size >= SIZE_MB [default: 100]",
            "",
            h1(".tmrignore and .tmrrc.py files"),
            *"\n  ".join(
                [
                    f"  Looked for in PARENT_PATH ({parent_path}) and HOME ({Path.home()}).\n",
                    h2(".tmrignore"),
                    "Each line is a STRING_OR_ADV_REGEX and is processed as if passed via EXCLUDE option.",
                    "Lines that start with `#` are not parsed.\n",
                    h3("Example .tmrignore:"),
                    f"{d(1)} /mnt/.*",
                    d(2),
                    f"{d(3)} `# .profile (gist id)`",
                    f"{d(4)} c123f45ce6fc789c0dfef1234fd5bcb6 `# Comments like these are fine`",
                    f"{d(5)} {Path.home().parts[2]}/Music",
                    d(6),
                    f"{d(7)} `# .gist description`",
                    f"{d(8)} Visual Studio Code Settings",
                    f"{d(9)} foo\-\d{{4}}\n",
                    h2(".tmrrc.py"),
                    "A file containing a `config` object "
                    "with the following settable attributes:",
                    "`config.verbose`: int = 0",
                    "`config.max_workers`: int = None",
                    "`config.max_depth`: int = 1",
                    "`config.difftool`: str = 'diff'",
                    "`config.gitdir_size_limit_mb`: int = 100",
                    "`config.cache.mode`: 'r' | 'w' | 'r+w' = None",
                    f"`config.cache.path`: str = '{Path.home()}/.cache/too-many-repos'",
                    "`config.cache.gist_list`: bool = None",
                    "`config.cache.gist_filenames`: bool = None",
                    "`config.cache.gist_content`: bool = None\n",
                    "Note that cmdline opts have priority over settings in .tmrrc.py in case both are specified.",
                ]
            ).splitlines(),
        ]
    )
    helpstr = helpstr.replace("[default: ", "\[default: ")  # Escape because rich
    helpstr = helpstr.replace("Options:", h1("Options:"))

    # `foo`
    helpstr = re.sub(r"`(.+)`", lambda match: code(match.group(1)), helpstr)

    # SIZE_MB
    helpstr = re.sub(
        r"(?<!: )\b\$?[A-Z_]{2,}\b", lambda match: kw(match.group()), helpstr
    )

    # : INT
    helpstr = re.sub(
        r": (\b(STR|INT)\b)", lambda match: f" {ta(match.group())}", helpstr
    )

    # -h, --help
    helpstr = re.sub(
        r"(-[a-z-]+)(,)?",
        lambda match: f'{arg(match.group(1))}{match.group(2) if match.group(2) else ""}',
        helpstr,
    )

    # from rich import inspect
    main.callback.__doc__ = helpstr
    from rich.console import Console

    con = Console(highlight=False, soft_wrap=False)
    con.print(helpstr)


if __name__ == "__main__":
    main()
