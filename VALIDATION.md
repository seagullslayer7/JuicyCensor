# JuicyCensor 2.1.0 validation

- All 27 backend, cache, setup, review and time-estimate tests passed. New FFmpeg integration checks
  verify mute, continuous beep, pulse beep and custom beep audio, unchanged copied
  video streams, preview cache reuse/invalidation, invalid bounds and cleanup.
- Confirmed live transcription and alignment callbacks with real CPU and Vulkan
  analysis of the JFK sample, using existing offline models. First-run estimates,
  stage transitions, slower batches and out-of-order updates are covered by tests.
- Older review migration preserves edited regions while adding aligned transcript words.
- Qt integration checks cover transcript search/seek, original/censored source switching,
  cached switching, playhead and speed preservation, timing-edit invalidation and ETA.
- Preview and export use the same audio filter builders. Preview requires preparation
  and disk space for a cached video copy; it is not live audio filtering while editing.
- Estimates are approximate and available on the first run. Initial estimates use
  video length and processing settings; live stage progress refines the remaining time.

# JuicyCensor 2.0.3 validation

- AMD Radeon RX 9060 XT Vulkan support is confirmed by a user on a separate PC.
  This is community verification, distinct from the local automated tests below.

- All 17 backend/cache/setup tests passed, including successful recovery, a missing or
  invalid interpreter, unrelated errors, successful normal installs, and cancellation.
- A real child process emitted the reported uv error and exited unsuccessfully. Setup
  captured that output, verified Python 3.12.14 directly, and created a working venv.
- The original installer's Windows error 448 was simulated; it has not been reproduced
  under the affected PC's exact security context. No Windows security settings were changed.

# JuicyCensor 2.0.2 validation

- Regression tests exercise the pinned Hugging Face Hub implementation with symlink
  creation denied: existing blobs copy correctly and new downloads move into snapshots.
- Repeated cache configuration is safe and missing files still report errors.
- Downloaded the real large-v3 config with symbolic links denied, reused it offline,
  and retried the failed file in an existing cache successfully.
- All 11 backend/cache tests passed, along with UI version and runtime-reuse checks.

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

This is not a certification of every PC or video format. Intel hardware encoding
and a separate physical clean PC have not been tested by the maintainer. Long-video, accessibility,
HDR color conversion and broad driver coverage need further validation. Automatic
encoder selection tests a few frames before rendering; later failures are still possible.

No personal videos or local model/environment overrides are included in the release
payload. The release builder uses an allowlist. Setup downloads dependencies directly
from publishers and checks pinned runtime/package hashes.



