"""ANSI color helpers and console print utilities."""

from __future__ import annotations


class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    MAG    = "\033[95m"


def banner(platform_label: str = ""):
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════╗
║            TAK · Talk to Keyboard        ║
║  {platform_label:^40s}║
╚══════════════════════════════════════════╝{C.RESET}
""")


def status(msg: str, color: str = C.DIM):
    print(f"  {color}▸ {msg}{C.RESET}")


def announce(msg: str):
    print(f"\n  {C.GREEN}{C.BOLD}✔ {msg}{C.RESET}")


def warn(msg: str):
    print(f"  {C.YELLOW}⚠ {msg}{C.RESET}")


def error(msg: str):
    print(f"  {C.RED}✖ {msg}{C.RESET}")
