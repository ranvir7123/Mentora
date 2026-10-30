import assert from "node:assert/strict";
import { test } from "node:test";

import {
  LineReader,
  OutputClip,
  Throttle,
  inputLines,
  insideFolder,
  isPythonRun,
  lessonShell,
  lineHeightPx,
  relativeInside,
  sameFolder,
  stripAnsi,
} from "../helpers";

test("on Windows the run terminal is Windows PowerShell, allowed to load VS Code's run reporting", () => {
  // Command Prompt has no shell integration, and a Restricted script policy would block VS Code's script.
  // Conda's base Python would come first on PATH, and its "(base) " prompt would end every run's output.
  assert.deepEqual(lessonShell("win32", { SystemRoot: "D:\\Win" }), {
    shellPath: "D:\\Win\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    env: { PSExecutionPolicyPreference: "RemoteSigned", CONDA_AUTO_ACTIVATE_BASE: "false", CONDA_CHANGEPS1: "false" },
  });
  assert.equal(lessonShell("win32", {}).shellPath, "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe");
  assert.deepEqual(lessonShell("linux", {}), {});
});

test("colour codes and terminal titles are removed from run output", () => {
  assert.equal(stripAnsi("\x1b[32mHello\x1b[0m world\r\n"), "Hello world\n");
  assert.equal(stripAnsi("\x1b]633;C\x07Hi\x1b]0;title\x1b\\!"), "Hi!");
  assert.equal(stripAnsi("\x1b[?25lplain\x1b[?25h"), "plain");
});

test("run output keeps only the first characters, even when a colour code is split", () => {
  const clip = new OutputClip(10);
  clip.add("\x1b[3");
  clip.add("1mabcdef");
  clip.add("ghijklmnop\x1b[0m");
  assert.equal(clip.text, "abcdefghij");
  const big = new OutputClip(4);
  for (let i = 0; i < 100000; i++) {
    big.add("xyz ");
  }
  assert.equal(big.text, "xyz ");
});

test("a path from the program must stay inside the lesson's folder", () => {
  const folder = "C:\\work\\lesson";
  assert.equal(insideFolder(folder, "hello.py"), "C:\\work\\lesson\\hello.py");
  assert.equal(insideFolder(folder, "src/app.py"), "C:\\work\\lesson\\src\\app.py");
  assert.equal(insideFolder(folder, "../other/secret.txt"), null);
  assert.equal(insideFolder(folder, "C:\\Windows\\win.ini"), null);
  assert.equal(insideFolder(folder, "\\\\server\\share\\x"), null);
  assert.equal(insideFolder(folder, "src/../../x.py"), null);
  assert.equal(insideFolder(folder, ""), null);
});

test("a file's name is its path inside the folder, with forward slashes", () => {
  const folder = "C:\\work\\lesson";
  assert.equal(relativeInside(folder, "C:\\work\\lesson\\src\\app.py"), "src/app.py");
  assert.equal(relativeInside(folder, "c:\\WORK\\lesson\\hello.py"), "hello.py");
  assert.equal(relativeInside(folder, "C:\\work\\other\\hello.py"), null);
  assert.equal(relativeInside(folder, "C:\\work\\lesson"), null);
});

test("the same folder is recognised whatever its spelling", () => {
  assert.equal(sameFolder("C:\\Users\\A\\work\\x", "c:/users/a/work/x/"), true);
  assert.equal(sameFolder("C:\\Users\\A\\work\\x", "C:\\Users\\A\\work\\y"), false);
});

test("the editor's line height follows VS Code's own rule and the window zoom", () => {
  assert.equal(lineHeightPx(14, 0, 0, false), 19); // 14 x 1.35 rounded
  assert.equal(lineHeightPx(14, 0, 0, true), 21); // 14 x 1.5
  assert.equal(lineHeightPx(14, 22, 0, false), 22); // pixels as set
  assert.equal(lineHeightPx(14, 1.5, 0, false), 21); // under 8 means times the font size
  assert.ok(Math.abs(lineHeightPx(14, 0, 1, false) - 22.8) < 1e-9); // one zoom step is x1.2
});

test("socket data is split into whole lines", () => {
  const reader = new LineReader();
  assert.deepEqual(reader.push('{"a":1}\n{"b"'), ['{"a":1}']);
  assert.deepEqual(reader.push(':2}\n\n'), ['{"b":2}']);
  assert.deepEqual(reader.push("x"), []);
});

test("state is sent at most once per interval, and the last change is never lost", async () => {
  let calls = 0;
  const throttle = new Throttle(() => {
    calls += 1;
  }, 40);
  throttle.poke();
  assert.equal(calls, 1); // the first change goes at once
  throttle.poke();
  throttle.poke();
  assert.equal(calls, 1);
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(calls, 2); // the later changes go together, once
  throttle.dispose();
});

test("only commands that run Python count as runs", () => {
  assert.equal(isPythonRun("python hello.py"), true);
  assert.equal(isPythonRun("py ask.py"), true);
  assert.equal(isPythonRun("python3 -u hello.py"), true);
  assert.equal(isPythonRun("& C:/dev/.venv/Scripts/python.exe c:/work/lesson/hello.py"), true);
  assert.equal(isPythonRun('cd "c:\work" && python -u "hello.py"'), true);
  assert.equal(isPythonRun("cls"), false);
  assert.equal(isPythonRun("pip install openai"), false);
  assert.equal(isPythonRun("notepad pythonnotes.txt"), false);
});

test("a run's input is typed one answer per line, and a last newline adds no empty answer", () => {
  assert.deepEqual(inputLines("Ranvir"), ["Ranvir"]);
  assert.deepEqual(inputLines("Ranvir\n20\n"), ["Ranvir", "20"]);
  assert.deepEqual(inputLines("Ranvir\r\n\r\n20"), ["Ranvir", "", "20"]);
  assert.deepEqual(inputLines(""), []);
});
