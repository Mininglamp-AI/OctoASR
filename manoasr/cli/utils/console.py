# coding=utf-8
"""Console output utilities"""

from __future__ import annotations


def success(msg: str) -> str:
    return f"  ✓ {msg}"


def error(msg: str) -> str:
    return f"  ✗ {msg}"


def warning(msg: str) -> str:
    return f"  ! {msg}"


def info(msg: str) -> str:
    return f"  → {msg}"


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def divider(width: int = 35) -> str:
    return "─" * width


def key_value(key: str, value: str, width: int = 10) -> str:
    return f"  {key}:{' ' * (width - len(key))}{value}"


def print_header(title: str) -> None:
    print(f"\n  {title}")
    print(f"  {divider()}")


def print_footer() -> None:
    print(f"  {divider()}\n")


def interactive_select(title: str, options: list[dict], current: str | None = None) -> dict | None:
    """Arrow-key driven interactive selector.

    Each option is a dict with at least a ``key`` field.  Optional fields:
    ``label`` (display text, defaults to key) and ``hint``.

    Returns the chosen option dict, or None if the user pressed Ctrl-C / q.
    """
    import sys
    import tty
    import termios

    if not options:
        return None

    selected = 0
    for i, opt in enumerate(options):
        if opt["key"] == current:
            selected = i
            break

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    menu_lines = len(options) + 4

    def _read_key() -> str:
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        if ch in ("\x03", "\x04"):
            return "ctrl-c"
        return ch

    def _render(sel: int) -> None:
        lines = []
        lines.append(f"\r\n  {title}")
        lines.append(f"  {divider()}")
        for i, opt in enumerate(options):
            label = opt.get("label", opt["key"])
            marker = "›" if i == sel else " "
            tag = " (active)" if opt["key"] == current else ""
            highlight = "\033[1m" if i == sel else ""
            reset = "\033[0m" if i == sel else ""
            lines.append(f"  {marker} {highlight}{label}{tag}{reset}")
        lines.append(f"  {divider()}")
        lines.append(f"  ↑↓ select  Enter confirm  q cancel")
        sys.stdout.write("\r\n".join(lines))
        sys.stdout.flush()

    def _clear_menu() -> None:
        sys.stdout.write(f"\r\033[{menu_lines}A")
        sys.stdout.write(f"\033[J")
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l")

        _render(selected)

        while True:
            key = _read_key()
            if key == "up":
                selected = (selected - 1) % len(options)
            elif key == "down":
                selected = (selected + 1) % len(options)
            elif key == "enter":
                _clear_menu()
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
                return options[selected]
            elif key in ("ctrl-c", "esc", "q"):
                _clear_menu()
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
                return None
            else:
                continue

            _clear_menu()
            _render(selected)
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
