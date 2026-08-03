from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def project_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = project_dir()
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
REVIEW_APP = ROOT / "AutoCensorReview.py"


def show_error(message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror("JuicyCensor Review", message)
    root.destroy()


def clean_child_environment() -> dict[str, str]:
    """
    PyInstaller sets Tcl/Tk environment variables for its temporary _MEI folder.
    Those variables must not be inherited by the project's normal Python
    process, or Tkinter looks in the wrong place for init.tcl.
    """
    env = os.environ.copy()

    for name in (
        "TCL_LIBRARY",
        "TK_LIBRARY",
        "TCLLIBPATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "_MEIPASS2",
    ):
        env.pop(name, None)

    return env


def main() -> int:
    if not PYTHON.exists():
        show_error(
            "Python environment not found.\n\n"
            f"Expected:\n{PYTHON}\n\n"
            "Keep JuicyCensor Review.exe in the main JuicyCensor folder."
        )
        return 1

    if not REVIEW_APP.exists():
        show_error(
            "Review application not found.\n\n"
            f"Expected:\n{REVIEW_APP}"
        )
        return 1

    try:
        subprocess.Popen(
            [str(PYTHON), str(REVIEW_APP)],
            cwd=ROOT,
            env=clean_child_environment(),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as exc:
        show_error(f"Could not launch the review application:\n\n{exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
