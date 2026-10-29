// Small pieces of the add-on that need no VS Code, so they can be tested with plain Node.

import * as path from "node:path";

const ESCAPES = new RegExp(
  [
    "\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)", // terminal titles and shell-integration marks
    "\\x1b\\[[0-?]*[ -/]*[@-~]", // colours, cursor moves
    "\\x1b[@-Z\\\\-_]", // other two-character codes
  ].join("|"),
  "g",
);

export function stripAnsi(text: string): string {
  return text.replace(ESCAPES, "").replace(/\r\n/g, "\n");
}

// Keeps the first `limit` characters of a run's output, colour codes removed. Chunks may split a
// colour code, so a little raw text is kept and cleaned as a whole.
export class OutputClip {
  private raw = "";
  private full = false;

  constructor(private readonly limit: number) {}

  add(chunk: string): void {
    if (this.full) {
      return;
    }
    this.raw += chunk;
    if (stripAnsi(this.raw).length >= this.limit || this.raw.length > this.limit * 16) {
      this.raw = stripAnsi(this.raw).slice(0, this.limit);
      this.full = true;
    }
  }

  get text(): string {
    return this.full ? this.raw : stripAnsi(this.raw).slice(0, this.limit);
  }
}

function norm(p: string): string {
  return path.win32.normalize(p).replace(/[\\/]+$/, "").toLowerCase();
}

export function sameFolder(a: string, b: string): boolean {
  return norm(a) === norm(b);
}

// The absolute path of `rel` inside `folder`, or null when it is not a plain relative path that
// stays inside the folder. The add-on never reads or writes anywhere else.
export function insideFolder(folder: string, rel: string): string | null {
  if (!rel || path.win32.isAbsolute(rel) || /^[a-zA-Z]:/.test(rel)) {
    return null;
  }
  const full = path.win32.resolve(folder, rel);
  const back = path.win32.relative(folder, full);
  if (!back || back.startsWith("..") || path.win32.isAbsolute(back)) {
    return null;
  }
  return full;
}

// A file's name as the program knows it: its path inside the folder, with forward slashes.
export function relativeInside(folder: string, full: string): string | null {
  const back = path.win32.relative(folder, full);
  if (!back || back.startsWith("..") || path.win32.isAbsolute(back)) {
    return null;
  }
  return back.split(path.win32.sep).join("/");
}

// VS Code's own rule for the editor's line height, then the window zoom (each step is x1.2).
export function lineHeightPx(fontSize: number, setting: number, zoomLevel: number, isMac: boolean): number {
  let height = setting;
  if (height === 0) {
    height = (isMac ? 1.5 : 1.35) * fontSize;
  } else if (height < 8) {
    height = height * fontSize;
  }
  return Math.max(8, Math.round(height)) * Math.pow(1.2, zoomLevel);
}

// A terminal command that runs Python: `python x.py`, `py x.py`, or a full path to python.exe as
// the Run button sends it. Other commands (cls, pip install) never replace the last run.
const PYTHON = /(?:^|[\s&;|("'\/\\])(?:python3?|py)(?:\.exe)?["']?(?=\s|$)/i;

export function isPythonRun(command: string): boolean {
  return PYTHON.test(command);
}

// The answers to type into a running program, one per line. A newline at the very end only ends
// the last answer.
export function inputLines(text: string): string[] {
  if (text === "") {
    return [];
  }
  const lines = text.split(/\r?\n/);
  if (lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines;
}

export class LineReader {
  private rest = "";

  push(chunk: string): string[] {
    const parts = (this.rest + chunk).split("\n");
    this.rest = parts.pop() ?? "";
    return parts.filter((line) => line.trim() !== "");
  }
}

// Runs `fn` at once on the first poke, then at most once per `ms`; a poke during the wait is
// never lost, it runs when the wait ends.
export class Throttle {
  private last = -Infinity;
  private timer: NodeJS.Timeout | undefined;

  constructor(
    private readonly fn: () => void,
    private readonly ms: number,
  ) {}

  poke(): void {
    if (this.timer) {
      return;
    }
    const wait = this.last + this.ms - Date.now();
    if (wait <= 0) {
      this.fire();
    } else {
      this.timer = setTimeout(() => {
        this.timer = undefined;
        this.fire();
      }, wait);
    }
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
  }

  private fire(): void {
    this.last = Date.now();
    this.fn();
  }
}
