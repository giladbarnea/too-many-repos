import typing
from collections import defaultdict
from concurrent import futures as fut
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, ForwardRef, List, Literal

from too_many_repos import system
from too_many_repos.cache import cache
from too_many_repos.log import logger
from too_many_repos.tmrconfig import config
from too_many_repos.tmrignore import tmrignore

Difference = Literal["whitespace", "content", "order", False]


class GistFile:
    content: str
    rstripped_content: str
    diffs: Dict[Path, Difference]
    gist: ForwardRef("Gist")
    file_name: str

    def __init__(self, name: str, gist: ForwardRef("Gist")):
        self.content: str = ""
        self.rstripped_content: str = ""
        self.diffs = dict()
        self.file_name = name
        self.gist = gist
        self.gist_temp_base_path = Path(f"/tmp/{self.gist.id}")
        self.gist_temp_base_path.mkdir(exist_ok=True, parents=True)
        self.gist_file_temp_path = self.gist_temp_base_path / self.file_name

    def __repr__(self) -> str:
        rv = f"GistFile('{self.file_name}') {{ \n\tcontent: "
        if self.content:
            rv += rf'"{self.content[:16]}..."'
        else:
            rv += "--"
        if self.gist:
            rv += f"\n\tGist: {self.gist.short()}"
        rv += f"\n\tdiffs: {self.diffs} }}"
        return rv

    def diff(self, against: Path) -> None:
        """Populates self.diffs[against] with the `Difference` between self and given file; either 'whitespace', 'content', 'order', or False."""
        # TODO (reuse files): write to ~/.cache/<SESSION>/ instead and check if exists before
        logger.debug(f'GistFile.diff() | {self.gist.short()} diffing "{against}"...')

        try:
            against_lines = against.open().read().splitlines()
        except UnicodeDecodeError:
            difference = self._diff_binary(against)
        else:
            difference = self._diff_text(against, against_lines)

        config.verbose >= 2 and difference and logger.debug(
            f'GistFile.diff() | {self.gist.short()} and "{against}" are different in {difference!r}'
        )
        self.diffs[against] = difference

    def _is_flat_format(self) -> bool:
        return all(
            line == line.lstrip() for line in filter(bool, self.content.splitlines())
        )

    def _diff_binary(self, against: Path) -> Difference:
        write_file(
            self.gist_file_temp_path,
            self.content,
            overwrite_ok=False,
        )
        same_as_is = system.diff_quiet(f'"{self.gist_file_temp_path}" "{against}"')
        return False if same_as_is else "content"

    def _diff_text(self, against: Path, against_lines: list[str]) -> Difference:
        against_lines_rstripped = list(filter(bool, map(str.rstrip, against_lines)))
        same_when_rstripped: bool = (
            against_lines_rstripped == self.rstripped_content.splitlines()
        )
        if not same_when_rstripped:
            difference = "content"
        elif not (
            against_lines == self.content.splitlines()
            # elif not same as-is:
        ):
            difference = "whitespace"
        else:
            difference = False
        if difference and self._is_flat_format():
            against_set = set(filter(bool, against_lines_rstripped))
            self_set = set(filter(bool, self.rstripped_content.splitlines()))
            if against_set == self_set:
                difference = "order"
        if difference:
            write_file(
                self.gist_file_temp_path,
                self.content,
                overwrite_ok=False,
            )
        return typing.cast(Difference, difference)


def write_file(file_path, content: str, *, overwrite_ok: bool) -> bool:
    if overwrite_ok:
        with open(file_path, mode="w") as file:
            file.write(content)
        return True
    try:
        with open(file_path, mode="x") as file:
            file.write(content)
        return True
    except FileExistsError:
        return False


