"""The VS Code check menu: pure rules over a snapshot of the lesson's files, problems and last run.

Code checks read the structure Python sees (`ast`), so every right way of writing a step passes. A check
says "Not yet" only when it can name what differs: a name with a slip in it, a wrong value, a near-miss
text, a failed run, or a saved file Python cannot read. Until the learner's work shows one of those it
waits, so a step never opens with a "Not yet". Files are read as saved on disk, and a file the editor
holds unsaved changes for never counts as a mistake. A line Python cannot read does not hide the rest of
the file: each top-level statement that parses on its own still counts, so finished steps stay ticked.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.types import CheckKind, Param, Verdict
from app.vscode.snapshot import Run, VsSnapshot, clean_path

MAX_WORDS = 20
KEY_LINE = "Not yet: keep your key out of the code. Use the META_API_KEY setting."
MERGE = 6            # top-level statements a broken file's reader joins while looking for a part that parses
FIND_LIMIT = 200     # places per piece the near-miss search looks at
_KEY = re.compile(r"[A-Za-z0-9_\-]{32,}")
_LATER_PART = re.compile(r"(?:else|elif|except|finally|case)\b|[)\]}]")
_STRING_OR_COMMENT = re.compile(
    r"(?P<q>\"\"\"|''')(?:\\.|(?!(?P=q)).)*(?:(?P=q)|\Z)"
    r"|\"(?:\\.|[^\"\\\n])*(?:\"|(?=\n)|\Z)"
    r"|'(?:\\.|[^'\\\n])*(?:'|(?=\n)|\Z)"
    r"|(?P<c>#[^\n]*)",
    re.S,
)
_TOKEN = re.compile(r"\"([^\"]*)\"|'([^']*)'|(\S+)")
_UNKNOWN = object()
_MATH = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
         ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}


# ---- reading the code ----

@dataclass(frozen=True)
class _Code:
    modules: tuple[ast.Module, ...]    # the whole file, or each part of a broken file that parses
    error: SyntaxError | None          # why the whole file does not parse


@lru_cache(maxsize=64)
def _parse(text: str) -> _Code:
    try:
        return _Code((ast.parse(text),), None)
    except SyntaxError as exc:
        error = exc
    except ValueError as exc:          # a null character
        return _Code((), SyntaxError(str(exc)))
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines)
              if line[:1].strip() and line[0] != "#" and not _LATER_PART.match(line)]
    modules, i = [], 0
    while i < len(starts):
        for j in range(i + 1, min(i + MERGE, len(starts)) + 1):
            end = starts[j] if j < len(starts) else len(lines)
            try:
                modules.append(ast.parse("".join(lines[starts[i]:end])))
            except (SyntaxError, ValueError):
                continue
            i = j
            break
        else:
            i += 1
    return _Code(tuple(modules), error)


def _nodes(code: _Code) -> Iterator[ast.AST]:
    for module in code.modules:
        yield from ast.walk(module)


def _top_level(code: _Code) -> Iterator[ast.stmt]:
    """Statements that run at the file's top level, in order: inside if, for, with and try, not def or class."""
    def walk(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
        for stmt in body:
            yield stmt
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for part in ("body", "orelse", "finalbody"):
                yield from walk(getattr(stmt, part, ()))
            for inner in (*getattr(stmt, "handlers", ()), *getattr(stmt, "cases", ())):
                yield from walk(inner.body)
    for module in code.modules:
        yield from walk(module.body)


@lru_cache(maxsize=64)
def _split_comments(text: str) -> tuple[str, str]:
    """The file without its # comments, and the comments. Quotes are respected, even unclosed ones."""
    code, comments, last = [], [], 0
    for m in _STRING_OR_COMMENT.finditer(text):
        if m.group("c") is not None:
            code.append(text[last:m.start()])
            comments.append(m.group("c"))
            last = m.end()
    code.append(text[last:])
    return "".join(code), "\n".join(comments)


def _value(node: ast.AST) -> Any:
    """The number or text a simple expression like 5, "Pune", 2 + 3 or -1 comes to, else _UNKNOWN."""
    if isinstance(node, ast.Constant):
        v = node.value
        return v if isinstance(v, (int, float, str)) and not isinstance(v, bool) else _UNKNOWN
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _value(node.operand)
        return _UNKNOWN if not _is_number(v) else (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, ast.BinOp):
        return _combine(_value(node.left), node.op, _value(node.right))
    return _UNKNOWN


def _combine(a: Any, op: ast.operator, b: Any) -> Any:
    numbers = _is_number(a) and _is_number(b)
    texts = isinstance(a, str) and isinstance(b, str) and isinstance(op, ast.Add)
    if type(op) not in _MATH or not (numbers or texts):
        return _UNKNOWN
    try:
        return _MATH[type(op)](a, b)
    except ArithmeticError:
        return _UNKNOWN


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same_value(have: Any, want: Any) -> bool:
    if _is_number(want):
        return _is_number(have) and math.isclose(have, want, rel_tol=1e-9, abs_tol=1e-12)
    return isinstance(have, str) and have == want


# ---- names with a slip in them ----

def _slips(a: str, b: str, most: int) -> int:
    """Letters added, dropped, changed or swapped between a and b; anything over `most` reads as most + 1."""
    if abs(len(a) - len(b)) > most:
        return most + 1
    before, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if before is not None and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], before[j - 2] + 1)
        before, prev = prev, cur
    return min(prev[len(b)], most + 1)


