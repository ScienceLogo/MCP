"""The long-running Racket helper that answers the server's requests."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any

HELPER = Path(__file__).parent / "racket" / "helper.rkt"


class HelperError(RuntimeError):
    pass


def find_racket() -> str:
    """The `racket` executable: SCIENCELOGO_MCP_RACKET, or `racket` on PATH."""
    racket = os.environ.get("SCIENCELOGO_MCP_RACKET") or shutil.which("racket")
    if not racket:
        raise HelperError("Racket not found: set SCIENCELOGO_MCP_RACKET or put racket on PATH")
    return racket


class RacketHelper:
    """One Racket process, restarted when it crashes or stops answering."""

    def __init__(self, racket: str | None = None, timeout: float = 120.0) -> None:
        self._racket = racket
        self._timeout = timeout
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._replies: queue.Queue[str | None] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=50)
        self._next_id = 0

    def _start(self) -> None:
        if self._racket is None:
            self._racket = find_racket()
        self._process = subprocess.Popen(
            [self._racket, str(HELPER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._replies = queue.Queue()
        self._stderr.clear()
        threading.Thread(
            target=self._pump, args=(self._process.stdout, self._replies), daemon=True
        ).start()
        threading.Thread(target=self._drain, args=(self._process.stderr,), daemon=True).start()

    @staticmethod
    def _pump(stream: Any, replies: queue.Queue[str | None]) -> None:
        for line in stream:
            replies.put(line)
        replies.put(None)

    def _drain(self, stream: Any) -> None:
        for line in stream:
            self._stderr.append(line)

    def _stop(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process.wait()
            self._process = None

    def close(self) -> None:
        with self._lock:
            self._stop()

    def request(self, op: str, **args: Any) -> dict[str, Any]:
        """Send one request and return its result.

        A crash or timeout restarts the helper and raises HelperError.
        """
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._start()
            assert self._process is not None and self._process.stdin is not None
            self._next_id += 1
            request_id = self._next_id
            try:
                self._process.stdin.write(json.dumps({"id": request_id, "op": op, **args}) + "\n")
                self._process.stdin.flush()
                line = self._replies.get(timeout=self._timeout)
            except queue.Empty:
                self._stop()
                raise HelperError(f"the Racket helper did not answer within {self._timeout} s")
            except BrokenPipeError:
                line = None
            if line is None:
                detail = "".join(self._stderr).strip()
                self._stop()
                raise HelperError("the Racket helper stopped" + (f":\n{detail}" if detail else ""))
            reply = json.loads(line)
            if reply.get("id") != request_id:
                self._stop()
                raise HelperError("the Racket helper answered a different request")
            if "error" in reply:
                raise HelperError(reply["error"])
            return reply["result"]
