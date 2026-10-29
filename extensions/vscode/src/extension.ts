// The Project X add-on: tells the Project X program what is happening in a lesson's VS Code window
// (the files, the problems list, the cursor, the last Python run) and carries out its operations.
//
// It wakes up only in a window whose folder is the lesson folder named in the program's link file
// (%LOCALAPPDATA%\projectx\vscode.json, or the file PROJECTX_VSCODE names), connects to 127.0.0.1 on
// the port written there and says hello with the one-time token. It never reads or writes outside
// that folder, and it keeps any terminal settings the program sends in memory only.

import * as fs from "node:fs";
import * as net from "node:net";
import * as path from "node:path";
import * as vscode from "vscode";

import {
  LineReader,
  OutputClip,
  Throttle,
  inputLines,
  insideFolder,
  isPythonRun,
  lineHeightPx,
  relativeInside,
  sameFolder,
} from "./helpers";
import {
  Active,
  FileState,
  FromProgram,
  OUTPUT_LIMIT,
  Op,
  PROTOCOL_VERSION,
  Problem,
  Run,
  State,
} from "./protocol";

const MAX_FILES = 50;
const MAX_FILE_BYTES = 256 * 1024;
const MAX_PROBLEMS = 200;
const SKIP = "{**/.vscode/**,**/__pycache__/**,**/.git/**,**/node_modules/**,**/.venv/**}";
const STATE_EVERY_MS = 100;
const RETRY_MS = 1000;
const RETRIES = 30;
const SHELL_WAIT_MS = 5000;
const OUTPUT_GRACE_MS = 1000;
const STOP_WAIT_MS = 3000;
const POLL_MS = 50;
const CTRL_C = String.fromCharCode(3);
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

interface LinkInfo {
  port: number;
  token: string;
  folder: string;
}

interface Running {
  terminal: vscode.Terminal;
  execution: vscode.TerminalShellExecution;
  ended: boolean;
  run: Run;
  clip: OutputClip;
  reading: Promise<void>;
}

function linkFile(): string {
  return process.env.PROJECTX_VSCODE || path.join(process.env.LOCALAPPDATA ?? "", "projectx", "vscode.json");
}

function readLinkInfo(file: string): LinkInfo | null {
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    if (typeof data.port === "number" && typeof data.token === "string" && typeof data.folder === "string") {
      return { port: data.port, token: data.token, folder: data.folder };
    }
  } catch {
    // no lesson is waiting for this window
  }
  return null;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const SEVERITY: Record<number, Problem["severity"]> = {
  [vscode.DiagnosticSeverity.Error]: "error",
  [vscode.DiagnosticSeverity.Warning]: "warning",
  [vscode.DiagnosticSeverity.Information]: "info",
  [vscode.DiagnosticSeverity.Hint]: "hint",
};

