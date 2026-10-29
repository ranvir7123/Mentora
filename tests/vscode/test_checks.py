"""The VS Code checks: every right way of writing a step passes, wrong ways get a "Not yet" naming the
difference, and nothing the learner is still typing counts as a mistake."""
from __future__ import annotations

import pytest

from app.core.types import validate_args
from app.vscode.checks import CHECKS
from app.vscode.ops import OPS
from app.vscode.snapshot import VsSnapshot

KEY_LINE = "Not yet: keep your key out of the code. Use the META_API_KEY setting."


def snap(files: dict[str, str] | None = None, *, saved: bool = True, problems=(), run=None) -> VsSnapshot:
    return VsSnapshot.from_state({
        "files": {path: {"text": text, "saved": saved} for path, text in (files or {}).items()},
        "active": None,
        "problems": [dict(zip(("path", "line", "severity", "message"), p)) for p in problems],
        "run": run,
    })


def ran(command: str, exit_code: int | None = 0, output: str = "", finished: bool = True) -> dict:
    return {"command": command, "exit_code": exit_code, "output": output, "finished": finished}


def judge(kind: str, args: dict, snapshot: VsSnapshot):
    assert validate_args(CHECKS[kind], args) == []
    return CHECKS[kind].run(snapshot, args)


def h(text: str) -> VsSnapshot:
    return snap({"hello.py": text})


# (check, args, snapshot) for three right ways per check.
RIGHT = [
    ("file_exists", {"path": "hello.py"}, snap({"hello.py": ""})),
    ("file_exists", {"path": "hello.py"}, snap({"Hello.py": "print(1)\n"})),
    ("file_exists", {"path": "src/app.py"}, snap({"src/app.py": "", "other.py": ""})),

    ("defines_function", {"path": "hello.py", "name": "greet", "params": 1},
     h("def greet(name):\n    print(name)\n")),
    ("defines_function", {"path": "hello.py", "name": "greet", "params": 1},
     h('def greet(person):\n    """Say hello to someone."""\n    return f"Hi {person}"\n')),
    ("defines_function", {"path": "hello.py", "name": "greet"},
     h("def greet(name='you', loud=False):\n    pass\n")),

    ("calls", {"path": "hello.py", "name": "print"}, h('print("Hello")\n')),
    ("calls", {"path": "hello.py", "name": "print"}, h("x = 5\nif x:\n    print(f'Hi {x}')\n")),
    ("calls", {"path": "ask.py", "name": "create"},
     snap({"ask.py": 'r = client.responses.create(model="muse-spark-1.3", input="Hi")\n'})),

    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import openai\n"})),
    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import os\nfrom openai import OpenAI\n"})),
    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import openai as ai\n"})),

    ("assigns", {"path": "hello.py", "name": "name"}, h('name = "Ranvir"\n')),
    ("assigns", {"path": "hello.py", "name": "name"}, h('name = input("Your name? ")\n')),
    ("assigns", {"path": "hello.py", "name": "name"}, h('name: str = "Asha"\n')),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = 5\n")),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = 2 + 3\n")),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = 1\ncount: int = 5\n")),
    ("assigns", {"path": "hello.py", "name": "city", "value": "Pune"}, h("city = 'Pune'\n")),

    ("prints", {"path": "hello.py", "name": "name"}, h('name = "Asha"\nprint(f"Nice to meet you, {name}!")\n')),
    ("prints", {"path": "hello.py", "name": "name"}, h('name = "Asha"\nprint("Hello, " + name + "!")\n')),
    ("prints", {"path": "hello.py", "name": "name"}, h('name = "Asha"\nprint("Hello,", name.title())\n')),

    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": 'client = OpenAI(base_url="https://api.meta.ai/v1")\n'})),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": "BASE = 'https://api.meta.ai/v1'  # Meta's address\n"})),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": 'client = OpenAI(\n    base_url = "https://api.meta.ai/v1",\n)\n'})),

    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'import os\nclient = OpenAI(api_key=os.environ["META_API_KEY"])\n'})),
    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": "from os import getenv\nclient = OpenAI(api_key=getenv('META_API_KEY'))\n"})),
    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'import os\nkey = os.environ.get("META_API_KEY")\nclient = OpenAI(api_key=key)\n'})),

    ("run_ok", {"path": "hello.py"}, snap({"hello.py": ""}, run=ran("python hello.py", 0, "Hello\n"))),
    ("run_ok", {"path": "hello.py"},
     snap({"hello.py": ""}, run=ran("& C:/py/python.exe c:/work/lesson/hello.py", 0, ""))),
    ("run_ok", {"path": "hello.py", "printed": True}, snap({"hello.py": ""}, run=ran("py hello.py", 0, "Hi\n"))),

    ("run_output", {"contains": "hello"}, snap(run=ran("python hello.py", 0, "Hello, Asha!\n"))),
    ("run_output", {"contains": "hello"}, snap(run=ran("python hello.py", 0, "hello world\n"))),
    ("run_output", {"contains": "Hello, Asha"}, snap(run=ran("python hello.py", 0, "Your name? Hello, ASHA\n"))),

    ("no_problems", {"path": "hello.py"}, h('print("Hi")\n')),
    ("no_problems", {"path": "hello.py"},
     snap({"hello.py": "import os\n"}, problems=[("hello.py", 1, "warning", '"os" is not accessed')])),
    ("no_problems", {"path": "hello.py"},
     snap({"hello.py": "x = 1\n", "other.py": "x = (\n"}, problems=[("other.py", 1, "error", '"(" was not closed')])),

    ("no_key_in_code", {"path": "ask.py"}, snap({"ask.py": 'key = os.environ["META_API_KEY"]\n'})),
    ("no_key_in_code", {"path": "ask.py"},
     snap({"ask.py": 'client = OpenAI(api_key=os.environ["META_API_KEY"], base_url="https://api.meta.ai/v1")\n'})),
    ("no_key_in_code", {"path": "ask.py"}, snap({"ask.py": 'import os\nprint("A short friendly string")\n'})),
]

