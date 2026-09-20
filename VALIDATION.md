# JuicyCensor 2.0.1 validation

Validated locally on Windows on 2026-09-20.

- Verified that the sidebar badge and setup window title display 2.0.1.
- Checked centered Start/End controls, timestamp parsing, and increment buttons.
- Verified the new subtitle and visually inspected the app screenshot and README banner.
- Confirmed the existing 2.0.0 processing runtime remains ready without reinstalling.
- Reviewed the shipped profanity lists and parsed the Python source for syntax errors.

The processing pipeline and dependency versions are unchanged. Earlier backend and
installer validation is recorded below; it is not a new full-system test of this patch.

# JuicyCensor 2.0.0 validation

Validated locally on Windows on 2026-09-19.

- Created a new private Python 3.12.14 environment, independent of JuicyCensor 1.0.
- Installed the hash-locked CPU profile and then the CUDA 12.8 profile. Both passed
  imports, FFmpeg execution and device discovery. No system Python/toolkit setup required.
- Downloaded and loaded starter English speech models and forced alignment data.
- CPU, AMD integrated Vulkan and NVIDIA RTX 5060 Ti CUDA transcription/word alignment
  each produced 22 words and two expected matches on the public 11-second JFK sample.
- Worker analysis, eight backend unit tests and a real censored sample export passed.
- PySide6 6.11.2 interface checks passed timestamp editing, volume/mute, speed controls,
  adjustable skips, scissors selection/cancel, zoom/pan and export.
- The frozen 2.0.0 executable passed runtime discovery; the first-run setup dialog loaded.
- Built the Windows installer and portable/source ZIPs. Installer extraction mode,
  first-run setup UI, ZIP integrity and release-file checksums passed. The standard
  uninstall registry entry could not be exercised inside the restricted build session.
- Export feature checks covered original stream copy, resolution/frame-rate changes,
  NVIDIA H.264/HEVC/AV1, AMD H.264/HEVC, CPU H.264/HEVC, and MKV/Opus output to a chosen
  folder with filenames without spaces. Explicit unsupported encoders fail visibly.
- Audio Original targets the reported source bitrate; the 192 kbps fallback and preset
  transitions were tested. It does not promise lossless processed audio.

This is not a certification of every PC or video format. RX 9060 XT, Intel hardware
encoding and a separate physical clean PC have not been tested. Long-video, accessibility,
HDR color conversion and broad driver coverage need further validation. Automatic
encoder selection tests a few frames before rendering; later failures are still possible.

No personal videos or local model/environment overrides are included in the release
payload. The release builder uses an allowlist. Setup downloads dependencies directly
from publishers and checks pinned runtime/package hashes.