class Link implements vscode.Disposable {
  private socket: net.Socket | undefined;
  private connected = false;
  private lastToken = "";
  private readonly lines = new LineReader();
  private readonly throttle = new Throttle(() => void this.sendState(), STATE_EVERY_MS);
  private building = false;
  private again = false;
  private run: Run | null = null;
  private running: Running | undefined;
  private runTerminal: vscode.Terminal | undefined;
  private listening: vscode.Disposable[] = [];

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly folder: vscode.WorkspaceFolder,
    private readonly log: vscode.LogOutputChannel,
    private readonly file: string,
  ) {}

  // Connect when the link file names this window's folder with a token not used yet. Called at
  // start-up and whenever the link file changes, so a lesson reopened in this window connects again.
  tryConnect(): void {
    if (this.connected || this.socket) {
      return;
    }
    const info = readLinkInfo(this.file);
    if (!info || !sameFolder(info.folder, this.folder.uri.fsPath) || info.token === this.lastToken) {
      return;
    }
    this.lastToken = info.token;
    this.connect(info, RETRIES);
  }

  private connect(info: LinkInfo, retries: number): void {
    const socket = net.createConnection({ host: "127.0.0.1", port: info.port });
    this.socket = socket;
    socket.setEncoding("utf8");
    socket.on("connect", () => {
      this.connected = true;
      this.log.info(`connected to Project X on port ${info.port}`);
      this.write({ type: "hello", token: info.token, version: PROTOCOL_VERSION });
      this.listen();
      void this.sendState();
    });
    socket.on("data", (chunk: string) => {
      for (const line of this.lines.push(chunk)) {
        this.handle(line);
      }
    });
    socket.on("error", (err) => {
      if (!this.connected && retries > 0) {
        socket.destroy();
        this.socket = undefined;
        setTimeout(() => {
          if (!this.socket && !this.connected) {
            this.connect(info, retries - 1);
          }
        }, RETRY_MS);
      } else {
        this.log.warn(`link error: ${err.message}`);
      }
    });
    socket.on("close", () => {
      if (this.socket !== socket) {
        return;
      }
      if (this.connected) {
        this.log.info("Project X closed the link");
      }
      this.connected = false;
      this.socket = undefined;
      this.stopListening();
    });
  }

  private write(message: object): void {
    if (this.socket && this.connected) {
      this.socket.write(JSON.stringify(message) + "\n");
    }
  }

  private handle(line: string): void {
    let message: FromProgram;
    try {
      message = JSON.parse(line);
    } catch {
      return;
    }
    switch (message.type) {
      case "ping":
        void this.sendState();
        break;
      case "do":
        this.perform(message.op).then(
          () => this.write({ type: "done", id: message.id, ok: true, error: "" }),
          (err: unknown) => {
            const error = err instanceof Error ? err.message : String(err);
            this.log.warn(`${message.op?.kind}: ${error}`);
            this.write({ type: "done", id: message.id, ok: false, error });
          },
        ).finally(() => this.throttle.poke());
        break;
      case "env":
        this.setEnv(message.set, message.path_prepend);
        break;
      case "close":
        void this.closeWindow();
        break;
    }
  }

  // Watching the window.

  private listen(): void {
    const poke = () => this.throttle.poke();
    const mine = (uri: vscode.Uri) => relativeInside(this.folder.uri.fsPath, uri.fsPath) !== null;
    const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(this.folder, "**/*"));
    this.listening = [
      watcher,
      watcher.onDidCreate(poke),
      watcher.onDidChange(poke),
      watcher.onDidDelete(poke),
      vscode.workspace.onDidChangeTextDocument((e) => mine(e.document.uri) && poke()),
      vscode.workspace.onDidSaveTextDocument(poke),
      vscode.workspace.onDidCloseTextDocument(poke),
      vscode.workspace.onDidChangeConfiguration(poke),
      vscode.window.onDidChangeActiveTextEditor(poke),
      vscode.window.onDidChangeTextEditorSelection(poke),
      vscode.window.onDidChangeTextEditorVisibleRanges(poke),
      vscode.languages.onDidChangeDiagnostics(poke),
      vscode.window.onDidStartTerminalShellExecution((e) => this.runStarted(e.terminal, e.execution)),
      vscode.window.onDidEndTerminalShellExecution((e) => void this.runEnded(e.execution, e.exitCode)),
    ];
  }

  private stopListening(): void {
    for (const d of this.listening) {
      d.dispose();
    }
    this.listening = [];
    this.throttle.dispose();
  }

  private runStarted(terminal: vscode.Terminal, execution: vscode.TerminalShellExecution): void {
    const command = execution.commandLine.value;
    if (!isPythonRun(command)) {
      return;
    }
    const run: Run = { command, exit_code: null, output: "", finished: false };
    const clip = new OutputClip(OUTPUT_LIMIT);
    const reading = (async () => {
      for await (const chunk of execution.read()) {
        clip.add(chunk);
        run.output = clip.text;
        this.throttle.poke();
      }
    })().catch(() => undefined);
    this.running = { terminal, execution, ended: false, run, clip, reading };
    this.run = run;
    this.throttle.poke();
  }

  private async runEnded(execution: vscode.TerminalShellExecution, exitCode: number | undefined): Promise<void> {
    const running = this.running;
    if (!running || running.execution !== execution) {
      return;
    }
    running.ended = true;
    await Promise.race([running.reading, delay(OUTPUT_GRACE_MS)]);
    running.run.output = running.clip.text;
    running.run.exit_code = exitCode ?? null;
    running.run.finished = true;
    this.throttle.poke();
  }

  // The state the program judges.

  private async sendState(): Promise<void> {
    if (!this.connected) {
      return;
    }
    if (this.building) {
      this.again = true;
      return;
    }
    this.building = true;
    try {
      this.write(await this.buildState());
    } catch (err) {
      this.log.warn(`could not read the lesson's state: ${err instanceof Error ? err.message : err}`);
    } finally {
      this.building = false;
      if (this.again) {
        this.again = false;
        this.throttle.poke();
      }
    }
  }

  private async buildState(): Promise<State> {
    const root = this.folder.uri.fsPath;
    const uris = await vscode.workspace.findFiles(new vscode.RelativePattern(this.folder, "**/*"), SKIP, MAX_FILES);
    const files: Record<string, FileState> = {};
    const decoder = new TextDecoder("utf-8");
    for (const uri of uris.sort((a, b) => a.fsPath.localeCompare(b.fsPath))) {
      const rel = relativeInside(root, uri.fsPath);
      if (rel === null) {
        continue;
      }
      try {
        const stat = await vscode.workspace.fs.stat(uri);
        if (stat.size > MAX_FILE_BYTES) {
          continue;
        }
        const bytes = await vscode.workspace.fs.readFile(uri);
        if (bytes.includes(0)) {
          continue; // not a text file
        }
        const open = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
        files[rel] = { text: decoder.decode(bytes), saved: !open?.isDirty };
      } catch {
        // deleted while we looked
      }
    }

    const problems: Problem[] = [];
    for (const [uri, diagnostics] of vscode.languages.getDiagnostics()) {
      const rel = uri.scheme === "file" ? relativeInside(root, uri.fsPath) : null;
      for (const d of rel === null ? [] : diagnostics) {
        if (problems.length < MAX_PROBLEMS) {
          problems.push({
            path: rel as string,
            line: d.range.start.line + 1,
            severity: SEVERITY[d.severity] ?? "info",
            message: d.message.slice(0, 500),
          });
        }
      }
    }

    return {
      type: "state",
      files,
      active: this.active(),
      problems,
      run: this.run ? { ...this.run } : null,
    };
  }

  private active(): Active | null {
    const editor = vscode.window.activeTextEditor;
    const rel = editor && editor.document.uri.scheme === "file"
      ? relativeInside(this.folder.uri.fsPath, editor.document.uri.fsPath)
      : null;
    if (!editor || rel === null) {
      return null;
    }
    const config = vscode.workspace.getConfiguration("editor", editor.document);
    const zoom = vscode.workspace.getConfiguration("window").get<number>("zoomLevel", 0);
    const fontSize = config.get<number>("fontSize", 14);
    const ranges = editor.visibleRanges;
    const cursor = editor.selection.active;
    return {
      path: rel,
      line: cursor.line + 1,
      column: cursor.character + 1,
      visible_from: (ranges[0]?.start.line ?? 0) + 1,
      visible_to: (ranges[ranges.length - 1]?.end.line ?? 0) + 1,
      line_height: lineHeightPx(fontSize, config.get<number>("lineHeight", 0), zoom, process.platform === "darwin"),
      font_size: fontSize * Math.pow(1.2, zoom),
    };
  }

  // Operations from the plug-in's menu (app/vscode/ops.py).

  private uriOf(args: Record<string, unknown>): vscode.Uri {
    const rel = args.path;
    const full = typeof rel === "string" ? insideFolder(this.folder.uri.fsPath, rel) : null;
    if (full === null) {
      throw new Error(`${String(rel)} is not a file inside the lesson's folder`);
    }
    return vscode.Uri.file(full);
  }

  private textOf(args: Record<string, unknown>): string {
    if (typeof args.text !== "string") {
      throw new Error("the text is missing");
    }
    return args.text;
  }

  private openDoc(uri: vscode.Uri): vscode.TextDocument | undefined {
    return vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
  }

  private async exists(uri: vscode.Uri): Promise<boolean> {
    try {
      await vscode.workspace.fs.stat(uri);
      return true;
    } catch {
      return false;
    }
  }

  private async replaceAll(doc: vscode.TextDocument, text: string): Promise<void> {
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)), text);
    if (!(await vscode.workspace.applyEdit(edit)) || !(await doc.save())) {
      throw new Error(`VS Code could not write ${path.basename(doc.uri.fsPath)}`);
    }
  }

  private async perform(op: Op): Promise<void> {
    const args = op?.args ?? {};
    switch (op?.kind) {
      case "write_file": {
        const uri = this.uriOf(args);
        const text = this.textOf(args);
        const doc = this.openDoc(uri);
        if (doc) {
          await this.replaceAll(doc, text);
        } else {
          await vscode.workspace.fs.createDirectory(vscode.Uri.file(path.dirname(uri.fsPath)));
          await vscode.workspace.fs.writeFile(uri, Buffer.from(text, "utf8"));
        }
        return;
      }
      case "append_line": {
        const uri = this.uriOf(args);
        const text = this.textOf(args);
        if (!(await this.exists(uri))) {
          await vscode.workspace.fs.writeFile(uri, new Uint8Array());
        }
        const doc = await vscode.workspace.openTextDocument(uri);
        await vscode.window.showTextDocument(doc, { preview: false });
        const old = doc.getText();
        const edit = new vscode.WorkspaceEdit();
        const gap = old === "" || old.endsWith("\n") ? "" : "\n";
        edit.insert(uri, doc.positionAt(old.length), gap + text + "\n");
        if (!(await vscode.workspace.applyEdit(edit)) || !(await doc.save())) {
          throw new Error(`VS Code could not write ${path.basename(uri.fsPath)}`);
        }
        return;
      }
      case "open_file": {
        const uri = this.uriOf(args);
        if (!(await this.exists(uri))) {
          throw new Error(`${String(args.path)} is not there`);
        }
        await vscode.window.showTextDocument(uri, { preview: false });
        return;
      }
      case "save_file": {
        const doc = this.openDoc(this.uriOf(args));
        if (doc?.isDirty && !(await doc.save())) {
          throw new Error(`VS Code could not save ${String(args.path)}`);
        }
        return;
      }
      case "run_file":
        return this.runFile(args);
      case "delete_file": {
        const uri = this.uriOf(args);
        await this.closeTabs(uri);
        if (await this.exists(uri)) {
          await vscode.workspace.fs.delete(uri, { useTrash: false });
        }
        return;
      }
      case "clear_terminal":
        await this.stopRun();
        this.run = null;
        this.running = undefined;
        if (vscode.window.activeTerminal) {
          await vscode.commands.executeCommand("workbench.action.terminal.clear");
        }
        return;
      default:
        throw new Error(`the add-on has no operation ${String(op?.kind)}`);
    }
  }

  // Run a file the way a learner would: `python <file>` in a terminal in the lesson's folder. Done
  // means the run started; the state says when it finished.
  private async runFile(args: Record<string, unknown>): Promise<void> {
    const uri = this.uriOf(args);
    if (!(await this.exists(uri))) {
      throw new Error(`${String(args.path)} is not there`);
    }
    const doc = this.openDoc(uri);
    if (doc?.isDirty) {
      await doc.save();
    }
    if (!this.runTerminal || this.runTerminal.exitStatus !== undefined) {
      this.runTerminal = vscode.window.createTerminal({ name: "Python", cwd: this.folder.uri });
    }
    const terminal = this.runTerminal;
    terminal.show(true);
    const shell = terminal.shellIntegration ?? (await this.shellOf(terminal));
    if (!shell) {
      throw new Error("VS Code's terminal is not reporting runs (shell integration is off)");
    }
    const before = this.running;
    shell.executeCommand("python", [relativeInside(this.folder.uri.fsPath, uri.fsPath) as string]);
    const answers = typeof args.input === "string" ? inputLines(args.input) : [];
    if (answers.length === 0) {
      return;
    }
    // Type the answers as a learner would, once the program has started and only while it runs.
    await this.until(() => this.running !== before && this.running?.terminal === terminal, SHELL_WAIT_MS);
    const running = this.running;
    if (running === before || running?.terminal !== terminal) {
      throw new Error(`${String(args.path)} did not start, so its input was not typed`);
    }
    for (const line of answers) {
      if (running.ended) {
        break;
      }
      terminal.sendText(line, true);
    }
  }

  // Stop a program that is still running, as Ctrl+C would. A program that ignores Ctrl+C loses its
  // terminal, so the next run starts in a fresh one.
  private async stopRun(): Promise<void> {
    const running = this.running;
    if (!running || running.ended) {
      return;
    }
    running.terminal.sendText(CTRL_C, false);
    if (!(await this.until(() => running.ended, STOP_WAIT_MS))) {
      running.terminal.dispose();
      if (this.runTerminal === running.terminal) {
        this.runTerminal = undefined;
      }
    }
  }

  // Close a file's tabs before it is deleted, saving it first so VS Code does not ask.
  private async closeTabs(uri: vscode.Uri): Promise<void> {
    const doc = this.openDoc(uri);
    if (doc?.isDirty) {
      await doc.save();
    }
    const tabs = vscode.window.tabGroups.all
      .flatMap((group) => group.tabs)
      .filter((tab) => tab.input instanceof vscode.TabInputText && tab.input.uri.toString() === uri.toString());
    if (tabs.length) {
      await vscode.window.tabGroups.close(tabs);
    }
  }

  private async until(done: () => boolean, ms: number): Promise<boolean> {
    const end = Date.now() + ms;
    while (!done()) {
      if (Date.now() >= end) {
        return false;
      }
      await delay(POLL_MS);
    }
    return true;
  }

  private shellOf(terminal: vscode.Terminal): Promise<vscode.TerminalShellIntegration | undefined> {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        sub.dispose();
        resolve(terminal.shellIntegration);
      }, SHELL_WAIT_MS);
      const sub = vscode.window.onDidChangeTerminalShellIntegration((e) => {
        if (e.terminal === terminal) {
          clearTimeout(timer);
          sub.dispose();
          resolve(e.shellIntegration);
        }
      });
    });
  }

  // Terminal settings for this lesson (the Meta key, the program's Python first on PATH). Kept in
  // memory only: never written to settings or any file.
  private setEnv(values: unknown, pathPrepend: unknown): void {
    const env = this.context.environmentVariableCollection;
    env.persistent = false;
    env.clear();
    env.description = "Set by Project X for this lesson";
    if (values && typeof values === "object") {
      for (const [name, value] of Object.entries(values)) {
        if (ENV_NAME.test(name) && typeof value === "string") {
          env.replace(name, value);
        }
      }
    }
    if (Array.isArray(pathPrepend)) {
      const dirs = pathPrepend.filter((d): d is string => typeof d === "string" && d !== "");
      if (dirs.length) {
        env.prepend("PATH", dirs.join(path.delimiter) + path.delimiter);
      }
    }
  }

  private async closeWindow(): Promise<void> {
    for (const doc of vscode.workspace.textDocuments) {
      if (doc.isDirty && relativeInside(this.folder.uri.fsPath, doc.uri.fsPath) !== null) {
        await doc.save();
      }
    }
    await vscode.commands.executeCommand("workbench.action.closeWindow");
  }

  dispose(): void {
    this.stopListening();
    this.socket?.destroy();
    this.socket = undefined;
    this.connected = false;
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder || folder.uri.scheme !== "file") {
    return;
  }
  const file = linkFile();
  const workRoot = path.join(process.env.LOCALAPPDATA ?? "", "projectx", "work");
  const named = readLinkInfo(file);
  const isLesson = relativeInside(workRoot, folder.uri.fsPath) !== null
    || (named !== null && sameFolder(named.folder, folder.uri.fsPath));
  if (!isLesson) {
    return; // the learner's own projects: stay asleep
  }
  const log = vscode.window.createOutputChannel("Project X", { log: true });
  const link = new Link(context, folder, log, file);
  const recheck = () => link.tryConnect();
  fs.watchFile(file, { interval: RETRY_MS }, recheck);
  context.subscriptions.push(log, link, { dispose: () => fs.unwatchFile(file, recheck) });
  link.tryConnect();
}

export function deactivate(): void {
  // the link is closed by its dispose
}
