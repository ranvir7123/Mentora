# Project X lessons (VS Code add-on)

This add-on lets the Project X program see what you do in a lesson's VS Code window, so it can tick
your steps: the lesson's files, the problems list, where your cursor is, and the last Python program you
ran in the terminal. It also lets the program write a lesson's files and run them, to prove a lesson works.

It wakes up only in a lesson's folder (inside `%LOCALAPPDATA%\projectx\work\`). In your own projects it
does nothing. It talks only to the Project X program on this computer (127.0.0.1), with a one-time
password the program writes to `%LOCALAPPDATA%\projectx\vscode.json`, and never reads or writes files
outside the lesson's folder.

Build and install (from this folder):

```
npm install
npm test
npm run package
code --install-extension projectx-0.1.0.vsix
```
