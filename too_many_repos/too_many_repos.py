#!/bin/python3.8
import os
import re
import sys
from collections import defaultdict
from concurrent import futures as fut
from multiprocessing import Pool as ProcPool
from pathlib import Path
from typing import Dict, List, Optional

import click
from rich import print
from rich.prompt import Confirm, Prompt

import too_many_repos.gist as gist
from too_many_repos.log import logger
from too_many_repos.repo import Repo, is_repo
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore
from too_many_repos.util import safe_glob, safe_is_dir, safe_is_file, unrequired_opt



def ask_user_which_gist_file_belongs_to(
    file: Path, matching_gists: List[gist.Gist]
) -> Optional[gist.Gist]:
    if len(matching_gists) == 1:
        matching_gist = matching_gists[0]
    else:
        prompt = f"[i]{file.absolute()}[/i] | What gist?\n"
        for i, matching_gist in enumerate(matching_gists, start=1):
            prompt += f"{i}] {matching_gist}\n"
        prompt += "s] skip\n"
        answer = Prompt.ask(
            prompt, choices=list(map(str, range(1, len(matching_gists) + 1))) + ["s"]
        )
        if answer == "s":
            return None
        matching_gist = matching_gists[int(answer) - 1]
    return matching_gist


def get_direct_subdirs(path: Path) -> List[Path]:
    direct_subdirs = []
    if tmrignore.is_ignored(path.absolute()):
        if config.verbose >= 2:
            logger.warning(
                f"Main.get_direct_subdirs() | [b]{path}[/b]: skipping; excluded"
            )
        return direct_subdirs
    for subdir in filter(Path.is_dir, path.glob("*")):
        if tmrignore.is_ignored(subdir.absolute()):
            if (
                config.verbose >= 2
            ):  # keep >=2 because prints for all subdirs of excluded
                logger.warning(
                    f"Main.get_direct_subdirs() | [b]{subdir}[/b]: skipping; excluded"
                )
            continue
        direct_subdirs.append(subdir)
    return direct_subdirs


def diff_recursively_with_gists(
    path: Path, file_name_to_gist_files: Dict[str, List[gist.GistFile]], *, max_depth
) -> Dict[Path, List[gist.GistFile]]:
    """
    Goes over files inside path and diffs them against any matching gist.

    Called in a multithreaded context.
    """
    if tmrignore.is_ignored(path.absolute()):
        config.verbose >= 2 and logger.warning(
            f"Main.diff_recursively_with_gists() | [b]{path}[/b]: skipping; excluded"
        )
        return defaultdict(list)

    need_user_disambiguation: Dict[Path, List[gist.GistFile]] = defaultdict(list)

    # File case
    if safe_is_file(path):
        file = path
        config.verbose >= 3 and logger.debug(
            f"Main.diff_recursively_with_gists() | Checking if there a matching gist to {file}..."
        )
        gist_files = file_name_to_gist_files.get(file.name)
        if not gist_files:
            return defaultdict(list)
        if len(gist_files) > 1:
            need_user_disambiguation[file].extend(gist_files)
            return need_user_disambiguation
        gist_file = gist_files[0]
        gist_file.diff(file)
        return defaultdict(list)

    # Directory case
    if max_depth == 0:
        config.verbose >= 3 and logger.debug(
            f"Main.diff_recursively_with_gists() | Reached {max_depth = } in {path}"
        )
        return defaultdict(list)

    config.verbose >= 3 and logger.debug(
        f"Main.diff_recursively_with_gists() | Looking for gists to diff inside {path}..."
    )

    if safe_is_dir(path):
        for subpath in path.glob("*"):
            update = diff_recursively_with_gists(
                subpath, file_name_to_gist_files, max_depth=max_depth - 1
            )
            need_user_disambiguation.update(update)
    return need_user_disambiguation


def populate_repos_recursively(path: Path, repos: List[Repo], *, max_depth) -> None:
    config.verbose >= 3 and logger.debug(
        f"Main.populate_repos_recursively() | Populating repos inside {path}..."
    )

    if safe_is_file(path):
        config.verbose >= 3 and logger.debug(
            f"Main.populate_repos_recursively() | {path} is a file. Returning None."
        )
        return

    if tmrignore.is_ignored(path.absolute()):
        config.verbose >= 2 and logger.warning(
            f"Main.populate_repos_recursively() | [b]{path}[/b]: skipping; excluded"
        )
        return

    if is_repo(path):
        repo = Repo(path)

        if repo.is_gitdir_too_big():
            logger.warning(
                f"Main.populate_repos_recursively() | [b]{repo.path}[/b]: skipping; .git dir size is above {config.gitdir_size_limit_mb}MB"
            )
        else:
            repos.append(repo)
    if max_depth == 0:
        config.verbose >= 3 and logger.debug(
            f"Main.populate_repos_recursively() | Reached {max_depth = } in {path}"
        )
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
        file_name_to_gist_files = gist.build_file_name_to_gist_files_parallel()
        logger.info(f"\nMain.main() | Built {len(file_name_to_gist_files)} gists\n")

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
        logger.info(
            f"\nMain.main() | Diffing gists recursively in {max_workers} threads..."
        )
        need_user_disambiguation: Dict[Path, List[gist.GistFile]] = defaultdict(list)
        futures: Dict[Path, fut.Future] = {}
        with fut.ThreadPoolExecutor(max_workers) as xtr:
            for subdir in direct_subdirs:
                future = xtr.submit(
                    diff_recursively_with_gists,
                    subdir,
                    file_name_to_gist_files,
                    max_depth=config.max_depth,
                )
                futures[subdir] = future

        for subdir, future in futures.items():
            current_need_user = future.result()
            current_need_user and logger.debug(
                f"Got {len(current_need_user)} paths that need user to disambiguate from {subdir}"
            )
            need_user_disambiguation.update(current_need_user)
        current_need_user = diff_recursively_with_gists(
            parent_path, file_name_to_gist_files, max_depth=1
        )
        current_need_user and logger.debug(
            f"Main.main() | Got {len(current_need_user)} paths that need user to disambiguate from {parent_path}"
        )
        need_user_disambiguation.update(current_need_user)
        logger.debug(
            f"Main.main() | In total, {len(need_user_disambiguation)} paths need user to disambiguate"
        )

        for filename, gistfiles in file_name_to_gist_files.items():
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
                                    f'nohup "{difftool}" {" ".join(difftool_args)} "{path}" "{gistfile.gist_file_temp_path}" 1>/dev/null 2>&1 &'
                                )
                            else:
                                os.system(
                                    f'"{difftool}" {" ".join(difftool_args)} "{path}" "{gistfile.gist_file_temp_path}"'
                                )
                    else:
                        logger.info(
                            f"[b]Diff '{path.absolute()}'[/b] and [b]{gistfile.gist.short()}[/b] are [b green]identical[/]"
                        )

    # if need_user_disambiguation:
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
        logger.info(
            f"Main.main() | Fetching {len(repos)} repos in {max_workers} processes..."
        )
        with ProcPool(max_workers) as pool:
            pool.map(Repo.fetch, repos)

    # * status
    logger.info(f"Main.main() | Git status {len(repos)} repos serially...")
    for repo in repos:
        repo.popuplate_status()

    logger.info("Main.main() | Done fetching and git statusing")

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
    kw = lambda x: f"[rgb(180,180,180)]{x}[/rgb(180,180,180)]"
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
            "  --gitdir-size-limit-mb SIZE_MB: INT\t A dir is skipped if its .git dir size >= SIZE_MB [default: 100]",
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
