"""The Python and TypeScript ends of the link must name every message and field the same way."""
from __future__ import annotations

import re
from pathlib import Path

from app.vscode import protocol

PROTOCOL_TS = Path(__file__).resolve().parents[2] / "extensions" / "vscode" / "src" / "protocol.ts"


def _ts_interface(source: str, name: str) -> set[str]:
    """The field names of one `export interface <name> { ... }` block."""
    match = re.search(rf"export interface {name}\b[^{{]*\{{(.*?)\n\}}", source, re.S)
    assert match, f"protocol.ts has no interface {name}"
    return set(re.findall(r"^\s+(\w+)\??:", match.group(1), re.M))


def test_protocol_names_match_the_extension():
    source = PROTOCOL_TS.read_text(encoding="utf-8")
    assert re.search(rf"PROTOCOL_VERSION\s*=\s*{protocol.PROTOCOL_VERSION}\b", source)
    for kind, fields in protocol.MESSAGES.items():
        interface = protocol.TS_NAMES[kind]
        assert _ts_interface(source, interface) == {"type", *fields}, kind
        assert re.search(rf'type:\s*"{kind}"', source), kind
    for interface, fields in protocol.PARTS.items():
        assert _ts_interface(source, interface) == set(fields), interface
    assert re.search(rf"OUTPUT_LIMIT\s*=\s*{protocol.OUTPUT_LIMIT}\b", source)


def test_the_check_finds_a_missing_field(tmp_path):
    source = PROTOCOL_TS.read_text(encoding="utf-8")
    broken = source.replace("  saved: boolean;", "  isSaved: boolean;")
    assert broken != source
    assert _ts_interface(broken, "FileState") != set(protocol.PARTS["FileState"])
