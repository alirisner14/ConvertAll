# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.2.1] - 2026-09-13

### Fixed
- **Every button was dead to the mouse.** `AccessibleButton` defined
  `_on_enter` and `_on_leave`, the names CTkButton uses internally, so the
  subclass silently overrode the parent's methods. CTkButton sets
  `_mouse_inside` in those, and checks it before firing a button's command — so
  no click ever reached one. The buttons still drew, hovered, took keyboard
  focus and responded to Enter and Space; only the mouse did nothing. Drag and
  drop was unaffected. Introduced in 0.2.0.
- **The narrowest allowed window clipped its content.** The minimum width was
  980, but the widest panel needs more than that leaves, and nothing scrolls
  horizontally — so roughly 48px of controls sat off the right edge with no way
  to reach them. The minimum is now 1040.
- GUI tests no longer skip silently. Creating Tk roots in quick succession can
  fail on Windows, and the suite was quietly skipping up to eight tests.

### Added
- `tests/test_widgets.py` drives the real click path across every button
  variant, and enforces a structural rule — no private name may be defined on
  both `AccessibleButton` and `CTkButton` — which needs no display and catches
  that whole class of bug.
- `tests/test_layout.py` shrinks the window to its minimum and checks that no
  panel clips and every run button stays on screen.

## [0.2.0] - 2026-09-13

### Added
- **A video codec choice in the Compression tool: H.264, H.265/HEVC or AV1.**
  Measured on screen-recording content, H.265 saves about 17% over an H.264
  source and AV1 about 34%, at roughly two and four times the encode time
  respectively. Unavailable encoders are reported clearly instead of failing
  mid-job.
- Video audio streams are now copied rather than re-encoded to AAC, so they no
  longer lose a generation. Sources whose audio cannot live in MP4 fall back to
  AAC automatically.
- `tools/build_exe.py` for building the Windows executable locally, with
  `--clean`, a `--smoke` flag that launches the result, and a bundle check that
  reads the frozen archive's table of contents rather than the filesystem.

### Changed
- **New palette, and no yellow in either theme.** The default is a charcoal
  ground (`#2C2D30`) with off-white text (`#F7F5F6`) and a mint accent
  (`#94F2C0`, 10.3:1). *Maximum contrast* drops its yellow for plain white on
  black at 21:1, with the selected item inverting rather than tinting.
  Saturated yellow scores well on paper and is tiring to actually look at.
- **Hover darkens instead of lightening.** The mint and white accents step down
  on hover rather than flaring up, so the interface never gets brighter as the
  mouse moves across it.
- **The default type scale is ordinary desktop size**, not pre-enlarged. Text
  scaling is an option (`Ctrl` + `+`, up to 160%) rather than the starting
  point, so the app looks like a normal application out of the box.
- Hover no longer floods a whole button with the accent — it tints the surface
  and recolours the label, leaving one saturated block on screen instead of
  lighting up the interface as the mouse moves.
- `tests/test_theme.py` measures every colour pairing against WCAG 2.1 and
  fails the build below threshold, so the palettes cannot quietly rot.
- **Reorganised around intent rather than file type.** The five tools are now
  four: **Conversion** (you need a specific format), **Compression** (you want
  a smaller file), and a **Vector art tools** group holding **Tracing (Raster
  to Vector)** and **Split SVG Layers**. Separate Image conversion and Audio to
  MP4 tools are gone — both are conversions, so they share one panel whose
  format dropdown is built from whatever files you load.
- The format dropdown offers only targets *every* selected file can reach, and
  says so plainly when a mixed selection has nothing in common, rather than
  silently skipping files mid-run.
- "Smart compression" is now just **Compression**. "Smart" implied judgement
  the code does not have — it dispatches on file type.
- The **Audio to video** tool is now called **Audio to MP4**. The old name
  described something impossible — the tool wraps an audio file in an MP4
  container so it can be uploaded where only video is accepted.

### Fixed
- **Compression no longer returns video that got bigger.** The
  "keep the original if the re-encode is larger" guard was documented as
  general but only implemented for images, so an already-efficient MP4 — or
  anything in a newer codec than H.264 — could come back larger *and* slightly
  degraded, reported as a success. The guard now covers video too.
- A kept original is written under its own extension. Previously the source
  bytes were copied into the re-encode's filename, so a GIF that failed to beat
  PNG was saved as `.png`, and an MKV as `.mp4`.

## [0.1.0] - 2026-09-12

The first release.

### Added
- **Image conversion** — batch `.png → .webp`, `.heic → .png/.jpg`, and
  `.png/.jpg → .ico` with every icon size in one file. Alpha, ICC profiles and
  EXIF rotation are preserved.
- **Audio to video** — wrap audio into `.mp4` with a still background image or a
  synthesised flat-colour track, at 720p/1080p/4K/square.
- **Raster to vector** — auto-tracing with two Potrace-based engines: colour
  artwork is posterised and traced as stacked colour layers, and line art is
  thresholded and traced as a single path. Adjustable detail, threshold and
  inversion.
- **SVG splitting** — split layered `.svg` files into standalone files per
  layer, group or shape. Lone container groups are unwrapped and their
  transforms re-applied; `<defs>` and `<style>` are copied into every piece and
  the original `viewBox` is preserved.
- **Smart compression** — type-aware optimisation: true-lossless WebP for flat
  artwork, q95 for photographs, FLAC for WAV, x264 CRF for video, metadata
  stripping for SVG. Already-lossy audio is left untouched, and any file that
  would grow keeps its original bytes.
- **Accessible GUI** — two contrast-verified palettes (WCAG AAA and 21:1
  maximum), live text scaling from 85% to 160%, a 3px focus ring distinct from
  the hover state, full keyboard access with shortcuts, and visible help text
  instead of tooltips.
- Optional drag-and-drop file input via `tkinterdnd2`.
- Bundled FFmpeg fallback through `imageio-ffmpeg`, so no manual install is
  needed on Windows.
- pytest suite covering every pipeline, runnable without a display.

[Unreleased]: https://github.com/alirisner14/ConvertAll/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/alirisner14/ConvertAll/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alirisner14/ConvertAll/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alirisner14/ConvertAll/releases/tag/v0.1.0
