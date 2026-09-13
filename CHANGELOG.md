# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tools/build_exe.py` for building the Windows executable locally, with
  `--clean`, a `--smoke` flag that launches the result, and a bundle check that
  reads the frozen archive's table of contents rather than the filesystem.

### Fixed
- **Smart compression no longer returns video that got bigger.** The
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

[Unreleased]: https://github.com/alirisner14/ConvertAll/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alirisner14/ConvertAll/releases/tag/v0.1.0
