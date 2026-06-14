"""Human-readable demo logging to console and logs/."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any


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

    def __init__(self, log_dir: str = "logs", debug_enabled: bool | None = None) -> None:
        self.start_time = time.monotonic()
        path = Path(log_dir)
        path.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.file_path = path / f"simulation-{stamp}.log"

        env_debug = os.getenv("SWARM_DEBUG_STATE", "")
        self.debug_enabled = debug_enabled if debug_enabled is not None else env_debug.lower() in {"1", "true", "yes", "on"}
        self._debug_counter = 0
        self._debug_dir: Path | None = None
        if self.debug_enabled:
            debug_root = path / "debug"
            debug_root.mkdir(exist_ok=True)
            self._debug_dir = debug_root / f"simulation-{stamp}"
            self._debug_dir.mkdir(exist_ok=True)

    def log(self, tag: str, message: str) -> None:
        """Emit one event with elapsed time; side effect: append to log file."""
        elapsed = time.monotonic() - self.start_time
        plain = f"{elapsed:05.2f}s [{tag}] {message}"
        color = COLOR_BY_AGENT.get(tag, Colors.RESET)
        print(f"{Colors.DIM}{elapsed:05.2f}s{Colors.RESET} {color}[{tag}]{Colors.RESET} {message}", flush=True)
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(plain + "\n")

    def log_debug(self, tag: str, label: str, payload: dict[str, Any]) -> Path | None:
        """Persist structured debugging payloads when debugging is enabled."""

        if not self._debug_dir:
            return None

        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "snapshot"
        filename = f"{self._debug_counter:04d}-{tag}-{safe_label}.json"
        self._debug_counter += 1
        file_path = self._debug_dir / filename
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return file_path
