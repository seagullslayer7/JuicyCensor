from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = PROJECT_DIR / "venv" / "Scripts" / "python.exe"
ENGINE = PROJECT_DIR / "autocensor.py"

sys.path.insert(0, str(PROJECT_DIR))
import autocensor


def format_review_time(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def parse_review_time(value: str) -> float:
    value = value.strip()
    if not value:
        raise ValueError("Timestamp cannot be blank.")

    if ":" not in value:
        return float(value)

    parts = value.split(":")
    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds

    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    raise ValueError("Use seconds, MM:SS.mmm, or HH:MM:SS.mmm.")


class ReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JuicyCensor Review")
        self.geometry("1160x720")
        self.minsize(940, 620)

        self.video: Path | None = None
        self.alignment_path: Path | None = None
        self.overrides_path: Path | None = None
        self.detected_events: list[autocensor.Event] = []
        self.manual_overrides: list[dict] = []

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.video_var = tk.StringVar()
        ttk.Label(top, text="Video:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.video_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="Browse", command=self.browse_video).grid(row=0, column=2)
        ttk.Button(top, text="Load Review", command=self.load_review).grid(row=0, column=3, padx=(8, 0))
        top.columnconfigure(1, weight=1)

        middle = ttk.Panedwindow(self, orient="horizontal")
        middle.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(middle)
        right = ttk.Frame(middle, padding=(10, 0, 0, 0))
        middle.add(left, weight=3)
        middle.add(right, weight=2)

        columns = ("kind", "start", "end", "duration", "match", "source")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        headings = {
            "kind": "Type",
            "start": "Start",
            "end": "End",
            "duration": "Duration",
            "match": "Matched text",
            "source": "Source/list entry",
        }
        widths = {"kind": 90, "start": 115, "end": 115, "duration": 85, "match": 300, "source": 180}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        controls = ttk.Frame(left, padding=(0, 8, 0, 0))
        controls.pack(fill="x")
        ttk.Button(controls, text="Preview selected", command=self.preview_selected).pack(side="left")
        ttk.Button(controls, text="Add manual region", command=self.add_override).pack(side="left", padx=6)
        ttk.Button(controls, text="Delete manual region", command=self.delete_override).pack(side="left")
        ttk.Button(controls, text="Save overrides", command=self.save_overrides).pack(side="right")

        ttk.Label(right, text="Selected region", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        form = ttk.Frame(right, padding=(0, 10, 0, 0))
        form.pack(fill="x")

        self.kind_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.match_var = tk.StringVar()
        self.source_var = tk.StringVar()

        rows = [
            ("Type", self.kind_var),
            ("Start (HH:MM:SS.mmm)", self.start_var),
            ("End (HH:MM:SS.mmm)", self.end_var),
            ("Label/text", self.match_var),
            ("Source", self.source_var),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=var).grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=4)
        form.columnconfigure(1, weight=1)

        ttk.Button(
            right,
            text="Apply changes to manual region",
            command=self.apply_changes
        ).pack(fill="x", pady=(10, 0))

        ttk.Separator(right).pack(fill="x", pady=15)

        ttk.Label(right, text="Actions", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Button(right, text="Render censored video", command=self.render_video).pack(fill="x", pady=(10, 5))
        ttk.Button(right, text="Open output folder", command=self.open_output_folder).pack(fill="x")

        self.status = tk.StringVar(value="Choose the original video, then click Load Review.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Select original video",
            filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("All files", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def _paths_for_video(self, video: Path) -> tuple[Path, Path]:
        fingerprint = autocensor.video_fingerprint(video)
        stem = autocensor.safe_stem(video)
        alignment = PROJECT_DIR / "cache" / "alignments" / f"{stem}_{fingerprint}_aligned.json"
        overrides = PROJECT_DIR / "cache" / "manual_overrides" / f"{stem}_{fingerprint}_overrides.json"
        return alignment, overrides

    def load_review(self) -> None:
        try:
            video = Path(self.video_var.get()).expanduser().resolve()
            if not video.exists():
                raise FileNotFoundError("Video not found.")

            alignment, overrides = self._paths_for_video(video)
            if not alignment.exists():
                raise FileNotFoundError(
                    f"Alignment cache not found:\n{alignment}\n\nRun dry_run.bat on this video first."
                )

            aligned = json.loads(alignment.read_text(encoding="utf-8"))
            words = autocensor.flatten_words(aligned)
            config = autocensor.load_config()
            self.detected_events = autocensor.find_events(
                words,
                autocensor.read_entries(PROJECT_DIR / "banned_words.txt"),
                autocensor.read_entries(PROJECT_DIR / "banned_phrases.txt"),
                config,
            )

            self.manual_overrides = []
            if overrides.exists():
                raw = json.loads(overrides.read_text(encoding="utf-8"))
                self.manual_overrides = list(raw.get("regions", []))

            self.video = video
            self.alignment_path = alignment
            self.overrides_path = overrides
            self.refresh_tree()
            self.status.set(
                f"Loaded {len(self.detected_events)} detected events and "
                f"{len(self.manual_overrides)} manual regions."
            )
        except Exception as exc:
            messagebox.showerror("JuicyCensor Review", str(exc))

    def refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())

        for i, event in enumerate(self.detected_events):
            self.tree.insert(
                "", "end", iid=f"d:{i}",
                values=(
                    "Detected",
                    format_review_time(event.start),
                    format_review_time(event.end),
                    f"{event.end-event.start:.3f}",
                    event.matched,
                    event.source,
                ),
            )

        for i, region in enumerate(self.manual_overrides):
            start = float(region["start"])
            end = float(region["end"])
            self.tree.insert(
                "", "end", iid=f"m:{i}",
                values=(
                    "Manual",
                    format_review_time(start),
                    format_review_time(end),
                    f"{end-start:.3f}",
                    region.get("label", "manual censor"),
                    region.get("source", "manual"),
                ),
            )

    def on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        self.kind_var.set(values[0])
        self.start_var.set(values[1])
        self.end_var.set(values[2])
        self.match_var.set(values[4])
        self.source_var.set(values[5])

    def add_override(self) -> None:
        self.manual_overrides.append({
            "start": 0.0,
            "end": 1.0,
            "label": "manual censor",
            "source": "manual",
        })
        self.refresh_tree()
        iid = f"m:{len(self.manual_overrides)-1}"
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self.on_select()

    def delete_override(self) -> None:
        selection = self.tree.selection()
        if not selection or not selection[0].startswith("m:"):
            messagebox.showinfo("JuicyCensor Review", "Select a manual region first.")
            return
        index = int(selection[0].split(":")[1])
        del self.manual_overrides[index]
        self.refresh_tree()

    def apply_changes(self) -> None:
        selection = self.tree.selection()
        if not selection or not selection[0].startswith("m:"):
            messagebox.showinfo("JuicyCensor Review", "Only manual regions can be edited.")
            return
        try:
            index = int(selection[0].split(":")[1])
            start = parse_review_time(self.start_var.get())
            end = parse_review_time(self.end_var.get())
            if end <= start:
                raise ValueError("End must be greater than start.")

            self.manual_overrides[index] = {
                "start": start,
                "end": end,
                "label": self.match_var.get().strip() or "manual censor",
                "source": self.source_var.get().strip() or "manual",
            }
            self.refresh_tree()
            iid = f"m:{index}"
            self.tree.selection_set(iid)
            self.tree.see(iid)
        except Exception as exc:
            messagebox.showerror("JuicyCensor Review", str(exc))

    def save_overrides(self) -> None:
        if self.overrides_path is None:
            messagebox.showinfo("JuicyCensor Review", "Load a video first.")
            return
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "regions": self.manual_overrides}
        self.overrides_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.status.set(f"Saved overrides: {self.overrides_path.name}")

    def selected_times(self) -> tuple[float, float] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return parse_review_time(values[1]), parse_review_time(values[2])

    def preview_selected(self) -> None:
        if self.video is None:
            messagebox.showinfo("JuicyCensor Review", "Load a video first.")
            return
        times = self.selected_times()
        if times is None:
            messagebox.showinfo("JuicyCensor Review", "Select a region first.")
            return

        start, end = times
        preview_start = max(0.0, start - 2.0)
        preview_end = end + 2.0
        duration = max(1.0, preview_end - preview_start)

        preview_dir = PROJECT_DIR / "cache" / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview = preview_dir / "review_preview.mp4"

        self.status.set("Creating preview clip...")
        self.update_idletasks()
        try:
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-ss", f"{preview_start:.3f}", "-i", str(self.video),
                "-t", f"{duration:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                str(preview),
            ], check=True)
            os.startfile(preview)
            self.status.set(
                f"Opened preview from {format_review_time(preview_start)} "
                f"to {format_review_time(preview_end)}."
            )
        except Exception as exc:
            messagebox.showerror("JuicyCensor Review", f"Preview failed:\n{exc}")

    def render_video(self) -> None:
        if self.video is None:
            messagebox.showinfo("JuicyCensor Review", "Load a video first.")
            return

        self.save_overrides()

        def worker() -> None:
            self.status.set("Rendering censored video...")
            try:
                result = subprocess.run(
                    [str(PYTHON_EXE), str(ENGINE), str(self.video)],
                    cwd=PROJECT_DIR,
                )
                if result.returncode == 0:
                    self.status.set("Render complete.")
                    messagebox.showinfo(
                        "JuicyCensor Review",
                        "Render complete.\n\nCheck outputs\\censored.",
                    )
                else:
                    self.status.set("Render failed.")
                    messagebox.showerror(
                        "JuicyCensor Review",
                        "Render failed. Check logs\\last_error.txt.",
                    )
            except Exception as exc:
                self.status.set("Render failed.")
                messagebox.showerror("JuicyCensor Review", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def open_output_folder(self) -> None:
        folder = PROJECT_DIR / "outputs" / "censored"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)


if __name__ == "__main__":
    ReviewApp().mainloop()
