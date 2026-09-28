# JuicyCensor 3.0.0 validation

Release checks on Windows x64, September 27, 2026.

## Processing and media

- All **48 automated tests** pass: backend selection, parsing, cache reuse and
  invalidation, Windows model-download privileges, setup recovery, audio censoring,
  review migration, progress estimates, subtitle formats/timing/history, Unicode
  matching, and translation response validation.
- Alignment-download regression tests cover reuse without networking, a truncated
  cached checkpoint, interrupted range retries, ignored ranges, failed integrity
  checks, and cleanup that preserves existing files when a retry fails.
- Live subtitle transcription passes on **CPU, NVIDIA CUDA, and Vulkan** using the
  public JFK speech sample. Local Whisper audio-to-English translation returns a
  reviewable suggestion. These checks use existing local models.
- Real MP4 subtitle burn-in and MKV subtitle-track exports pass FFprobe checks.
  Copied audio matches the input stream; copied MKV video also matches the input.
- Local/online text-model request formatting, context batches, endpoint boundaries,
  key handling, and malformed responses are covered by mocked protocol tests.
  No claim of translation quality from a particular text-model service is made.

## Interface and editing

- Native Qt checks cover bilingual editing, search, suggestion acceptance/dismissal,
  autosave, Undo/Redo, workspace switching, exports, and clean shutdown.
- Layout checks cover 1280×720 through 2560×1440, balanced video/transcript panes,
  edge resizing, queue visibility/removal, menu routing, shortcuts, and full-screen
  transitions that restore the previous window state.
- Waveform checks cover automatic decoding, 10 ms peak bins, quiet peaks, cache
  reuse, stale-result cancellation, videos without audio, cue moving/edge trimming,
  chronological reordering, bounds, Escape cancellation, busy-state guards,
  Undo/Redo, autosave, and saved censor-region timing changes.
- Appearance checks cover four palettes, two spacing choices, minimum and large
  windows, text contrast, saturation, invalid preference recovery, live preview,
  nested color-picker cancellation, pending-change cancellation, custom preset
  saving/reopening, and reset. Subtitle styling remains unchanged by app themes.
- Screenshots in the README use a generated demonstration clip and illustrative
  subtitles. No personal media or transcripts are included.

## Packaging and setup

- The frozen executable, installer, manifest, and documentation identify **3.0.0**.
  The executable's Windows file/product version metadata also identifies 3.0.0.
- The frozen first-run setup dialog opens. A fresh private **CPU runtime** installs
  from the frozen executable on the release machine, and startup/device discovery
  succeeds with that new runtime. No system Python or CUDA Toolkit is needed.
- Starter multilingual speech models download and load in that fresh environment.
  A real alignment download that ended early was recovered with the range downloader;
  the repaired checkpoint loads successfully. Complete cached copies are reused.
- Installer extraction and an actual **2.1.0 → 3.0.0** installer upgrade are checked
  in isolated folders. Custom configuration, word lists, appearance preferences,
  project/cache data, and runtime/model files are preserved while application files
  and the executable are replaced.
- Installer and portable/source archives are checked against the release source;
  ZIP integrity and SHA-256 checksums are verified before publishing. Uploaded
  GitHub asset digests must match the local release downloads.
- Private overrides, environments, models, caches, API keys, personal media, and
  development reports are excluded by the release builder's explicit allowlist.

## Scope and limitations

This is testing on the release machine, not certification of every Windows PC or
driver. A separate physical clean PC, Intel hardware encoding, HDR conversion,
long-video performance, and comprehensive accessibility have not been tested for
3.0.0. Radeon RX 9060 XT Vulkan support was confirmed by a user on another PC during
the 2.x releases; this is separate from the local 3.0.0 checks.

Installer tests use its documented extraction mode, which suppresses registry and
shortcut changes. They do not verify normal uninstall registration. Existing 2.x
runtime/download fixes remain covered by regression tests; the original affected
PC's installer security context has not been reproduced exactly.

Processing estimates are approximate. Censored preview prepares a cached media
copy using the export filters; it is not live filtering as regions are dragged.
Speech recognition and translation require review. ASS import retains text and
timing, not complex styles/effects. Censor transcripts and subtitle projects remain
separate. See README.md for workflows and format details.
