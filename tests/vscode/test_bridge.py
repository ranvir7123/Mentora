"""The program's end of the link to VS Code, tested with a fake add-on that speaks the same JSON lines."""
from __future__ import annotations

import json
import socket
import time

import pytest

from app.core.types import Call
from app.vscode.bridge import Bridge
from app.vscode.protocol import PROTOCOL_VERSION


class FakeExtension:
    """What the VS Code add-on does on the wire: one JSON object per line."""

    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.reader = self.sock.makefile("r", encoding="utf-8")

    def send(self, message: dict) -> None:
        self.sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def try_send(self, message: dict) -> None:
        """Send, ignoring a link the program already dropped."""
        try:
            self.send(message)
        except OSError:
            pass

    def hello(self, token: str, version: int = PROTOCOL_VERSION) -> None:
        self.send({"type": "hello", "token": token, "version": version})

    def receive(self) -> dict:
        line = self.reader.readline()
        assert line, "the program closed the link"
        return json.loads(line)

    def is_dropped(self) -> bool:
        try:
            return self.reader.readline() == ""
        except (ConnectionError, OSError):
            return True

    def close(self) -> None:
        self.reader.close()
        self.sock.close()


def wait_for(condition, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


STATE = {"type": "state", "files": {"hello.py": {"text": "print('hi')\n", "saved": True}},
         "active": None, "problems": [], "run": None}


@pytest.fixture
def link():
    states: list[dict] = []
    closed: list[int] = []
    bridge = Bridge(on_state=states.append, on_closed=lambda: closed.append(1))
    port = bridge.start()
    clients: list[FakeExtension] = []

    def connect() -> FakeExtension:
        client = FakeExtension(port)
        clients.append(client)
        return client

    yield bridge, connect, states, closed
    for client in clients:
        client.close()
    bridge.stop()


def test_the_link_listens_on_this_computer_only():
    bridge = Bridge(on_state=lambda s: None, on_closed=lambda: None)
    try:
        bridge.start()
        assert bridge.address[0] == "127.0.0.1"
        assert bridge.address[1] == bridge.port > 0
        assert len(bridge.token) >= 32
    finally:
        bridge.stop()


def test_wrong_token_is_dropped(link):
    bridge, connect, states, closed = link
    stranger = connect()
    stranger.hello("not-the-token")
    stranger.try_send(STATE)
    assert stranger.is_dropped()
    assert not bridge.connected
    assert states == []

    vscode = connect()                       # the real add-on can still get in afterwards
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)
    assert closed == []


def test_anything_but_hello_first_is_dropped(link):
    bridge, connect, states, _ = link
    stranger = connect()
    stranger.send({**STATE, "token": bridge.token})
    assert stranger.is_dropped()
    assert states == []


def test_an_old_add_on_is_refused_with_a_reason(link):
    bridge, connect, _, _ = link
    old = connect()
    old.hello(bridge.token, version=PROTOCOL_VERSION + 1)
    assert old.is_dropped()
    assert not bridge.connected
    assert "out of date" in bridge.refused


def test_state_messages_reach_on_state(link):
    bridge, connect, states, _ = link
    vscode = connect()
    vscode.hello(bridge.token)
    vscode.send(STATE)
    assert wait_for(lambda: len(states) == 1)
    assert states[0]["files"] == {"hello.py": {"text": "print('hi')\n", "saved": True}}
    assert states[0]["run"] is None


def test_a_broken_line_is_skipped_not_fatal(link):
    bridge, connect, states, closed = link
    vscode = connect()
    vscode.hello(bridge.token)
    vscode.sock.sendall(b"{not json\n")
    vscode.send(STATE)
    assert wait_for(lambda: len(states) == 1)
    assert bridge.connected and closed == []