def _looks_like(found: str, want: str) -> bool:
    """True when `found` reads like a slip for `want`: other capitals, or a typing slip or two."""
    if found == want:
        return False
    if found.lower() == want.lower():
        return True
    most = 0 if len(want) <= 3 else 1 if len(want) <= 8 else 2
    return most > 0 and _slips(found.lower(), want.lower(), most) <= most


def _slip_for(found: Iterable[str], want: str) -> str | None:
    return next((f for f in found if _looks_like(f, want)), None)


def _fewest_slips_inside(p: str, t: str) -> int:
    """Fewest slips between p and any stretch of t."""
    prev = [0] * (len(t) + 1)
    for i in range(1, len(p) + 1):
        cur = [i] + [0] * len(t)
        for j in range(1, len(t) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (p[i - 1] != t[j - 1]))
        prev = cur
    return min(prev)


def _near(want: str, code: str) -> bool:
    """True when the code holds something within a slip or two of `want`, ignoring capitals.

    A match with at most k slips holds one of k + 1 pieces of `want` exactly, so only the places
    where a piece appears are compared letter by letter."""
    p, t = want.lower(), code.lower()
    most = 0 if len(p) < 6 else max(1, len(p) // 10)
    if most == 0:
        return p in t
    size = len(p) // (most + 1)
    for k in range(most + 1):
        start = k * size
        piece = p[start:start + size] if k < most else p[start:]
        pos, looked = t.find(piece), 0
        while pos >= 0 and looked < FIND_LIMIT:
            window = t[max(0, pos - start - most):pos - start + len(p) + most]
            if _fewest_slips_inside(p, window) <= most:
                return True
            pos, looked = t.find(piece, pos + 1), looked + 1
    return False


# ---- answers ----

def _not_yet(code: str, text: str) -> Verdict:
    words = text.split()
    if len(words) > MAX_WORDS:
        words = words[:MAX_WORDS]
        words[-1] += "…"
    return Verdict.wrong(code, " ".join(words))


def _show(v: Any) -> str:
    shown = json.dumps(v, ensure_ascii=False)
    return shown if len(shown) <= 40 else shown[:39] + "…"


def _inputs(n: int) -> str:
    return "no inputs" if n == 0 else "1 input" if n == 1 else f"{n} inputs"


def _syntax(name: str, error: SyntaxError) -> Verdict:
    where = f"line {error.lineno} of {name}" if error.lineno else name
    return _not_yet("syntax", f"Not yet: Python can't read {where}: {error.msg}")


def _code_check(snap: VsSnapshot, path: str, find: Callable[[_Code], Verdict | None]) -> Verdict:
    """The shape every code check shares. `find` looks through the parts of the file Python can read and
    answers right, Not yet, or None when it finds nothing of the step."""
    got = snap.file(path)
    if got is None:
        return Verdict.waiting()
    name, state = got
    if _holds_key(state.text):
        return Verdict.wrong("key", KEY_LINE)
    code = _parse(state.text)
    verdict = find(code)
    if verdict is not None:
        return verdict
    if code.error is not None and state.saved:
        return _syntax(name, code.error)
    return Verdict.waiting()


# ---- the checks ----

def _file_exists(snap: VsSnapshot, args: Mapping) -> Verdict:
    if snap.file(args["path"]) is not None:
        return Verdict.right()
    want = clean_path(args["path"])
    want_name = want.rsplit("/", 1)[-1].lower()
    want_stem = want_name.split(".")[0]
    for name in snap.files:
        found = clean_path(name).rsplit("/", 1)[-1].lower()
        if (want_stem and found.split(".")[0] == want_stem) or _looks_like(found, want_name):
            return _not_yet(f"named:{name}", f"Not yet: the file is named {name}. Name it {want} exactly.")
    return Verdict.waiting()


def _param_count(d: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    a = d.args
    return len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs) + (a.vararg is not None) + (a.kwarg is not None)


def _defines_function(snap: VsSnapshot, args: Mapping) -> Verdict:
    want, count = args["name"], args.get("params")

    def find(code: _Code) -> Verdict | None:
        defs = [n for n in _nodes(code) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        mine = [d for d in defs if d.name == want]
        if any(count is None or _param_count(d) == count for d in mine):
            return Verdict.right()
        if mine:
            return _not_yet(f"params:{want}", f"Not yet: {want} takes {_inputs(_param_count(mine[0]))}. "
                                              f"Give it {_inputs(count)} in its brackets.")
        slip = _slip_for((d.name for d in defs), want)
        if slip:
            return _not_yet(f"named:{slip}", f"Not yet: it's named {slip}. Python reads capitals and "
                                             f"spelling exactly: call it {want}.")
        return None
    return _code_check(snap, args["path"], find)


def _calls(snap: VsSnapshot, args: Mapping) -> Verdict:
    want = args["name"]

    def find(code: _Code) -> Verdict | None:
        called, mentioned = [], set()
        for n in _nodes(code):
            if isinstance(n, ast.Call):
                func = n.func
                called.append(func.id if isinstance(func, ast.Name)
                              else func.attr if isinstance(func, ast.Attribute) else "")
            elif isinstance(n, ast.Name):
                mentioned.add(n.id)
            elif isinstance(n, ast.Attribute):
                mentioned.add(n.attr)
        if want in called:
            return Verdict.right()
        slip = _slip_for(called, want)
        if slip:
            return _not_yet(f"named:{slip}", f"Not yet: you wrote {slip}. Python reads capitals and "
                                             f"spelling exactly: write {want}.")
        if want in mentioned:
            return _not_yet(f"not_called:{want}", f"Not yet: {want} is there but never run. "
                                                  f"Add brackets after it: {want}(...)")
        return None
    return _code_check(snap, args["path"], find)


def _prints(snap: VsSnapshot, args: Mapping) -> Verdict:
    want = args["name"]

    def find(code: _Code) -> Verdict | None:
        used, braced = [], False        # names inside print(...), and "{name}" left in plain quotes
        for n in _nodes(code):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
                for arg in [*n.args, *(k.value for k in n.keywords)]:
                    for part in ast.walk(arg):
                        if isinstance(part, ast.Name):
                            used.append(part.id)
                        elif isinstance(part, ast.Constant) and isinstance(part.value, str):
                            braced = braced or "{" + want + "}" in part.value
        if want in used:
            return Verdict.right()
        if braced:
            return _not_yet(f"no_f:{want}", f"Not yet: put f before the quotes, so Python fills in {{{want}}}.")
        slip = _slip_for(used, want)
        if slip:
            return _not_yet(f"named:{slip}", f"Not yet: you wrote {slip}. Python reads capitals and "
                                             f"spelling exactly: write {want}.")
        return None
    return _code_check(snap, args["path"], find)


def _imports(snap: VsSnapshot, args: Mapping) -> Verdict:
    want = args["module"]

    def find(code: _Code) -> Verdict | None:
        found = []
        for n in _nodes(code):
            if isinstance(n, ast.Import):
                found += [alias.name for alias in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                found.append(n.module)
        if any(f == want or f.startswith(want + ".") for f in found):
            return Verdict.right()
        slip = _slip_for(found, want)
        if slip:
            return _not_yet(f"named:{slip}", f"Not yet: you imported {slip}. The module is spelled {want}.")
        return None
    return _code_check(snap, args["path"], find)


def _assigns(snap: VsSnapshot, args: Mapping) -> Verdict:
    want, value = args["name"], args.get("value")

    def find(code: _Code) -> Verdict | None:
        last: dict[str, Any] = {}       # each top-level name and the value it ends up with
        for stmt in _top_level(code):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        last[target.id] = _value(stmt.value)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        last.update((t.id, _UNKNOWN) for t in target.elts if isinstance(t, ast.Name))
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None and isinstance(stmt.target, ast.Name):
                last[stmt.target.id] = _value(stmt.value)
            elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
                last[stmt.target.id] = _combine(last.get(stmt.target.id, _UNKNOWN), stmt.op, _value(stmt.value))
        if want in last:
            have = last[want]
            if value is None or _same_value(have, value):
                return Verdict.right()
            now = "" if have is _UNKNOWN else f" Right now it's {_show(have)}."
            return _not_yet(f"value:{want}", f"Not yet: set {want} to {_show(value)}.{now}")
        inside = {t.id for n in _nodes(code) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  for s in ast.walk(n) if isinstance(s, (ast.Assign, ast.AnnAssign))
                  for t in (s.targets if isinstance(s, ast.Assign) else [s.target]) if isinstance(t, ast.Name)}
        if want in inside:
            return _not_yet(f"inside:{want}", f"Not yet: {want} is set inside a function. "
                                              f"Set it at the top level, outside any def.")
        slip = _slip_for([*last, *sorted(inside)], want)
        if slip:
            return _not_yet(f"named:{slip}", f"Not yet: you named it {slip}. Python reads capitals and "
                                             f"spelling exactly: call it {want}.")
        return None
    return _code_check(snap, args["path"], find)


def _uses_text(snap: VsSnapshot, args: Mapping) -> Verdict:
    got = snap.file(args["path"])
    if got is None or not got[1].text.strip():
        return Verdict.waiting()
    if _holds_key(got[1].text):
        return Verdict.wrong("key", KEY_LINE)
    want = args["text"]
    code, comments = _split_comments(got[1].text)
    if want in code:
        return Verdict.right()
    if want in comments:
        return _not_yet("in_comment", "Not yet: that's in a comment (after #), so Python skips it. "
                                      "Put it in the code.")
    if _near(want, code):
        exact = want if len(want.split()) <= 8 else "the text in the lesson"
        return _not_yet("near", f"Not yet: close, but it must match exactly, capitals too: {exact}")
    return Verdict.waiting()


def _failed(run: Run) -> bool:
    if run.exit_code is None:
        return "Traceback (most recent call last)" in run.output
    return run.exit_code != 0


def _error_line(run: Run) -> Verdict:
    lines = [line.strip() for line in run.output.splitlines() if line.strip()]
    if lines:
        return _not_yet("error", f"Not yet: Python stopped with: {lines[-1]}")
    return _not_yet("error", f"Not yet: the program stopped with an error (exit code {run.exit_code}).")


def _command_files(command: str) -> list[str]:
    return [clean_path(next(g for g in m.groups() if g is not None)) for m in _TOKEN.finditer(command)]


def _run_ok(snap: VsSnapshot, args: Mapping) -> Verdict:
    run = snap.run
    if run is None or not run.finished:
        return Verdict.waiting()
    path = args.get("path")
    if path is not None:
        want, tokens = clean_path(path), _command_files(run.command)
        if not any(t.lower() == want.lower() or t.lower().endswith("/" + want.lower()) for t in tokens):
            other = next((t.rsplit("/", 1)[-1] for t in tokens if t.lower().endswith(".py")), None)
            text = (f"Not yet: that ran {other}. Run {want} instead." if other
                    else f"Not yet: run {want} itself, like this: python {want}")
            return _not_yet("other_file", text)
    if _failed(run):
        return _error_line(run)
    if args.get("printed") and not run.output.strip():
        return _not_yet("no_output", "Not yet: it ran but printed nothing. Add a print(...) line.")
    return Verdict.right()


def _run_output(snap: VsSnapshot, args: Mapping) -> Verdict:
    run = snap.run
    if run is None or not run.finished:
        return Verdict.waiting()
    if args["contains"].lower() in run.output.lower():
        return Verdict.right()
    if _failed(run):
        return _error_line(run)
    return _not_yet("missing_text", f"Not yet: it ran, but the output should show: {args['contains']}")


def _no_problems(snap: VsSnapshot, args: Mapping) -> Verdict:
    got = snap.file(args["path"])
    if got is None or not got[1].saved:
        return Verdict.waiting()
    name, state = got
    if _holds_key(state.text):
        return Verdict.wrong("key", KEY_LINE)
    errors = sorted((p for p in snap.problems
                     if p.severity == "error" and clean_path(p.path).lower() == clean_path(name).lower()),
                    key=lambda p: p.line)
    if errors:
        return _not_yet("problem", f"Not yet: VS Code marks line {errors[0].line}: {errors[0].message}")
    code = _parse(state.text)
    if code.error is not None and name.lower().endswith(".py"):
        return _syntax(name, code.error)
    return Verdict.right()


def _looks_like_key(run: str) -> bool:
    return any(c.isalpha() for c in run) and any(c.isdigit() for c in run)


def _holds_key(text: str) -> bool:
    """A pasted key anywhere in the file fails every check that reads it, not only no_key_in_code."""
    return any(_looks_like_key(run) for run in _KEY.findall(text))


def _no_key_in_code(snap: VsSnapshot, args: Mapping) -> Verdict:
    got = snap.file(args["path"])
    if got is None or not got[1].text.strip():
        return Verdict.waiting()
    if _holds_key(got[1].text):
        return Verdict.wrong("key", KEY_LINE)
    return Verdict.right()


_PATH = Param("path", "path")

CHECKS: dict[str, CheckKind] = {c.name: c for c in (
    CheckKind("file_exists", (_PATH,), _file_exists, "The file exists"),
    CheckKind("defines_function", (_PATH, Param("name", "text"), Param("params", "int", required=False)),
              _defines_function, "The file defines a function with that name (and that many inputs)"),
    CheckKind("calls", (_PATH, Param("name", "text")), _calls, "The file calls that function or method"),
    CheckKind("prints", (_PATH, Param("name", "text")), _prints,
              "The file prints something made with that name, such as f\"Hi {name}\""),
    CheckKind("imports", (_PATH, Param("module", "text")), _imports, "The file imports that module"),
    CheckKind("assigns", (_PATH, Param("name", "text"), Param("value", "value", required=False)), _assigns,
              "The file sets that name at its top level (to that value)"),
    CheckKind("uses_text", (_PATH, Param("text", "text")), _uses_text,
              "The text appears in the file's code, not in a comment"),
    CheckKind("run_ok", (Param("path", "path", required=False), Param("printed", "bool", required=False)),
              _run_ok, "The last run (of that file) finished without an error (and printed something)"),
    CheckKind("run_output", (Param("contains", "text"),), _run_output,
              "The last run printed that text, capitals aside"),
    CheckKind("no_problems", (_PATH,), _no_problems, "The saved file has no errors in VS Code's problems list"),
    CheckKind("no_key_in_code", (_PATH,), _no_key_in_code, "The file holds nothing that looks like a key"),
)}
