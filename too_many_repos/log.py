import logging
from datetime import datetime
from typing import Optional, IO, Union, Callable, Mapping, Literal

from rich._log_render import FormatTimeCallable
from rich.console import Console, HighlighterType
from rich.highlighter import ReprHighlighter
from rich.logging import RichHandler
from rich.style import StyleType
from rich.theme import Theme


# from typing_extensions import Literal


class TmrConsole(Console):

	def __init__(self, *,
				 color_system: Optional[Literal["auto", "standard", "256", "truecolor", "windows"]] = "auto",
				 force_terminal: bool = None,
				 force_jupyter: bool = None,
				 force_interactive: bool = None,
				 soft_wrap: bool = False,
				 theme: Theme = None,
				 stderr: bool = False,
				 file: IO[str] = None,
				 quiet: bool = False,
				 width: int = None,
				 height: int = None,
				 style: StyleType = None,
				 no_color: bool = None,
				 tab_size: int = 2,
				 record: bool = False,
				 markup: bool = True,
				 emoji: bool = True,
				 highlight: bool = True,
				 log_time: bool = True,
				 log_path: bool = True,
				 log_time_format: Union[str, FormatTimeCallable] = "[%X]",
				 highlighter: Optional["HighlighterType"] = ReprHighlighter(),
				 legacy_windows: bool = None,
				 safe_box: bool = True,
				 get_datetime: Callable[[], datetime] = None,
				 get_time: Callable[[], float] = None,
				 _environ: Mapping[str, str] = None):
		if theme is None:
			theme = Theme({'#': 'rgb(120,120,120)',
						   'warn': 'rgb(200,200,200) on rgb(40,40,0)',
						   'good': 'green',
						   'prompt': 'b bright_magenta'})
		super().__init__(color_system=color_system, force_terminal=force_terminal, force_jupyter=force_jupyter, force_interactive=force_interactive, soft_wrap=soft_wrap, theme=theme, stderr=stderr, file=file,
						 quiet=quiet, width=width, height=height, style=style, no_color=no_color, tab_size=tab_size, record=record, markup=markup, emoji=emoji, highlight=highlight, log_time=log_time, log_path=log_path,
						 log_time_format=log_time_format, highlighter=highlighter, legacy_windows=legacy_windows, safe_box=safe_box, get_datetime=get_datetime, get_time=get_time, _environ=_environ)


console = TmrConsole()
rhandler = RichHandler(level=logging.DEBUG,
					   console=console,
					   markup=True,
					   show_level=False,
					   show_time=False,
					   show_path=False,
					   rich_tracebacks=True,
					   tracebacks_extra_lines=10,
					   tracebacks_show_locals=True)
logger = logging.getLogger()

# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter('%(asctime)s %(name) %(levelname) %(message)s'))
# logger.addHandler(handler)
logger.addHandler(rhandler)
logger.setLevel(logging.DEBUG)


def good(self: logging.Logger, msg, *args, **kwargs):
	self._log(logging.INFO, f'[good]{msg}[/good]', args, **kwargs)


logger.__class__.good = good

_record_factory = logging.getLogRecordFactory()


def record_factory(name, level, pathname, lineno,
				   msg, args, exc_info, func=None, sinfo=None, **kwargs) -> logging.LogRecord:
	if level == 10:
		lines = str(msg).splitlines()

		msg = f'[#]' + '# ' + '\n# '.join(lines) + '[/#]'
	elif level == 30:
		msg = f'[warn]{msg}[/warn]'

	return _record_factory(name, level, pathname, lineno, msg, args, exc_info, func, sinfo, **kwargs)


logging.setLogRecordFactory(record_factory)