# (check, args, snapshot, code the Not yet carries) for three wrong ways per check.
WRONG = [
    ("file_exists", {"path": "hello.py"}, snap({"helo.py": ""}), "named:helo.py"),
    ("file_exists", {"path": "hello.py"}, snap({"hello.txt": ""}), "named:hello.txt"),
    ("file_exists", {"path": "hello.py"}, snap({"hello.py.py": ""}), "named:hello.py.py"),

    ("defines_function", {"path": "hello.py", "name": "greet", "params": 1}, h("def greet():\n    pass\n"),
     "params:greet"),
    ("defines_function", {"path": "hello.py", "name": "greet", "params": 1}, h("def Greet(name):\n    pass\n"),
     "named:Greet"),
    ("defines_function", {"path": "hello.py", "name": "greet", "params": 1}, h("def greet(name)\n    pass\n"),
     "syntax"),

    ("calls", {"path": "hello.py", "name": "print"}, h('Print("Hello")\n'), "named:Print"),
    ("calls", {"path": "hello.py", "name": "print"}, h('prnt("Hello")\n'), "named:prnt"),
    ("calls", {"path": "hello.py", "name": "print"}, h("print\n"), "not_called:print"),

    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import OpenAI\n"}), "named:OpenAI"),
    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "from open_ai import OpenAI\n"}),
     "named:open_ai"),
    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import opneai\n"}), "named:opneai"),

    ("assigns", {"path": "hello.py", "name": "name"}, h('Name = "Ranvir"\n'), "named:Name"),
    ("assigns", {"path": "hello.py", "name": "name"}, h('def f():\n    name = "x"\n'), "inside:name"),
    ("assigns", {"path": "hello.py", "name": "name"}, h('nmae = "x"\n'), "named:nmae"),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = 6\n"), "value:count"),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = '5'\n"), "value:count"),
    ("assigns", {"path": "hello.py", "name": "count", "value": 5}, h("count = 5\ncount = 7\n"), "value:count"),

    ("prints", {"path": "hello.py", "name": "name"}, h('name = "Asha"\nprint("Hello, {name}!")\n'), "no_f:name"),
    ("prints", {"path": "hello.py", "name": "name"}, h("name = 'Asha'\nprint('Hi ' + '{name}')\n"), "no_f:name"),
    ("prints", {"path": "hello.py", "name": "name"}, h('name = "Asha"\nprint(f"Hello, {Name}!")\n'), "named:Name"),

    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": '# base_url="https://api.meta.ai/v1"\nclient = OpenAI()\n'}), "in_comment"),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": 'client = OpenAI(base_url="http://api.meta.ai/v1")\n'}), "near"),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"},
     snap({"ask.py": 'client = OpenAI(base_url="https://API.meta.ai/v2")\n'}), "near"),

    ("run_ok", {"path": "hello.py"},
     snap({"hello.py": ""}, run=ran("python hello.py", 1,
                                    "Traceback (most recent call last):\n  File \"hello.py\", line 2\n"
                                    "NameError: name 'nme' is not defined\n")), "error"),
    ("run_ok", {"path": "hello.py"}, snap({"hello.py": ""}, run=ran("python other.py", 0, "")), "other_file"),
    ("run_ok", {"path": "hello.py", "printed": True}, snap({"hello.py": ""}, run=ran("python hello.py", 0, "  \n")),
     "no_output"),
    # The learner closed the terminal while the program waited at input(): it never finished.
    ("run_ok", {"path": "hello.py", "printed": True},
     snap({"hello.py": ""}, run=ran("python hello.py", None, "Hello, world!\nWhat is your name? ")), "stopped"),

    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'client = OpenAI(api_key="META_API_KEY")\n'}), "quoted:META_API_KEY"),
    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'import os\nkey = os.environ["META_APIKEY"]\n'}), "named:META_APIKEY"),
    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'import os\nkey = os.getenv("meta_api_key")\n'}), "named:meta_api_key"),

    ("run_output", {"contains": "hello"}, snap(run=ran("python hello.py", 0, "Hi Asha\n")), "missing_text"),
    ("run_output", {"contains": "hello"},
     snap(run=ran("python hello.py", 1, "Traceback (most recent call last):\nSyntaxError: invalid syntax\n")),
     "error"),
    ("run_output", {"contains": "hello"}, snap(run=ran("python hello.py", 0, "")), "missing_text"),

    ("no_problems", {"path": "hello.py"},
     snap({"hello.py": "print(nme)\n"}, problems=[("hello.py", 1, "error", '"nme" is not defined')]), "problem"),
    ("no_problems", {"path": "hello.py"}, h('print("Hi"\n'), "syntax"),
    ("no_problems", {"path": "hello.py"},
     snap({"hello.py": "x = 1\n"}, problems=[("hello.py", 1, "warning", "w"), ("hello.py", 1, "error", "e")]),
     "problem"),

    ("no_key_in_code", {"path": "ask.py"},
     snap({"ask.py": 'client = OpenAI(api_key="LLM|abcdefghijklmnopqrstuvwxyz0123456789ABCD")\n'}), "key"),
    ("no_key_in_code", {"path": "ask.py"}, snap({"ask.py": "KEY = 'sk_abcdefghijklmnopqrstuvwxyz012345'\n"}), "key"),
    ("no_key_in_code", {"path": "ask.py"},
     snap({"ask.py": "# my key: abcdefghijklmnopqrstuvwxyz0123456789\nimport os\n"}), "key"),
]


