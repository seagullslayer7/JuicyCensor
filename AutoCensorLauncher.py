from __future__ import annotations
import subprocess, sys, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

PROJECT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PYTHON_EXE = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
ENGINE = PROJECT_DIR / "autocensor.py"

def pick_video():
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    path = filedialog.askopenfilename(title="Select a video", filetypes=[("Video files","*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),("All files","*.*")])
    root.destroy()
    return Path(path) if path else None

def popup(kind, title, text):
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    getattr(messagebox, kind)(title, text)
    root.destroy()

def main():
    if not PYTHON_EXE.exists():
        popup("showerror","JuicyCensor",f"Virtual environment not found:\n\n{PYTHON_EXE}\n\nKeep JuicyCensor.exe in the main project folder beside venv.")
        return 1
    if not ENGINE.exists():
        popup("showerror","JuicyCensor",f"Engine not found:\n\n{ENGINE}")
        return 1
    video = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pick_video()
    if video is None:
        return 0
    if not video.exists():
        popup("showerror","JuicyCensor",f"Video not found:\n{video}")
        return 1
    result = subprocess.run([str(PYTHON_EXE), str(ENGINE), str(video)], cwd=PROJECT_DIR)
    if result.returncode == 0:
        popup("showinfo","JuicyCensor","Finished successfully.\n\nCheck outputs\\censored.")
    else:
        popup("showerror","JuicyCensor","JuicyCensor failed.\n\nCheck logs\\last_error.txt.")
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
