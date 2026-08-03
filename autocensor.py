#!/usr/bin/env python3
"""
JuicyCensor v1.0.0

Uses cached WhisperX forced-alignment when available, then creates a new
censored MP4. The original video is never modified.

Censor modes:
- continuous_beep: generated sine tone, seamless at any duration
- pulse_beep: repeated short tone with small gaps
- custom_beep: loop/trim beep.mp3
- mute: silence only
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
import whisperx

PROJECT_DIR = Path(__file__).resolve().parent


@dataclass
class Word:
    text: str
    normalized: str
    start: float
    end: float
    score: float | None = None


@dataclass
class Event:
    start: float
    end: float
    matched: str
    kind: str
    source: str


def ensure_directories() -> dict[str, Path]:
    paths = {
        "audio_cache": PROJECT_DIR / "cache" / "audio",
        "aligned_cache": PROJECT_DIR / "cache" / "alignments",
        "logs": PROJECT_DIR / "logs",
        "censored_outputs": PROJECT_DIR / "outputs" / "censored",
        "reports": PROJECT_DIR / "outputs" / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def load_config() -> dict[str, Any]:
    path = PROJECT_DIR / "config.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"'{name}' was not found on PATH.")


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, text=True, capture_output=capture)


def video_fingerprint(video: Path) -> str:
    stat = video.stat()
    raw = f"{video.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def safe_stem(path: Path) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", path.stem).strip() or "video"


def normalize_token(text: str) -> str:
    text = text.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9']+", "", text)


def read_entries(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing list file: {path}")
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip().lower()
        if value and not value.startswith("#"):
            entries.append(value)
    return entries


def word_variants(entry: str) -> set[str]:
    entry = normalize_token(entry)
    variants = {entry}
    variants.update({
        "rape": {"rape", "rapes", "raped", "raping", "rapist", "rapists"},
        "grape": {"grape", "grapes", "graped", "graping"},
        "nigger": {"nigger", "niggers"},
        "nigga": {"nigga", "niggas"},
        "fag": {"fag", "fags", "faggot", "faggots"},
        "faggot": {"faggot", "faggots", "fag", "fags"},
        "jew": {"jew", "jews", "jewish"},
        "kike": {"kike", "kikes"},
        "chink": {"chink", "chinks"},
        "spic": {"spic", "spics"},
        "wetback": {"wetback", "wetbacks"},
        "tranny": {"tranny", "trannies"},
    }.get(entry, set()))
    return variants


def extract_audio(video: Path, audio_path: Path) -> None:
    if audio_path.exists() and audio_path.stat().st_size > 0:
        print(f"Using cached audio: {audio_path.name}")
        return
    print("Extracting 16 kHz mono WAV with FFmpeg...")
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(audio_path),
    ])


def transcribe_and_align(
    audio_path: Path,
    config: dict[str, Any],
    aligned_cache_path: Path,
) -> dict[str, Any]:
    if aligned_cache_path.exists():
        print(f"Using cached WhisperX alignment: {aligned_cache_path.name}")
        return json.loads(aligned_cache_path.read_text(encoding="utf-8"))

    device = config.get("device", "cuda")
    compute_type = config.get("compute_type", "float16")
    model_name = config.get("model", "large-v3")
    language = config.get("language", "en")
    batch_size = int(config.get("batch_size", 8))

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access the GPU.")

    print(f"Loading WhisperX {model_name} on {device} ({compute_type})...")
    model = whisperx.load_model(
        model_name, device, compute_type=compute_type, language=language
    )

    print("Loading extracted WAV...")
    audio = whisperx.load_audio(str(audio_path))

    print("Transcribing...")
    result = model.transcribe(
        audio, batch_size=batch_size, language=language, print_progress=True
    )

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    detected_language = result.get("language") or language
    print(f"Loading alignment model for '{detected_language}'...")
    align_model, metadata = whisperx.load_align_model(
        language_code=detected_language, device=device
    )

    print("Performing forced alignment...")
    aligned = whisperx.align(
        result["segments"], align_model, metadata, audio, device,
        return_char_alignments=False, print_progress=True,
    )
    aligned["language"] = detected_language

    del align_model, audio
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    aligned_cache_path.write_text(
        json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved alignment cache: {aligned_cache_path}")
    return aligned


def flatten_words(aligned: dict[str, Any]) -> list[Word]:
    words = []
    for segment in aligned.get("segments", []):
        for item in segment.get("words", []):
            if item.get("start") is None or item.get("end") is None:
                continue
            raw = str(item.get("word", "")).strip()
            normalized = normalize_token(raw)
            if normalized:
                words.append(Word(
                    text=raw,
                    normalized=normalized,
                    start=float(item["start"]),
                    end=float(item["end"]),
                    score=float(item["score"]) if item.get("score") is not None else None,
                ))
    return words


def find_events(
    words: list[Word],
    banned_words: list[str],
    banned_phrases: list[str],
    config: dict[str, Any],
) -> list[Event]:
    pre = float(config.get("pre_padding", 0.08))
    post = float(config.get("post_padding", 0.12))
    minimum = float(config.get("minimum_censor_duration", 0.50))

    expanded: dict[str, str] = {}
    for source in banned_words:
        for variant in word_variants(source):
            expanded[variant] = source

    events: list[Event] = []
    for word in words:
        source = expanded.get(word.normalized)
        if source:
            start = max(0.0, word.start - pre)
            end = word.end + post
            if end - start < minimum:
                center = (start + end) / 2
                start = max(0.0, center - minimum / 2)
                end = center + minimum / 2
            events.append(Event(start, end, word.text, "word", source))

    normalized_words = [w.normalized for w in words]
    for phrase in banned_phrases:
        tokens = [normalize_token(x) for x in phrase.split()]
        tokens = [x for x in tokens if x]
        if not tokens:
            continue
        n = len(tokens)
        for i in range(len(words) - n + 1):
            if normalized_words[i:i+n] == tokens:
                events.append(Event(
                    max(0.0, words[i].start - pre),
                    words[i+n-1].end + post,
                    " ".join(w.text for w in words[i:i+n]),
                    "phrase", phrase
                ))

    return merge_events(events, float(config.get("merge_gap", 0.10)))


def merge_events(events: Iterable[Event], gap: float) -> list[Event]:
    ordered = sorted(events, key=lambda e: (e.start, e.end))
    if not ordered:
        return []
    merged = [ordered[0]]
    for event in ordered[1:]:
        previous = merged[-1]
        if event.start <= previous.end + gap:
            merged[-1] = Event(
                previous.start,
                max(previous.end, event.end),
                f"{previous.matched} | {event.matched}",
                f"{previous.kind}+{event.kind}",
                f"{previous.source} | {event.source}",
            )
        else:
            merged.append(event)
    return merged


def probe_duration(video: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ], capture=True)
    return float(result.stdout.strip())


def mute_chain(events: list[Event]) -> str:
    return ",".join(
        f"volume=enable='between(t,{e.start:.3f},{e.end:.3f})':volume=0"
        for e in events
    )


def build_generated_tone_filter(
    events: list[Event],
    total: float,
    config: dict[str, Any],
    pulse: bool,
) -> str:
    """
    Build one stereo tone timeline from alternating silence and generated-tone
    segments. This fixes the previous version, which accidentally zeroed the
    sine source before mixing it.
    """
    frequency = float(config.get("beep_frequency", 1000))
    volume = float(config.get("beep_volume", 0.8))
    pulse_on = float(config.get("pulse_on", 0.22))
    pulse_off = float(config.get("pulse_off", 0.08))

    parts = [
        f"[0:a]{mute_chain(events)},"
        f"aformat=channel_layouts=stereo,"
        f"aresample=async=1:first_pts=0[muted]"
    ]

    labels: list[str] = []
    cursor = 0.0
    index = 0

    def add_silence(length: float) -> None:
        nonlocal index
        if length <= 0.001:
            return
        label = f"s{index}"
        parts.append(
            f"anullsrc=r=48000:cl=stereo,"
            f"atrim=0:{length:.3f},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
        index += 1

    def add_tone(length: float) -> None:
        nonlocal index
        if length <= 0.001:
            return
        label = f"t{index}"
        parts.append(
            f"sine=frequency={frequency}:sample_rate=48000:"
            f"duration={length:.3f},"
            f"aformat=channel_layouts=stereo,"
            f"volume={volume},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
        index += 1

    for event in events:
        add_silence(max(0.0, event.start - cursor))
        length = max(0.05, event.end - event.start)

        if pulse:
            remaining = length
            while remaining > 0.001:
                on_length = min(pulse_on, remaining)
                add_tone(on_length)
                remaining -= on_length
                if remaining <= 0.001:
                    break
                off_length = min(pulse_off, remaining)
                add_silence(off_length)
                remaining -= off_length
        else:
            add_tone(length)

        cursor = event.end

    add_silence(max(0.0, total - cursor))

    parts.append(
        f"{''.join(labels)}"
        f"concat=n={len(labels)}:v=0:a=1[tonetimeline]"
    )
    parts.append(
        f"[muted][tonetimeline]"
        f"amix=inputs=2:duration=first:"
        f"dropout_transition=0:normalize=0,"
        f"aformat=channel_layouts=stereo,"
        f"atrim=0:{total:.3f},"
        f"aresample=async=1:first_pts=0[outa]"
    )
    return ";".join(parts)


def build_custom_beep_filter(
    events: list[Event], total: float, volume: float
) -> str:
    parts = [f"[0:a]{mute_chain(events)},aresample=async=1:first_pts=0[muted]"]
    labels, cursor, index = [], 0.0, 0

    for event in events:
        gap = max(0.0, event.start - cursor)
        if gap > 0.001:
            label = f"s{index}"
            parts.append(
                f"anullsrc=r=48000:cl=stereo,atrim=0:{gap:.3f},"
                f"asetpts=PTS-STARTPTS[{label}]"
            )
            labels.append(f"[{label}]")
            index += 1

        length = max(0.05, event.end - event.start)
        label = f"b{index}"
        parts.append(
            f"[1:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,"
            f"aloop=loop=-1:size=2147483647,atrim=0:{length:.3f},"
            f"volume={volume}[{label}]"
        )
        labels.append(f"[{label}]")
        index += 1
        cursor = event.end

    tail = max(0.0, total - cursor)
    if tail > 0.001:
        label = f"s{index}"
        parts.append(
            f"anullsrc=r=48000:cl=stereo,atrim=0:{tail:.3f},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")

    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[beeptimeline]")
    parts.append(
        f"[muted][beeptimeline]amix=inputs=2:duration=first:"
        f"dropout_transition=0:normalize=0,atrim=0:{total:.3f},"
        f"aresample=async=1:first_pts=0[outa]"
    )
    return ";".join(parts)


def create_censored_video(
    video: Path, beep: Path, output: Path,
    events: list[Event], config: dict[str, Any]
) -> None:
    total = probe_duration(video)
    mode = str(config.get("censor_mode", "continuous_beep")).lower()

    command = ["ffmpeg", "-hide_banner", "-y", "-i", str(video)]

    if mode == "continuous_beep":
        filter_complex = build_generated_tone_filter(events, total, config, False)
    elif mode == "pulse_beep":
        filter_complex = build_generated_tone_filter(events, total, config, True)
    elif mode == "custom_beep":
        if not beep.exists():
            raise FileNotFoundError(f"Custom beep file not found: {beep}")
        command += ["-stream_loop", "-1", "-i", str(beep)]
        filter_complex = build_custom_beep_filter(
            events, total, float(config.get("beep_volume", 1.0))
        )
    elif mode == "mute":
        filter_complex = (
            f"[0:a]{mute_chain(events)},aresample=async=1:first_pts=0[outa]"
        )
    else:
        raise ValueError(
            "censor_mode must be continuous_beep, pulse_beep, custom_beep, or mute"
        )

    print(f"Creating censored MP4 using mode: {mode}")

    # Windows has a relatively small process command-line limit. Long videos
    # with many censor events can make filter_complex too large to pass as a
    # command-line argument, causing WinError 206. Store the filter graph in a
    # UTF-8 text file and let FFmpeg read it instead.
    filter_dir = PROJECT_DIR / "cache" / "ffmpeg_filters"
    filter_dir.mkdir(parents=True, exist_ok=True)
    filter_script = filter_dir / f"{safe_stem(video)}_filter.txt"
    filter_script.write_text(filter_complex, encoding="utf-8")

    command += [
        "-filter_complex_script", str(filter_script),
        "-map", "0:v:0", "-map", "[outa]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(output),
    ]
    run(command)


def format_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def write_report(path: Path, video: Path, events: list[Event], cache_file: Path) -> None:
    counts = Counter()
    for event in events:
        for source in event.source.split(" | "):
            counts[source] += 1

    lines = [
        "JuicyCensor v1.0.0 report",
        f"Video: {video}",
        f"Alignment cache: {cache_file}",
        f"Events: {len(events)}",
        "",
        "Counts by list entry:",
    ]
    for source, count in counts.most_common():
        lines.append(f"  {source}: {count}")

    lines += ["", "Timestamped events:", ""]
    for i, event in enumerate(events, 1):
        lines.extend([
            f"{i}. {format_time(event.start)} --> {format_time(event.end)}",
            f"   Match: {event.matched}",
            f"   Type: {event.kind}",
            f"   List entry: {event.source}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def load_manual_override_events(video: Path) -> list[Event]:
    fingerprint = video_fingerprint(video)
    stem = safe_stem(video)
    path = PROJECT_DIR / "cache" / "manual_overrides" / f"{stem}_{fingerprint}_overrides.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    events = []
    for region in raw.get("regions", []):
        start = float(region["start"])
        end = float(region["end"])
        if end <= start:
            continue
        events.append(Event(start, end, str(region.get("label", "manual censor")), "manual", str(region.get("source", "manual"))))
    return events

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--retranscribe", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = ensure_directories()
    config = load_config()

    require_command("ffmpeg")
    require_command("ffprobe")

    video = args.video.expanduser().resolve()
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")

    beep = PROJECT_DIR / str(config.get("beep_file", "beep.mp3"))
    fingerprint = video_fingerprint(video)
    stem = safe_stem(video)

    audio_cache = paths["audio_cache"] / f"{stem}_{fingerprint}.wav"
    aligned_cache = paths["aligned_cache"] / f"{stem}_{fingerprint}_aligned.json"
    if args.retranscribe and aligned_cache.exists():
        aligned_cache.unlink()

    output = paths["censored_outputs"] / f"{stem}_censored.mp4"
    report = paths["reports"] / f"{stem}_report.txt"
    event_json = paths["reports"] / f"{stem}_events.json"

    extract_audio(video, audio_cache)
    aligned = transcribe_and_align(audio_cache, config, aligned_cache)
    words = flatten_words(aligned)

    events = find_events(
        words,
        read_entries(PROJECT_DIR / "banned_words.txt"),
        read_entries(PROJECT_DIR / "banned_phrases.txt"),
        config,
    )
    manual_events = load_manual_override_events(video)
    if manual_events:
        events = merge_events([*events, *manual_events], float(config.get("merge_gap", 0.10)))
        print(f"Manual override regions: {len(manual_events)}")

    write_report(report, video, events, aligned_cache)
    event_json.write_text(
        json.dumps([asdict(e) for e in events], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nAligned words: {len(words)}")
    print(f"Censor events: {len(events)}")
    print(f"Report: {report}")

    if not events:
        print("No matches found. No MP4 was created.")
        return 0
    if args.dry_run:
        print("Dry run complete. No MP4 was created.")
        return 0

    create_censored_video(video, beep, output, events, config)
    print("\nDone.")
    print(f"Original preserved: {video}")
    print(f"Censored copy:     {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        log_dir = PROJECT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        error_log = log_dir / "last_error.txt"
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"\nError: {exc}", file=sys.stderr)
        print(f"Details: {error_log}", file=sys.stderr)
        raise SystemExit(1)