@pytest.mark.parametrize("kind,args,snapshot", RIGHT)
def test_right_ways_pass(kind, args, snapshot):
    verdict = judge(kind, args, snapshot)
    assert verdict.ok, verdict


@pytest.mark.parametrize("kind,args,snapshot,code", WRONG)
def test_wrong_ways_get_a_not_yet(kind, args, snapshot, code):
    verdict = judge(kind, args, snapshot)
    assert not verdict.ok
    assert verdict.attempted
    assert verdict.code == code
    assert verdict.text.startswith("Not yet: ")
    assert len(verdict.text.split()) <= 20


def test_every_check_has_three_right_and_three_wrong_ways():
    for kind in CHECKS:
        assert sum(k == kind for k, *_ in RIGHT) >= 3, kind
        assert sum(k == kind for k, *_ in WRONG) >= 3, kind


def windows(snapshot: VsSnapshot) -> VsSnapshot:
    """The same files and run as VS Code on Windows saves and shows them: lines end in \\r\\n."""
    crlf = lambda text: text.replace("\n", "\r\n")  # noqa: E731
    run = snapshot.run
    return VsSnapshot.from_state({
        "files": {p: {"text": crlf(f.text), "saved": f.saved} for p, f in snapshot.files.items()},
        "active": None, "problems": [vars(p) for p in snapshot.problems],
        "run": run and {"command": run.command, "exit_code": run.exit_code, "output": crlf(run.output),
                        "finished": run.finished},
    })


