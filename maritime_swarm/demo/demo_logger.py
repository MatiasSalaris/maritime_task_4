"""Human-readable demo logging to console and logs/."""

from __future__ import annotations

import time
from pathlib import Path


class Colors:
    """ANSI colors for terminal demo logs."""

    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    DIM = "\033[2m"
    BOLD = "\033[1m"


COLOR_BY_AGENT = {
    "USV-1": Colors.GREEN,
    "USV-2": Colors.YELLOW,
    "USV-3": Colors.MAGENTA,
    "BUS": Colors.CYAN,
    "SIM": Colors.BLUE,
    "OPERATOR": Colors.RED,
}


class DemoLogger:
    """Write concise structured events to terminal and a timestamped log file."""

    def __init__(self, log_dir: str = "logs") -> None:
        self.start_time = time.monotonic()
        path = Path(log_dir)
        path.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.file_path = path / f"simulation-{stamp}.log"

    def log(self, tag: str, message: str) -> None:
        """Emit one event with elapsed time; side effect: append to log file."""
        elapsed = time.monotonic() - self.start_time
        plain = f"{elapsed:05.2f}s [{tag}] {message}"
        color = COLOR_BY_AGENT.get(tag, Colors.RESET)
        print(f"{Colors.DIM}{elapsed:05.2f}s{Colors.RESET} {color}[{tag}]{Colors.RESET} {message}", flush=True)
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(plain + "\n")