def test_a_second_add_on_is_dropped_once_one_is_connected(link):
    bridge, connect, states, _ = link
    first = connect()
    first.hello(bridge.token)
    assert bridge.wait_connected(3)
    assert connect_or_refused(bridge)
    first.send(STATE)
    assert wait_for(lambda: len(states) == 1)


def test_ops_resolve_when_done_arrives(link):
    bridge, connect, _, _ = link
    vscode = connect()
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)

    good = bridge.send_op(Call("write_file", {"path": "hello.py", "text": "print('hi')\n"}))
    bad = bridge.send_op(Call("open_file", {"path": "missing.py"}))
    first, second = vscode.receive(), vscode.receive()
    assert first == {"type": "do", "id": first["id"],
                     "op": {"kind": "write_file", "args": {"path": "hello.py", "text": "print('hi')\n"}}}
    assert second["op"] == {"kind": "open_file", "args": {"path": "missing.py"}}
    assert first["id"] != second["id"]

    vscode.send({"type": "done", "id": second["id"], "ok": False, "error": "missing.py is not there"})
    vscode.send({"type": "done", "id": first["id"], "ok": True, "error": ""})
    assert good.result(3) is None
    with pytest.raises(RuntimeError, match="missing.py is not there"):
        bad.result(3)


def test_an_op_before_connecting_fails_at_once():
    bridge = Bridge(on_state=lambda s: None, on_closed=lambda: None)
    bridge.start()
    try:
        future = bridge.send_op(Call("clear_terminal", {}))
        with pytest.raises(ConnectionError):
            future.result(0.5)
    finally:
        bridge.stop()


def test_ping_and_env_reach_the_add_on(link):
    bridge, connect, _, _ = link
    vscode = connect()
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)
    bridge.ping()
    bridge.send_env({"META_API_KEY": "test-value"}, ["C:\\py"])
    assert vscode.receive() == {"type": "ping"}
    assert vscode.receive() == {"type": "env", "set": {"META_API_KEY": "test-value"},
                                "path_prepend": ["C:\\py"]}


def test_disconnect_calls_on_closed_once(link):
    bridge, connect, _, closed = link
    vscode = connect()
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)
    pending = bridge.send_op(Call("save_file", {"path": "hello.py"}))
    vscode.close()
    assert wait_for(lambda: closed == [1])
    time.sleep(0.1)
    assert closed == [1]
    assert not bridge.connected
    with pytest.raises(ConnectionError):
        pending.result(1)


def test_the_link_is_used_once(link):
    bridge, connect, _, closed = link
    first = connect()
    first.hello(bridge.token)
    assert bridge.wait_connected(3)
    first.close()
    assert wait_for(lambda: closed == [1])
    again = connect_or_refused(bridge)
    assert again


def connect_or_refused(bridge: Bridge) -> bool:
    """True when a new add-on can't get in: refused at connect, or dropped after hello."""
    try:
        client = FakeExtension(bridge.port)
    except OSError:
        return True
    try:
        client.hello(bridge.token)
        return client.is_dropped()
    except OSError:
        return True
    finally:
        client.close()


def test_stop_does_not_call_on_closed(link):
    bridge, connect, _, closed = link
    vscode = connect()
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)
    bridge.stop()
    assert vscode.is_dropped()
    time.sleep(0.1)
    assert closed == []


def test_no_hello_means_not_connected():
    bridge = Bridge(on_state=lambda s: None, on_closed=lambda: None)
    bridge.start()
    try:
        started = time.monotonic()
        assert bridge.wait_connected(0.2) is False
        assert time.monotonic() - started < 1
    finally:
        bridge.stop()



def test_close_asks_the_add_on_to_save_and_close_its_window(link):
    bridge, connect, _, closed = link
    vscode = connect()
    vscode.hello(bridge.token)
    assert bridge.wait_connected(3)
    assert bridge.close_window() is True
    assert vscode.receive() == {"type": "close"}
    vscode.close()
    time.sleep(0.2)
    assert closed == []                      # the program closed it, so no "VS Code was closed"