@pytest.mark.parametrize("kind,args,snapshot", [case[:3] for case in RIGHT + WRONG])
def test_windows_line_endings_get_the_same_verdict(kind, args, snapshot):
    # VS Code on Windows saves new files with \r\n, and an edit keeps the file's own line endings.
    assert judge(kind, args, windows(snapshot)) == judge(kind, args, snapshot)


@pytest.mark.parametrize("kind,args,snapshot", [
    ("file_exists", {"path": "hello.py"}, snap({"notes.txt": ""})),
    ("defines_function", {"path": "hello.py", "name": "greet"}, h('print("Hi")\n')),
    ("defines_function", {"path": "hello.py", "name": "greet"}, snap({})),
    ("calls", {"path": "hello.py", "name": "print"}, h("x = 1\n")),
    ("imports", {"path": "ask.py", "module": "openai"}, snap({"ask.py": "import os\n"})),
    ("assigns", {"path": "hello.py", "name": "name"}, h('print("Hi")\n')),
    ("prints", {"path": "hello.py", "name": "name"}, h('print("Hello, world!")\nname = "Asha"\n')),
    ("prints", {"path": "hello.py", "name": "name"}, h('greeting = f"Hi {name}"\n')),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"}, snap({"ask.py": "from openai import OpenAI\n"})),
    ("uses_text", {"path": "ask.py", "text": "https://api.meta.ai/v1"}, snap({"ask.py": ""})),
    ("reads_setting", {"path": "ask.py", "name": "META_API_KEY"},
     snap({"ask.py": 'import os\nclient = OpenAI(base_url="https://api.meta.ai/v1")\n'})),
    ("run_ok", {"path": "hello.py"}, snap({"hello.py": ""})),
    ("run_ok", {"path": "hello.py"}, snap({"hello.py": ""}, run=ran("python hello.py", None, "Your name? ", False))),
    ("run_output", {"contains": "hello"}, snap(run=ran("python hello.py", None, "", False))),
    ("no_problems", {"path": "hello.py"}, snap({})),
    ("no_key_in_code", {"path": "ask.py"}, snap({"ask.py": ""})),
])
def test_untouched_work_is_waiting_not_wrong(kind, args, snapshot):
    """Before the learner starts a step, the step's check waits quietly instead of saying Not yet."""
    verdict = judge(kind, args, snapshot)
    assert not verdict.ok
    assert not verdict.attempted


def test_unsaved_syntax_errors_are_not_mistakes():
    # The learner is mid-typing: the editor holds `print("Hi"` and VS Code lists the error, but they
    # have not saved. On disk the file is the last saved version, which is broken too.
    typing = snap({"hello.py": 'def greet(name)\n    print("Hi"\n'}, saved=False,
                  problems=[("hello.py", 2, "error", '"(" was not closed')])
    for kind, args in [("no_problems", {"path": "hello.py"}),
                       ("defines_function", {"path": "hello.py", "name": "greet"}),
                       ("calls", {"path": "hello.py", "name": "print"}),
                       ("assigns", {"path": "hello.py", "name": "name"}),
                       ("imports", {"path": "hello.py", "module": "os"})]:
        verdict = judge(kind, args, typing)
        assert not verdict.attempted, (kind, verdict)

    saved = snap({"hello.py": 'def greet(name)\n    print("Hi")\n'}, saved=True,
                 problems=[("hello.py", 1, "error", "Expected \":\"")])
    verdict = judge("no_problems", {"path": "hello.py"}, saved)
    assert verdict.attempted and verdict.code == "problem"
    assert "line 1" in verdict.text


