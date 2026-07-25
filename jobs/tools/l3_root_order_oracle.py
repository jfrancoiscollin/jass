#!/usr/bin/env python3
"""Diagnostic Scan-root-order oracle used by the preregistered 0961 replay."""

from __future__ import annotations

import os
import re
import time
from typing import Any

try:
    from l3_internal_root_trace import parse_root_events
    from l3_internal_root_trace_report import final_attempt
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_internal_root_trace import parse_root_events
    from jobs.tools.l3_internal_root_trace_report import final_attempt


APPLY_RE = re.compile(
    r"^apply\s+(\d+)([-x])(\d+)(?:\s+captures=([0-9,]+))?$"
)
KV_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")


def schedule_from_events(
    events: list[dict[str, object]], max_depth: int
) -> str:
    parts: list[str] = []
    for depth in range(1, max_depth + 1):
        attempt = final_attempt(events, depth)
        order = [str(row["move"]) for row in attempt["moves"]]
        if not order:
            raise ValueError(f"Scan root order is empty at depth {depth}")
        parts.append(f"{depth}:{','.join(order)}")
    return ";".join(parts)


def make_root_order_engine_class(cv: Any):
    class RootOrderJass(cv.JassEngine):
        """Jass whose root list is ordered by a passive traced Scan search."""

        def __init__(
            self,
            path: str,
            *,
            scan_path: str,
            label: str = "Jass-Scan-root-order",
            pattern_path: str | None,
            search_params: str | None,
            timeout: float = 900.0,
        ):
            if os.environ.get("SCAN_TRACE_ROOT") != "1":
                raise RuntimeError("SCAN_TRACE_ROOT=1 is required for 0961")
            self._cv = cv
            self._scan_start_pos = cv.jass_fen_to_scan_pos(
                "W:W31-50:B1-20"
            )
            self._scan_history: list[str] = []
            self._oracle_timeout = timeout
            self.schedule_queries = 0
            self.schedule_terminal_queries = 0
            self.schedule_applications = 0
            self.schedule_failures = 0
            self.last_jass_lines: list[str] = []
            self.last_scan_lines: list[str] = []
            self.scan = cv.ScanEngine(
                scan_path,
                label=f"{label}-order-oracle",
                no_book=True,
                bb_size=0,
            )
            super().__init__(
                path,
                label=label,
                pattern_path=pattern_path,
                search_params=search_params,
            )

        def _send(self, line: str) -> None:
            super()._send(line)
            if line == "position startpos":
                self._scan_start_pos = self._cv.jass_fen_to_scan_pos(
                    "W:W31-50:B1-20"
                )
                self._scan_history = []
            elif line.startswith("position fen "):
                self._scan_start_pos = self._cv.jass_fen_to_scan_pos(
                    line.removeprefix("position fen ")
                )
                self._scan_history = []
            elif line.startswith("apply "):
                match = APPLY_RE.match(line)
                if not match:
                    raise ValueError(f"unparseable Jass apply command: {line!r}")
                captures = tuple(
                    int(token)
                    for token in (match.group(4) or "").split(",")
                    if token
                )
                if match.group(2) == "x" and not captures:
                    raise ValueError(
                        f"capture lacks identity in apply command: {line!r}"
                    )
                move = self._cv.Move(
                    int(match.group(1)), int(match.group(3)), captures
                )
                self._scan_history.append(move.scan_str())

        def _query_schedule(self, depth: int) -> str | None:
            self.scan.new_game()
            self.scan._drain()
            if self._scan_history:
                moves = " ".join(self._scan_history)
                self.scan._send(
                    f'pos pos={self._scan_start_pos} moves="{moves}"'
                )
            else:
                self.scan._send(f"pos pos={self._scan_start_pos}")
            self.scan._send(f"level depth={depth}")
            self.scan._send("go think")
            started = time.monotonic()
            lines = self.scan._read_until(
                lambda line: line.startswith("done")
                or line.startswith("error"),
                timeout_s=self._oracle_timeout,
            )
            self.last_scan_lines = lines
            self.schedule_queries += 1
            trace_lines = [
                line for line in lines if line.startswith("info roottrace ")
            ]
            if not trace_lines:
                terminal = lines[-1]
                if "move=0" not in terminal and "move=none" not in terminal:
                    raise RuntimeError(
                        f"Scan emitted no root order on non-terminal root: {terminal}"
                    )
                self.schedule_terminal_queries += 1
                return None
            events = parse_root_events(lines)
            schedule = schedule_from_events(events, depth)
            if time.monotonic() - started > self._oracle_timeout:
                raise TimeoutError("Scan root-order oracle exceeded timeout")
            return schedule

        def go(
            self,
            depth: int | None = None,
            movetime: float | None = None,
        ):
            if movetime is not None or depth is None:
                raise ValueError("0961 root-order oracle requires fixed depth")
            schedule = self._query_schedule(depth)
            self._send(f"setoption rootorder {schedule or 'none'}")
            configured = self._read_until(
                lambda line: line == "ok" or line.startswith("error")
            )
            if configured[-1].startswith("error"):
                raise RuntimeError(configured[-1])

            self._drain()
            self._send(f"go depth {depth}")
            lines = self._read_until(
                lambda line: line.startswith("bestmove")
                or line.startswith("error"),
                timeout_s=self._oracle_timeout,
            )
            self.last_jass_lines = lines
            last = lines[-1]
            if last.startswith("error"):
                return None
            fields = dict(KV_RE.findall(last))
            applications = int(fields.get("rootorder", "0"))
            failures = int(fields.get("rootorderfail", "0"))
            self.schedule_applications += applications
            self.schedule_failures += failures
            if schedule is not None and (applications < depth or failures):
                raise RuntimeError(
                    "root-order replay contract failed "
                    f"applications={applications} failures={failures} depth={depth}"
                )
            return self._cv.parse_jass_bestmove(last)

        def close(self) -> None:
            try:
                self.scan.close()
            finally:
                super().close()

    return RootOrderJass