@dataclass
class Gist:
    id: str
    description: str
    filecount: Any
    permissions: Literal["secret", "public"]
    date: str
    files: Dict[str, GistFile] = field(default_factory=dict)

    def __str__(self):
        return f"{self.id[:16]} '{self.description}' ({self.filecount} files)"

    def short(self) -> str:
        return f"{self.id[:8]} '{self.description[:32]}'"

    def __post_init__(self):
        self.filecount = int(self.filecount.partition(" ")[0])

    def _get_file_names(self) -> List[str]:
        """Calls `gh gist view "{self.id}" --files` to get this gist's list of
        file names (e.g 'alpine.sh').
        May use cache."""
        if (
            "r" in config.cache.mode
            and (filenames := cache.get_gist_filenames(self.id)) is not None
        ):
            return filenames
        filenames = system.run(f'gh gist view "{self.id}" --files').splitlines()
        if "w" in config.cache.mode:
            cache.set_gist_filenames(self.id, filenames)
        return filenames

    def _get_file_content(self, file_name) -> str:
        """Calls `gh gist view '{self.id}' -f '{file_name}'` to get the file's content.
        May use cache."""
        if (
            "r" in config.cache.mode
            and (file_content := cache.get_gist_file_content(self.id, file_name))
            is not None
        ):
            return file_content
        content = system.run(f"gh gist view '{self.id}' -f '{file_name}'")
        if "w" in config.cache.mode:
            cache.set_gist_file_content(self.id, file_name, content)
        return content

    def build_self_files(self, *, skip_ignored: bool) -> None:
        """
        Popuplates self.files.

        Calls self._get_file_names() (GET req) which may use cache.

        Called by build_filename2gistfiles() in a threaded context."""
        filenames = self._get_file_names()
        for name in filenames:
            if tmrignore.is_ignored(name) and skip_ignored:
                logger.warning(
                    f"Gist | file [b]'{name}'[/b] of {self.short()}: skipping; excluded"
                )
                continue
            file = GistFile(name, self)
            self.files[name] = file
        logger.debug(f"Gist | [b]{self.short()}[/b] built {len(self.files)} files")

    def popuplate_files_content(self) -> None:
        """
        For each gist_file in self.files, sets its content.

        Calls self._get_file_content(self, file_name) which may use cache.

        Called by build_filename2gistfiles() in a threaded context.
        """
        for name, gist_file in self.files.items():
            content = self._get_file_content(name)
            gist_file.content = content
            gist_file.rstripped_content = "\n".join(
                filter(bool, map(str.rstrip, content.splitlines()))
            )
        logger.debug(f"Gist | [b]{self.short()}[/b] populated files content")




def get_gist_list() -> List[str]:
    """Calls `gh gist list -L 1000` to get the list of gists.
    May use cache."""

    if "r" in config.cache.mode and (gist_list := cache.gist_list) is not None:
        return gist_list
    gist_list = system.run("gh gist list -L 1000").splitlines()  # not safe
    if "w" in config.cache.mode:
        cache.gist_list = gist_list
    return gist_list


def build_file_name_to_gist_files_parallel() -> Dict[str, List[GistFile]]:
    """
    Maps (using threads) the names of the GistFiles to their actual GistFiles.
    """
    logger.info("\nGist | Getting list of gists...")
    filename2gistfiles: Dict[str, List[GistFile]] = defaultdict(list)
    gists: List[Gist] = []
    gist_list: List[str] = get_gist_list()

    # * files = gh gist view ... --files
    logger.info("\nGist | Getting list of files for each gist...")
    max_workers = (
        min((gist_list_len := len(gist_list)), config.max_workers or gist_list_len) or 1
    )
    max_workers: int = min(max_workers, 32)
    with fut.ThreadPoolExecutor(max_workers) as executor:
        for gist_str in gist_list:
            gist = Gist(*gist_str.split("\t"))

            # There shouldn't be many false positives, because description includes
            # spaces which means pattern.search(gist.description), and id is specific.
            # Note: don't check for file names here
            if tmrignore.is_ignored(gist.id) or tmrignore.is_ignored(gist.description):
                logger.warning(f"Gist | [b]{gist.short()}[/b]: skipping; excluded")
                continue

            future = executor.submit(gist.build_self_files, skip_ignored=True)
            # if exc := future.exception():
            # 	raise exc
            gists.append(gist)

    # * file.content = gh gist view ... -f <NAME>
    logger.info("\nGist | Populating contents of all gist files...")
    with fut.ThreadPoolExecutor(max_workers) as executor:
        for gist in gists:
            for name, gistfile in gist.files.items():
                future = executor.submit(gist.popuplate_files_content)
                # if exc := future.exception():
                # 	raise exc
                filename2gistfiles[name].append(gistfile)
            config.verbose >= 2 and logger.debug(gist)

    return filename2gistfiles