def test_a_broken_line_elsewhere_keeps_finished_steps_ticked():
    text = 'import os\n\ndef greet(name):\n    print(name)\n\nname = "Asha"\nprint(f"Hi {name}"\n'
    broken = h(text)
    assert judge("defines_function", {"path": "hello.py", "name": "greet", "params": 1}, broken).ok
    assert judge("imports", {"path": "hello.py", "module": "os"}, broken).ok
    assert judge("assigns", {"path": "hello.py", "name": "name", "value": "Asha"}, broken).ok


def test_a_key_in_the_code_is_refused():
    pasted = snap({"ask.py": 'from openai import OpenAI\n'
                             'client = OpenAI(api_key="mk-0123456789abcdefghijklmnopqrstuvwxyzABCDEF",\n'  # made up; secret-scan: ok
                             '                base_url="https://api.meta.ai/v1")\n'})
    verdict = judge("no_key_in_code", {"path": "ask.py"}, pasted)
    assert verdict == verdict.wrong("key", KEY_LINE)
    assert "0123456789abcdef" not in verdict.text       # the Not yet line never repeats the key


def test_a_key_in_the_code_fails_every_check_that_reads_the_code():
    pasted = snap({"ask.py": 'import os\nfrom openai import OpenAI\n'
                             'client = OpenAI(base_url="https://api.meta.ai/v1",\n'
                             '                api_key="mk-0123456789abcdefghijklmnopqrstuvwxyzABCDEF")\n'  # made up; secret-scan: ok
                             'print(client)\n'})
    for kind, args in [("imports", {"module": "openai"}), ("calls", {"name": "print"}),
                       ("assigns", {"name": "client"}), ("defines_function", {"name": "ask"}),
                       ("uses_text", {"text": "https://api.meta.ai/v1"}), ("uses_text", {"text": "META_API_KEY"}),
                       ("no_problems", {})]:
        verdict = judge(kind, {"path": "ask.py", **args}, pasted)
        assert verdict == verdict.wrong("key", KEY_LINE), (kind, args)
    assert judge("uses_text", {"path": "ask.py", "text": "META_API_KEY"},
                 snap({"ask.py": 'api_key=os.environ["META_API_KEY"]\n'})).ok


def test_a_failed_run_names_python_s_last_line():
    failed = snap({"hello.py": ""}, run=ran("python hello.py", 1,
                                            "Traceback (most recent call last):\n"
                                            "NameError: name 'nme' is not defined\n"))
    verdict = judge("run_ok", {"path": "hello.py"}, failed)
    assert "NameError: name 'nme' is not defined" in verdict.text


def test_a_file_named_like_another_is_not_mistaken_for_it():
    assert not judge("run_ok", {"path": "hello.py"},
                     snap({"hello.py": ""}, run=ran("python say_hello.py", 0, ""))).ok


def test_a_malformed_state_gives_an_empty_snapshot():
    odd = VsSnapshot.from_state({"files": ["not", "a", "dict"], "active": 5, "problems": None, "run": "x"})
    assert odd.files == {} and odd.active is None and odd.problems == () and odd.run is None
    partly = VsSnapshot.from_state({"files": {"a.py": {"text": 3, "saved": True}, "b.py": {"text": "x", "saved": True}},
                                    "problems": [{"path": "b.py"}, {"path": "b.py", "line": 1, "severity": "error",
                                                                     "message": "m"}]})
    assert set(partly.files) == {"b.py"}
    assert len(partly.problems) == 1


def test_the_operation_menu():
    assert set(OPS) == {"new_file", "write_file", "append_line", "open_file", "save_file", "delete_file", "run_file",
                        "clear_terminal"}
    assert validate_args(OPS["new_file"], {"path": "hello.py"}) == []
    assert validate_args(OPS["write_file"], {"path": "hello.py", "text": "print(1)\n"}) == []
    assert validate_args(OPS["run_file"], {"path": "../outside.py"}) != []
    assert validate_args(OPS["clear_terminal"], {}) == []
    assert validate_args(OPS["run_file"], {"path": "ask.py", "input": "Ranvir"}) == []
    assert validate_args(OPS["run_file"], {"path": "ask.py", "input": ""}) != []
