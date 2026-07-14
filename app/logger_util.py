"""
Professional logging utility for Brambet YouTube Automation Server.

Provides:
  - ColorFormatter : ANSI color-coded log formatter with structured layout
  - banner()       : Large section banner for major lifecycle events
  - phase()        : Phase header for pipeline stages
  - step()         : Numbered step indicator within a phase
  - success()      : Green success marker
  - error_box()    : Visually distinct error block with details
  - warning_box()  : Visually distinct warning block
  - summary()      : End-of-cycle summary box
  - divider()      : Horizontal divider line
"""

import logging
import os
import sys
import textwrap

# ─── ANSI color codes ───────────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[97m"

# Detect color support — disable on non-TTY or when NO_COLOR is set
_USE_COLOR = (
    sys.stderr.isatty()
    and os.environ.get("NO_COLOR") is None
    and os.environ.get("TERM") != "dumb"
)

if not _USE_COLOR:
    _RESET = _BOLD = _DIM = ""
    _RED = _GREEN = _YELLOW = ""
    _BLUE = _MAGENTA = _CYAN = _WHITE = ""

# Level-based colors
_LEVEL_COLORS = {
    logging.DEBUG: _DIM,
    logging.INFO: _CYAN,
    logging.WARNING: _YELLOW,
    logging.ERROR: _RED,
    logging.CRITICAL: _RED + _BOLD,
}

# Module-name colors (short hash-based for visual variety)
_MODULE_COLORS = [_BLUE, _MAGENTA, _GREEN, _CYAN, _YELLOW]


def _short_name(name: str) -> str:
    """Shorten 'app.services.video_service' -> 'video_service'."""
    parts = name.split(".")
    return parts[-1] if parts else name


class ColorFormatter(logging.Formatter):
    """Structured, color-coded log formatter.

    Layout:
      HH:MM:SS LEVEL  module  message
    """

    def __init__(self):
        super().__init__(datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, _RESET)
        level_name = record.levelname.ljust(8)
        module_name = _short_name(record.name)
        time_str = self.formatTime(record, self.datefmt)

        # Indent multi-line messages
        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = msg + "\n" + record.exc_text

        lines = msg.split("\n")
        first = lines[0]
        rest = lines[1:]

        indent = " " * (len(time_str) + 1 + len(level_name) + 3 + len(module_name) + 4)
        formatted_rest = "\n".join(indent + line for line in rest)

        line = (
            f"{_DIM}{time_str}{_RESET} "
            f"{color}{level_name}{_RESET} "
            f"{_BOLD}{module_name}{_RESET}  "
            f"{first}"
        )
        if formatted_rest:
            line += "\n" + formatted_rest
        return line


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with the professional ColorFormatter."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColorFormatter())
    root.addHandler(handler)

    # Tame noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)


# ─── Visual helper functions ────────────────────────────────────────
# These use a dedicated logger so they always show up (module: "brambet")
_console = logging.getLogger("brambet")


def _bar(width: int = 60, char: str = "=") -> str:
    return char * width


def banner(title: str, subtitle: str = "") -> None:
    """Print a prominent banner for major lifecycle events."""
    width = 62
    _console.info("")
    _console.info(f"{_BOLD}{_CYAN}{_bar(width)}{_RESET}")
    _console.info(f"{_BOLD}{_CYAN}  {title.center(width - 2)}{_RESET}")
    if subtitle:
        _console.info(f"{_DIM}{_CYAN}  {subtitle.center(width - 2)}{_RESET}")
    _console.info(f"{_BOLD}{_CYAN}{_bar(width)}{_RESET}")


def phase(title: str, job_id: int | None = None) -> None:
    """Print a phase header for a pipeline stage."""
    tag = f"  [Job #{job_id}]" if job_id is not None else ""
    _console.info("")
    _console.info(f"{_BOLD}{_MAGENTA}>>> {title}{tag}{_RESET}")


def step(num: int, total: int, title: str) -> None:
    """Print a numbered step indicator."""
    _console.info(
        f"  {_BOLD}{_BLUE}[{num}/{total}]{_RESET} {title}"
    )


def success(msg: str) -> None:
    """Print a success message with a green checkmark."""
    _console.info(f"  {_GREEN}OK{_RESET}  {msg}")


def fail(msg: str) -> None:
    """Print a failure message with a red cross."""
    _console.error(f"  {_RED}FAIL{_RESET}  {msg}")


def detail(msg: str) -> None:
    """Print a detail line (dim, indented)."""
    _console.info(f"       {_DIM}{msg}{_RESET}")


def divider(char: str = "-", width: int = 60) -> None:
    """Print a horizontal divider."""
    _console.info(f"{_DIM}{char * width}{_RESET}")


def error_box(title: str, message: str, hint: str = "") -> None:
    """Print a visually distinct error block.

    ┌─ ERROR ─────────────────────────────────────────────┐
    │  Title line                                          │
    │  Detailed message...                                 │
    │  hint: suggestion text                              │
    └─────────────────────────────────────────────────────┘
    """
    width = 62
    inner = width - 4
    _console.error("")
    _console.error(f"{_RED}{_BOLD}+-{' ERROR ':-^{inner}}+{_RESET}")
    _console.error(f"{_RED}{_BOLD}|{_RESET} {title}")
    for line in textwrap.wrap(str(message), inner - 1):
        _console.error(f"{_RED}{_BOLD}|{_RESET} {line}")
    if hint:
        _console.error(f"{_RED}{_BOLD}|{_RESET}")
        for line in textwrap.wrap(f"hint: {hint}", inner - 1):
            _console.error(f"{_YELLOW}{_BOLD}|{_RESET} {_YELLOW}{line}{_RESET}")
    _console.error(f"{_RED}{_BOLD}+{'-' * inner}+{_RESET}")


def warning_box(title: str, message: str) -> None:
    """Print a visually distinct warning block."""
    width = 62
    inner = width - 4
    _console.warning("")
    _console.warning(f"{_YELLOW}{_BOLD}+-{' WARNING ':-^{inner}}+{_RESET}")
    _console.warning(f"{_YELLOW}{_BOLD}|{_RESET} {title}")
    for line in textwrap.wrap(str(message), inner - 1):
        _console.warning(f"{_YELLOW}{_BOLD}|{_RESET} {line}")
    _console.warning(f"{_YELLOW}{_BOLD}+{'-' * inner}+{_RESET}")


def summary(title: str, items: list[tuple[str, str]]) -> None:
    """Print a summary box with key-value pairs.

    items: list of (label, value) tuples.
    """
    width = 62
    inner = width - 4
    _console.info("")
    _console.info(f"{_BOLD}{_GREEN}+-{' ' + title + ' ':-^{inner}}+{_RESET}")
    for label, value in items:
        val_str = str(value)
        label_str = f"{_BOLD}{label}:{_RESET}"
        # Right-pad label area to 20 chars for alignment
        pad = max(1, 22 - len(label) - 1)
        for i, line in enumerate(textwrap.wrap(val_str, inner - 22)):
            if i == 0:
                _console.info(
                    f"{_GREEN}|{_RESET} {label_str}{' ' * pad}{line}"
                )
            else:
                _console.info(f"{_GREEN}|{_RESET} {' ' * 21}{line}")
        if not val_str:
            _console.info(f"{_GREEN}|{_RESET} {label_str}{' ' * pad}(none)")
    _console.info(f"{_BOLD}{_GREEN}+{'-' * inner}+{_RESET}")
