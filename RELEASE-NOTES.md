# JuicyCensor 2.0.1

- Centered the Start and End timestamp values for easier reading.
- Changed the subtitle to “Detect. Review. Filter the Juice.”
- Replaced the shipped word and phrase lists with ordinary profanity; removed slurs
  and the old non-profanity phrases. Existing user lists remain preserved on upgrade.
- Refreshed the README with an orange banner, a current screenshot, and clearer model
  download instructions.
- Reuses the 2.0.0 processing runtime; no dependency upgrade is needed for this patch.

# JuicyCensor 2.0.0

The new orange-themed desktop app combines detection, playback review and export.

- NVIDIA CUDA, AMD/other Vulkan and CPU speech processing.
- Saved region editing, scissors selection, timeline zoom/pan, configurable skipping,
  preview speed and volume controls.
- Export folder/filename options, MP4/Matroska, quality presets with Custom settings,
  up to 4K resolution limits, and hardware/software encoding options.
- Windows installer with destination selection and a portable ZIP.
- First-run setup for private Python, verified dependencies, runtimes and starter models.

Choose the Setup.exe for installation or extract the entire Portable.zip. The automatic
GitHub Source code archive is not a ready-to-run app. Internet is required for initial
runtime setup. The app is not code-signed.

AMD integrated Radeon and NVIDIA RTX 5060 Ti were tested locally. RX 9060 XT and a
separate physical clean PC remain untested. Review detected censor regions before sharing.
