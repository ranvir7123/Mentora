"""The program's end of the link to the VS Code add-on: a socket on this computer only.

The link listens on 127.0.0.1 on a free port and takes exactly one add-on: the first one whose first
line is `hello` with the right token and protocol version. Anything else is dropped. Once that add-on
has connected, the link stops listening; when it goes away, `on_closed` is called once (never when
the program itself calls `stop`).

`on_state` and `on_closed` are called from the link's own thread and must return at once.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import threading
from concurrent.futures import Future
from typing import Any, Callable, Mapping, Sequence

from app.core.types import Call
from app.vscode.protocol import MESSAGES, PROTOCOL_VERSION

HELLO_TIMEOUT = 5.0              # seconds a new connection has to say hello
HELLO_LIMIT = 4096               # bytes a hello line may take
LINE_LIMIT = 64 * 1024 * 1024    # bytes any later line may take

OUT_OF_DATE = "The Project X add-on in VS Code is out of date. Install the one built from extensions/vscode."


def _parse(line: bytes) -> dict | None:
    try:
        message = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        return None
    return message if isinstance(message, dict) and isinstance(message.get("type"), str) else None


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


class Bridge:
    def __init__(self, on_state: Callable[[dict], None], on_closed: Callable[[], None]):
        self._on_state = on_state
        self._on_closed = on_closed
        self.token = secrets.token_urlsafe(32)
        self.port = 0
        self.address: tuple[str, int] = ("127.0.0.1", 0)
        self.refused = ""                        # why the last add-on was turned away, in plain words
        self.errors: list[str] = []              # what went wrong inside on_state, for the logs
        self._lock = threading.Lock()            # guards everything below
        self._send_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._used = False
        self._stopped = False
        self._closing = False                    # the program asked VS Code to close
        self._pending: dict[int, Future] = {}
        self._next_id = 1
        self._connected = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> int:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        self.address = listener.getsockname()
        self.port = self.address[1]
        self._listener = listener
        threading.Thread(target=self._accept, args=(listener,), name="vscode-link-listen", daemon=True).start()
        return self.port

    def wait_connected(self, timeout: float) -> bool:
        return self._connected.wait(timeout)

    def send_op(self, op: Call) -> Future:
        """Ask the add-on to do one operation. The Future gives None, or raises with the add-on's reason."""
        future: Future = Future()
        with self._lock:
            conn = self._conn
            if conn is None:
                future.set_exception(ConnectionError("VS Code is not connected"))
                return future
            op_id = self._next_id
            self._next_id += 1
            self._pending[op_id] = future
        if not self._send(conn, {"type": "do", "id": op_id, "op": {"kind": op.kind, "args": dict(op.args)}}):
            with self._lock:
                self._pending.pop(op_id, None)
            if not future.done():
                future.set_exception(ConnectionError("VS Code is not connected"))
        return future

    def ping(self) -> bool:
        """Ask the add-on for a fresh state at once."""
        return self._send_now({"type": "ping"})

    def send_env(self, values: Mapping[str, str], path_prepend: Sequence[str]) -> bool:
        """Set variables for VS Code terminals opened from now on. The add-on never saves them."""
        return self._send_now({"type": "env", "set": dict(values), "path_prepend": list(path_prepend)})

    def close_window(self) -> bool:
        """Ask the add-on to save the lesson's files and close its window. No `on_closed` follows."""
        with self._lock:
            self._closing = True
        return self._send_now({"type": "close"})

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            listener, self._listener = self._listener, None
            conn, self._conn = self._conn, None
            pending, self._pending = list(self._pending.values()), {}
        self._connected.clear()
        if listener is not None:
            listener.close()
        if conn is not None:
            _close(conn)
        for future in pending:
            if not future.done():
                future.set_exception(ConnectionError("the link to VS Code was stopped"))

    # The link's own threads.

    def _accept(self, listener: socket.socket) -> None:
        while True:
            try:
                sock, _ = listener.accept()
            except OSError:
                return                           # stopped, or done listening
            threading.Thread(target=self._greet, args=(sock,), name="vscode-link", daemon=True).start()

    def _greet(self, sock: socket.socket) -> None:
        reader = sock.makefile("rb")
        try:
            sock.settimeout(HELLO_TIMEOUT)
            hello = _parse(reader.readline(HELLO_LIMIT))
        except OSError:
            hello = None
        if not self._accepts(hello):
            reader.close()
            _close(sock)
            return
        with self._lock:
            taken = self._stopped or self._used
            if not taken:
                self._used, self._conn = True, sock
                listener, self._listener = self._listener, None
        if taken:
            reader.close()
            _close(sock)
            return
        if listener is not None:
            listener.close()                     # the token is good for one add-on only
        sock.settimeout(None)
        self._connected.set()
        self._read(sock, reader)

    def _accepts(self, hello: dict | None) -> bool:
        if hello is None or hello.get("type") != "hello" or not isinstance(hello.get("token"), str):
            return False
        if not hmac.compare_digest(hello["token"].encode("utf-8"), self.token.encode("utf-8")):
            return False
        if hello.get("version") != PROTOCOL_VERSION:
            self.refused = OUT_OF_DATE
            return False
        return True

    def _read(self, sock: socket.socket, reader: Any) -> None:
        try:
            while True:
                line = reader.readline(LINE_LIMIT)
                if not line or (len(line) >= LINE_LIMIT and not line.endswith(b"\n")):
                    break                        # gone, or a line too long to be the add-on's
                message = _parse(line)
                if message is None:
                    continue
                if message["type"] == "state":
                    self._deliver({k: message.get(k) for k in MESSAGES["state"]})
                elif message["type"] == "done":
                    self._resolve(message)
        except OSError:
            pass
        finally:
            reader.close()
            self._lost(sock)

    def _deliver(self, state: dict) -> None:
        try:
            self._on_state(state)
        except Exception as exc:                 # a crash on our side must not cut the link
            if len(self.errors) < 20:
                self.errors.append(f"on_state: {exc!r}")

    def _resolve(self, message: dict) -> None:
        with self._lock:
            future = self._pending.pop(message.get("id"), None)
        if future is None or future.done():
            return
        if message.get("ok") is True:
            future.set_result(None)
        else:
            future.set_exception(RuntimeError(str(message.get("error") or "VS Code could not do that")))

    def _lost(self, sock: socket.socket) -> None:
        with self._lock:
            if self._conn is not sock:
                return                           # stopped by the program: no on_closed
            self._conn = None
            pending, self._pending = list(self._pending.values()), {}
            closing = self._closing
        self._connected.clear()
        _close(sock)
        for future in pending:
            if not future.done():
                future.set_exception(ConnectionError("VS Code was closed"))
        if closing:
            return
        try:
            self._on_closed()
        except Exception as exc:
            self.errors.append(f"on_closed: {exc!r}")

    # Sending.

    def _send_now(self, message: dict) -> bool:
        with self._lock:
            conn = self._conn
        return conn is not None and self._send(conn, message)

    def _send(self, conn: socket.socket, message: dict) -> bool:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                conn.sendall(data)
            return True
        except OSError:
            return False
