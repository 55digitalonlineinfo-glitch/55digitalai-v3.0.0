#!/usr/bin/env python3
"""Creates .venv/bin/python3 (and a few friends) as thin shims that forward to
the real interpreter at .venv/Scripts/ on Windows.

Every slash command in .claude/commands/ hardcodes the Unix-style path
`.venv/bin/python3` — that's what setup.sh produces on Mac/Linux, since
`python3 -m venv .venv` lays out `bin/` there. On Windows, the same venv
module lays out `Scripts/python.exe` instead, so without this, every slash
command fails after setup.bat finishes (the path it calls doesn't exist).

The shims are plain POSIX shell scripts, not .exe/.bat files, because the
thing invoking them is Claude Code's Bash tool — which on Windows runs
through Git Bash or WSL, not cmd.exe/PowerShell (same reason setup.bat's own
comment points there). Git Bash and WSL (with interop) can both exec a native
.exe referenced by a relative path from inside a shell script, the same way
npm's node_modules/.bin shims do — that's the pattern this follows.

Called by setup.bat right after dependencies are installed. Safe/no-op on
Mac/Linux, where setup.sh already produces a real bin/ directory and this
never runs.
"""
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "win32":
        return

    root = Path(__file__).resolve().parent.parent
    scripts_dir = root / ".venv" / "Scripts"
    bin_dir = root / ".venv" / "bin"

    if not scripts_dir.exists():
        print(f"  WARNING: {scripts_dir} not found — run setup.bat's venv step first.")
        return

    bin_dir.mkdir(parents=True, exist_ok=True)

    shims = {
        "python3": "python.exe",
        "python": "python.exe",
        "pip3": "pip.exe",
        "pip": "pip.exe",
    }

    made = []
    for shim_name, target_exe in shims.items():
        if not (scripts_dir / target_exe).exists():
            continue
        shim_path = bin_dir / shim_name
        content = (
            "#!/bin/sh\n"
            f'exec "$(dirname "$0")/../Scripts/{target_exe}" "$@"\n'
        )
        # Explicit LF only — a CRLF shebang line makes Git Bash/WSL fail with
        # "bad interpreter: No such file or directory", so this can't just be
        # a normal Path.write_text() on Windows (which would use os.linesep).
        with open(shim_path, "w", newline="\n", encoding="utf-8") as f:
            f.write(content)
        try:
            shim_path.chmod(0o755)
        except OSError:
            pass  # exec bit is meaningless on native Windows; Git Bash/WSL don't need it set here anyway
        made.append(shim_name)

    if made:
        print(f"  Windows compatibility shims ready in {bin_dir}: {', '.join(made)}")
    else:
        print(f"  WARNING: no shims created — expected .exe files not found in {scripts_dir}")


if __name__ == "__main__":
    main()
