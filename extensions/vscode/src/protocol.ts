// The messages the add-on and the Mentora program send each other: one JSON object per line.
// app/vscode/protocol.py names the same messages and fields; tests/vscode/test_protocol_in_step.py
// keeps the two in step.

export const PROTOCOL_VERSION = 1;
export const OUTPUT_LIMIT = 4096; // characters of a run's output kept

// Add-on to program.

export interface Hello {
  type: "hello";
  token: string;
  version: number;
}

export interface FileState {
  text: string; // the text saved on disk
  saved: boolean; // false while the editor holds changes not yet saved
}

export interface Active {
  path: string;
  line: number; // 1-based, the cursor's line
  column: number; // 1-based
  visible_from: number; // first line on screen, 1-based
  visible_to: number; // last line on screen, 1-based
  line_height: number; // CSS pixels, window zoom included
  font_size: number; // CSS pixels, window zoom included
}

export interface Problem {
  path: string;
  line: number; // 1-based
  severity: "error" | "warning" | "info" | "hint";
  message: string;
}

export interface Run {
  command: string;
  exit_code: number | null;
  output: string; // the first OUTPUT_LIMIT characters, colour codes removed
  finished: boolean;
}

export interface State {
  type: "state";
  files: Record<string, FileState>;
  active: Active | null;
  problems: Problem[];
  run: Run | null;
}

export interface Done {
  type: "done";
  id: number;
  ok: boolean;
  error: string;
}

// Program to add-on.

export interface Op {
  kind: string;
  args: Record<string, unknown>;
}

export interface Do {
  type: "do";
  id: number;
  op: Op;
}

export interface Ping {
  type: "ping";
}

export interface Env {
  type: "env";
  set: Record<string, string>;
  path_prepend: string[];
}

// Save the lesson's files and close the window.
export interface Close {
  type: "close";
}

export type FromProgram = Do | Ping | Env | Close;
