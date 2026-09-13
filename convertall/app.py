"""The ConvertAll window.

Layout: a header with the accessibility controls, a keyboard-navigable tool
sidebar, a scrolling panel for the selected tool, and a shared activity log.
The GUI never does any work itself - it hands a file list plus a worker
function to `JobRunner` and drains the resulting event queue on the Tk loop.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__
from .core import convert as convert_core
from .core import images as images_core
from .core import media as media_core
from .core import svgsplit as svg_core
from .core import vectorize as trace_core
from .core.common import (
    AUDIO_EXTS,
    IMAGE_EXTS,
    VECTOR_EXTS,
    VIDEO_EXTS,
    collect_files,
    default_output_dir,
    human,
    kind_of,
)
from .core.compress import smart_compress
from .core.convert import convert_file
from .core.svgsplit import split_svg
from .core.vectorize import trace_image
from .jobs import JobRunner, JobSummary
from .theme import (
    FONT_FAMILY,
    MAX_SCALE,
    MIN_SCALE,
    PALETTES,
    SCALE_STEP,
    Palette,
    sized,
)
from .widgets import (
    AccessibleButton,
    Card,
    FileList,
    LogView,
    checkbox,
    label,
    option_menu,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Optional drag-and-drop. The app works fine without it.
try:  # pragma: no cover - depends on environment
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

    DND_AVAILABLE = True
except Exception:  # pragma: no cover
    _Root = ctk.CTk
    DND_FILES = None
    DND_AVAILABLE = False


def _open_folder(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _filetypes(exts: set[str], description: str) -> list[tuple[str, str]]:
    pattern = " ".join(f"*{e}" for e in sorted(exts))
    return [(description, pattern), ("All files", "*.*")]


# --------------------------------------------------------------------------- #
# Tool panels
# --------------------------------------------------------------------------- #


class ToolPanel(ctk.CTkScrollableFrame):
    """Base panel: file list, options, output folder, run button."""

    key = "tool"
    title = "Tool"
    description = ""
    accepted: set[str] = set()
    file_label = "Files"
    drop_hint = "any supported file"
    action_text = "Convert"
    dialog_name = "Supported files"

    def __init__(self, master, app: ConvertAllApp):
        palette, scale = app.palette, app.scale
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color=palette.border_strong,
            scrollbar_button_hover_color=palette.accent,
        )
        self.app = app
        self.palette = palette
        self.scale = scale
        self.output_dir: Path | None = None
        self.option_rows: dict[str, ctk.CTkFrame] = {}

        label(self, palette, self.title, kind="display", scale=scale).pack(
            fill="x", padx=4, pady=(2, 2)
        )
        label(
            self, palette, self.description, kind="body", scale=scale, muted=True, wraplength=760
        ).pack(fill="x", padx=4, pady=(0, 14))

        self._build_files_card()
        self._build_options_card()
        self._build_output_card()

    # -- file selection ----------------------------------------------------- #

    def _build_files_card(self) -> None:
        card = Card(self, self.palette, self.file_label, scale=self.scale)
        card.pack(fill="both", expand=True, padx=4, pady=(0, 14))

        verb = "Drop or Browse" if DND_AVAILABLE else "Browse"
        hint = f"{verb} for {self.drop_hint}"
        label(card, self.palette, hint, kind="small", scale=self.scale, muted=True).pack(
            fill="x", padx=16, pady=(0, 8)
        )

        # The buttons sit above the list so they stay on screen in a short
        # window, where the list itself is what gets scrolled.
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 10))

        self.files = FileList(card, self.palette, scale=self.scale, height=8)
        self.files.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._enable_drop(self.files.listbox)

        for text, command, variant in (
            ("Browse…", self.add_files, "secondary"),
            ("Add folder…", self.add_folder, "secondary"),
            ("Remove selected", self.files.remove_selected, "quiet"),
            ("Clear all", self.clear_files, "quiet"),
        ):
            AccessibleButton(
                row,
                self.palette,
                text,
                command,
                variant=variant,
                scale=self.scale,
                height=40,
            ).pack(side="left", padx=(0, 10))

        self.count_label = label(
            card, self.palette, "No files selected", kind="small", scale=self.scale, muted=True
        )
        self.count_label.pack(fill="x", padx=16, pady=(0, 14))

    def _enable_drop(self, widget) -> None:
        if not DND_AVAILABLE:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - environment
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event) -> None:  # pragma: no cover - GUI callback
        paths = self.app.tk.splitlist(event.data)
        self._ingest(paths)

    def _ingest(self, paths) -> None:
        found = collect_files(paths, self.accepted or None)
        added = self.files.add(found)
        skipped = len(list(paths)) - added if not found else 0
        self.refresh_count()
        if added:
            self.app.log_line(f"Added {added} file(s) to {self.title}.", "ok")
        elif skipped or not found:
            self.app.log_line(
                f"Nothing added - {self.title} accepts: {', '.join(sorted(self.accepted))}", "warn"
            )

    def add_files(self) -> None:
        chosen = filedialog.askopenfilenames(
            title=f"Choose files for {self.title}",
            filetypes=_filetypes(self.accepted, self.dialog_name),
        )
        if chosen:
            self._ingest(chosen)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder (searched recursively)")
        if folder:
            self._ingest([folder])

    def clear_files(self) -> None:
        self.files.clear()
        self.refresh_count()

    def refresh_count(self) -> None:
        count = len(self.files)
        self.count_label.configure(
            text="No files selected" if not count else f"{count} file(s) ready"
        )
        if count and not self.output_dir:
            self.set_output(default_output_dir([Path(p) for p in self.files.paths]))
        self.on_files_changed()

    def on_files_changed(self) -> None:
        """Hook for panels whose options depend on which files are loaded."""

    # -- options (subclasses override) -------------------------------------- #

    def _build_options_card(self) -> None:
        self.options_card = Card(self, self.palette, "Options", scale=self.scale)
        self.options_card.pack(fill="x", padx=4, pady=(0, 14))
        self.build_options(self.options_card)

    def build_options(self, parent) -> None:  # pragma: no cover - overridden
        label(
            parent,
            self.palette,
            "No options for this tool.",
            kind="small",
            scale=self.scale,
            muted=True,
        ).pack(fill="x", padx=16, pady=(0, 16))

    def row(self, parent, text: str, hint: str = "", name: str = "") -> ctk.CTkFrame:
        """A labelled options row with optional visible help text."""
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.pack(fill="x", padx=16, pady=(0, 12))
        if name:
            self.option_rows[name] = wrapper
        label(wrapper, self.palette, text, kind="body", scale=self.scale).pack(
            anchor="w", pady=(0, 4)
        )
        if hint:
            label(
                wrapper,
                self.palette,
                hint,
                kind="small",
                scale=self.scale,
                muted=True,
                wraplength=700,
            ).pack(anchor="w", pady=(0, 6))
        control_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        control_row.pack(fill="x")
        return control_row

    # -- output ------------------------------------------------------------- #

    def _build_output_card(self) -> None:
        card = Card(self, self.palette, "Save to", scale=self.scale)
        card.pack(fill="x", padx=4, pady=(0, 14))

        self.output_label = label(
            card,
            self.palette,
            "A 'ConvertAll Output' folder next to your first file",
            kind="small",
            scale=self.scale,
            muted=True,
            wraplength=700,
        )
        self.output_label.pack(fill="x", padx=16, pady=(0, 10))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        AccessibleButton(
            row,
            self.palette,
            "Choose folder…",
            self.choose_output,
            variant="secondary",
            scale=self.scale,
            height=40,
        ).pack(side="left")
        AccessibleButton(
            row,
            self.palette,
            "Open folder",
            self.open_output,
            variant="quiet",
            scale=self.scale,
            height=40,
        ).pack(side="left", padx=10)

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose the output folder")
        if folder:
            self.set_output(Path(folder))

    def set_output(self, path: Path) -> None:
        self.output_dir = Path(path)
        self.output_label.configure(text=str(self.output_dir))

    def open_output(self) -> None:
        if self.output_dir and self.output_dir.exists():
            _open_folder(self.output_dir)
        else:
            self.app.log_line("Output folder does not exist yet - run a job first.", "warn")

    # -- run ---------------------------------------------------------------- #

    def build_footer(self, holder) -> None:
        """The action bar lives outside the scroll area, so the primary action
        is always on screen no matter how far the panel is scrolled."""
        bar = ctk.CTkFrame(holder, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 4))

        self.run_button = AccessibleButton(
            bar,
            self.palette,
            f"{self.action_text}   (Ctrl+Enter)",
            self.run,
            variant="primary",
            scale=self.scale,
            height=52,
            width=270,
        )
        self.run_button.pack(side="left", padx=(4, 0))

        self.cancel_button = AccessibleButton(
            bar,
            self.palette,
            "Stop",
            self.app.cancel_job,
            variant="danger",
            scale=self.scale,
            height=52,
            width=110,
        )
        self.cancel_button.pack(side="left", padx=12)
        self.cancel_button.configure(state="disabled")

    def make_job(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def run(self) -> None:
        if not len(self.files):
            self.app.log_line("Add some files first.", "warn")
            messagebox.showinfo("ConvertAll", "Add at least one file before converting.")
            return
        if not self.output_dir:
            self.set_output(default_output_dir([Path(p) for p in self.files.paths]))

        worker, kwargs = self.make_job()
        kwargs["out_dir"] = self.output_dir
        self.app.run_job([Path(p) for p in self.files.paths], worker, self.title, **kwargs)

    def set_running(self, running: bool) -> None:
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")


class ConversionPanel(ToolPanel):
    key = "conversion"
    title = "Conversion"
    description = (
        "Use this when you need a specific file type. Add files, then pick what "
        "to turn them into - the list only offers formats every selected file "
        "can actually become."
    )
    accepted = convert_core.ACCEPTED
    file_label = "Files"
    drop_hint = "any image, audio, or video file"
    action_text = "Convert"
    dialog_name = "Images, audio and video"

    # Rows are re-packed in this order whenever visibility changes, so hiding
    # one never shuffles the rest.
    ROW_ORDER = ("target", "quality", "resize", "background", "resolution", "bgcolour", "codec")

    def build_options(self, parent) -> None:
        self.targets: list[str] = []
        self.background: Path | None = None
        self.target = tk.StringVar(value="")
        self.preset = tk.StringVar(value=images_core.PRESET_LABELS["lossless"])
        self.resize = tk.StringVar(value="Keep original size")
        self.resolution = tk.StringVar(value=list(media_core.RESOLUTIONS)[0])
        self.bg_colour = tk.StringVar(value="Black")
        self.video_codec = tk.StringVar(value=media_core.VIDEO_CODECS["h264"])

        row = self.row(parent, "Convert to", name="target")
        self.target_menu = option_menu(
            row,
            self.palette,
            ["-"],
            self.target,
            self.scale,
            width=180,
            command=lambda _v: self._apply_visibility(),
        )
        self.target_menu.pack(side="left")
        self.target_hint = label(
            row, self.palette, "", kind="small", scale=self.scale, muted=True, wraplength=460
        )
        self.target_hint.pack(side="left", padx=12)

        row = self.row(
            parent,
            "Quality",
            "Visually lossless keeps flat artwork bit-perfect and photos "
            "indistinguishable from the original.",
            name="quality",
        )
        option_menu(
            row,
            self.palette,
            list(images_core.PRESET_LABELS.values()),
            self.preset,
            self.scale,
            width=240,
        ).pack(side="left")

        row = self.row(parent, "Maximum size", name="resize")
        option_menu(
            row,
            self.palette,
            ["Keep original size", "4096 px", "2048 px", "1024 px", "512 px"],
            self.resize,
            self.scale,
        ).pack(side="left")

        row = self.row(
            parent,
            "Background image",
            "Optional. Scaled to fit and padded - never stretched.",
            name="background",
        )
        AccessibleButton(
            row,
            self.palette,
            "Choose image...",
            self._pick_background,
            variant="secondary",
            scale=self.scale,
            height=38,
        ).pack(side="left")
        AccessibleButton(
            row,
            self.palette,
            "Clear",
            self._clear_background,
            variant="quiet",
            scale=self.scale,
            height=38,
        ).pack(side="left", padx=10)
        self.bg_label = label(
            row,
            self.palette,
            "None - a flat colour will be used",
            kind="small",
            scale=self.scale,
            muted=True,
        )
        self.bg_label.pack(side="left", padx=10)

        row = self.row(parent, "Video size", name="resolution")
        option_menu(
            row,
            self.palette,
            list(media_core.RESOLUTIONS),
            self.resolution,
            self.scale,
            width=240,
        ).pack(side="left")

        row = self.row(parent, "Background colour", name="bgcolour")
        option_menu(
            row,
            self.palette,
            ["Black", "White", "Dark grey"],
            self.bg_colour,
            self.scale,
            width=180,
        ).pack(side="left")

        row = self.row(
            parent,
            "Video codec",
            "AV1 saves roughly twice what H.265 does, but takes around four "
            "times as long to encode.",
            name="codec",
        )
        option_menu(
            row,
            self.palette,
            list(media_core.VIDEO_CODECS.values()),
            self.video_codec,
            self.scale,
            width=340,
        ).pack(side="left")

        self._refresh_targets()

    # -- dynamic format list ------------------------------------------------ #

    def on_files_changed(self) -> None:
        if hasattr(self, "target_menu"):
            self._refresh_targets()

    def _refresh_targets(self) -> None:
        paths = [Path(p) for p in self.files.paths]
        self.targets = convert_core.targets_for(paths)
        labels = [convert_core.TARGET_LABELS[t] for t in self.targets]

        if labels:
            self.target_menu.configure(values=labels)
            if self.target.get() not in labels:
                self.target.set(labels[0])
        else:
            self.target_menu.configure(values=["-"])
            self.target.set("-")
        self._apply_visibility()

    def _current_target(self) -> str | None:
        for key, text in convert_core.TARGET_LABELS.items():
            if text == self.target.get() and key in self.targets:
                return key
        return None

    def _kinds(self) -> set[str]:
        return {kind_of(Path(p)) for p in self.files.paths}

    def _apply_visibility(self) -> None:
        target = self._current_target()
        kinds = self._kinds()
        visible = {"target"}

        if target in convert_core.IMAGE_TARGETS:
            visible |= {"quality", "resize"}
        elif target == "mp4":
            visible.add("quality")
            if "audio" in kinds:
                visible |= {"background", "resolution", "bgcolour"}
            if "video" in kinds:
                visible.add("codec")

        for name in self.ROW_ORDER:
            row = self.option_rows.get(name)
            if row is not None:
                row.pack_forget()
        for name in self.ROW_ORDER:
            row = self.option_rows.get(name)
            if row is not None and name in visible:
                row.pack(fill="x", padx=16, pady=(0, 12))

        if target:
            self.target_hint.configure(text=convert_core.TARGET_HINTS.get(target, ""))
        elif self.files.paths:
            self.target_hint.configure(
                text="These files have no target format in common - convert them in "
                "separate batches."
            )
        else:
            self.target_hint.configure(text="Add files to see what they can become.")

    def _pick_background(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose a background image", filetypes=_filetypes(IMAGE_EXTS, "Images")
        )
        if chosen:
            self.background = Path(chosen)
            self.bg_label.configure(text=self.background.name)

    def _clear_background(self) -> None:
        self.background = None
        self.bg_label.configure(text="None - a flat colour will be used")

    # -- run ---------------------------------------------------------------- #

    def run(self) -> None:
        if self.files.paths and not self.targets:
            self.app.log_line("Nothing to convert - these files have no format in common.", "warn")
            messagebox.showinfo(
                "ConvertAll",
                "These files have no target format in common.\n\n"
                "Convert them in separate batches - images together, audio together.",
            )
            return
        super().run()

    def make_job(self):
        preset_key = next(k for k, v in images_core.PRESET_LABELS.items() if v == self.preset.get())
        codec_key = next(
            k for k, v in media_core.VIDEO_CODECS.items() if v == self.video_codec.get()
        )
        chosen = self.resize.get()
        colours = {"Black": "black", "White": "white", "Dark grey": "0x1E2936"}
        return convert_file, {
            "target": self._current_target() or "",
            "preset": preset_key,
            "max_dimension": None if chosen.startswith("Keep") else int(chosen.split()[0]),
            "background": self.background,
            "resolution": media_core.RESOLUTIONS[self.resolution.get()],
            "background_color": colours[self.bg_colour.get()],
            "video_codec": codec_key,
        }


class TracePanel(ToolPanel):
    key = "trace"
    title = "Tracing (Raster to Vector)"
    description = (
        "Auto-trace artwork into clean, infinitely scalable .svg curves. Use the "
        "colour engine for logos and illustration; the black & white engine gives "
        "the crispest result for line art and silhouettes."
    )
    accepted = IMAGE_EXTS
    file_label = "Files"
    drop_hint = "any image to trace"
    action_text = "Trace to SVG"
    dialog_name = "Images"

    def build_options(self, parent) -> None:
        self.engine = tk.StringVar(value=trace_core.ENGINES["color"])
        self.detail = tk.StringVar(value=trace_core.DETAIL_LABELS["medium"])
        self.threshold = tk.IntVar(value=128)
        self.invert = tk.BooleanVar(value=False)

        row = self.row(parent, "Engine")
        option_menu(
            row,
            self.palette,
            list(trace_core.ENGINES.values()),
            self.engine,
            self.scale,
            width=320,
            command=self._toggle_mono,
        ).pack(side="left")

        row = self.row(
            parent, "Detail", "Simplified drops small specks and produces fewer, smoother paths."
        )
        option_menu(
            row,
            self.palette,
            list(trace_core.DETAIL_LABELS.values()),
            self.detail,
            self.scale,
            width=220,
        ).pack(side="left")

        self.mono_row = self.row(
            parent,
            "Black & white threshold",
            "Pixels darker than this become filled shapes. Only used by the black & white engine.",
        )
        self.threshold_value = label(
            self.mono_row, self.palette, "128", kind="body", scale=self.scale
        )
        slider = ctk.CTkSlider(
            self.mono_row,
            from_=1,
            to=254,
            number_of_steps=253,
            variable=self.threshold,
            width=280,
            fg_color=self.palette.surface_alt,
            progress_color=self.palette.accent,
            button_color=self.palette.accent,
            button_hover_color=self.palette.accent_hover,
            command=lambda v: self.threshold_value.configure(text=str(int(float(v)))),
        )
        slider.pack(side="left")
        self.threshold_value.pack(side="left", padx=12)
        checkbox(
            self.mono_row, self.palette, "Invert (trace light shapes)", self.invert, self.scale
        ).pack(side="left", padx=12)
        self._toggle_mono()

    def _toggle_mono(self, *_args) -> None:
        is_mono = self.engine.get() == trace_core.ENGINES["mono"]
        for child in self.mono_row.winfo_children():
            # Labels have no 'state' option; skipping them is fine.
            with contextlib.suppress(Exception):
                child.configure(state="normal" if is_mono else "disabled")

    def make_job(self):
        engine_key = next(k for k, v in trace_core.ENGINES.items() if v == self.engine.get())
        detail_key = next(k for k, v in trace_core.DETAIL_LABELS.items() if v == self.detail.get())
        return trace_image, {
            "engine": engine_key,
            "detail": detail_key,
            "threshold": int(self.threshold.get()),
            "invert": bool(self.invert.get()),
        }


class SplitPanel(ToolPanel):
    key = "split"
    title = "Split SVG Layers"
    description = (
        "Break a layered .svg into one standalone file per layer, group or shape. "
        "Gradients, filters and CSS are copied into every piece and the original "
        "viewBox is kept, so the parts stay in register and can be stacked back "
        "together exactly."
    )
    accepted = VECTOR_EXTS
    file_label = "Files"
    drop_hint = "any .svg file"
    action_text = "Split files"
    dialog_name = "SVG files"

    def build_options(self, parent) -> None:
        self.mode = tk.StringVar(value=svg_core.MODES["auto"])
        self.subfolder = tk.BooleanVar(value=True)

        row = self.row(
            parent,
            "Split by",
            "Auto uses layers when the file has them and falls back to "
            "individual shapes when it does not.",
        )
        option_menu(
            row, self.palette, list(svg_core.MODES.values()), self.mode, self.scale, width=300
        ).pack(side="left")

        row = self.row(parent, "Organisation")
        checkbox(
            row,
            self.palette,
            "Put each file's pieces in their own subfolder",
            self.subfolder,
            self.scale,
        ).pack(side="left")

    def make_job(self):
        mode_key = next(k for k, v in svg_core.MODES.items() if v == self.mode.get())
        return split_svg, {
            "mode": mode_key,
            "subfolder_per_file": bool(self.subfolder.get()),
        }


class CompressionPanel(ToolPanel):
    key = "compress"
    title = "Compression"
    description = (
        "Use this when a smaller file is the goal and the format is not. Each "
        "file type gets the encoder settings that suit it: flat artwork goes "
        "true-lossless, WAV becomes FLAC, video is re-encoded in the codec you "
        "pick, and SVG has its editor metadata stripped. Already-lossy audio is "
        "left untouched, and any file that would grow keeps its original bytes."
    )
    accepted = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS | VECTOR_EXTS
    file_label = "Files"
    drop_hint = "any image, audio, video, or SVG file"
    action_text = "Compress"
    dialog_name = "Media files"

    def build_options(self, parent) -> None:
        self.preset = tk.StringVar(value=images_core.PRESET_LABELS["lossless"])
        self.to_webp = tk.BooleanVar(value=False)
        self.video_codec = tk.StringVar(value=media_core.VIDEO_CODECS["h264"])

        row = self.row(
            parent,
            "Target quality",
            "Visually lossless is the safe default - keep it unless you "
            "specifically need smaller files.",
        )
        option_menu(
            row,
            self.palette,
            list(images_core.PRESET_LABELS.values()),
            self.preset,
            self.scale,
            width=240,
        ).pack(side="left")

        row = self.row(parent, "Images")
        checkbox(
            row,
            self.palette,
            "Also convert images to WebP (much smaller)",
            self.to_webp,
            self.scale,
        ).pack(side="left")

        row = self.row(
            parent,
            "Video codec",
            "AV1 saves roughly twice what H.265 does, but takes around four "
            "times as long to encode - worth it for large recordings you are "
            "archiving. H.264 is the safe choice if the file must play anywhere.",
        )
        option_menu(
            row,
            self.palette,
            list(media_core.VIDEO_CODECS.values()),
            self.video_codec,
            self.scale,
            width=340,
        ).pack(side="left")

    def make_job(self):
        preset_key = next(k for k, v in images_core.PRESET_LABELS.items() if v == self.preset.get())
        codec_key = next(
            k for k, v in media_core.VIDEO_CODECS.items() if v == self.video_codec.get()
        )
        return smart_compress, {
            "preset": preset_key,
            "images_to_webp": bool(self.to_webp.get()),
            "video_codec": codec_key,
        }


TOOL_GROUPS = [
    ("Tools", [ConversionPanel, CompressionPanel]),
    ("Vector art tools", [TracePanel, SplitPanel]),
]
PANELS = [cls for _, group in TOOL_GROUPS for cls in group]


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #


class ConvertAllApp(_Root):
    def __init__(self, palette_key: str = "dark", scale: float = 1.0):
        ctk.set_appearance_mode("dark")
        super().__init__()

        self.palette: Palette = PALETTES[palette_key]
        self.scale = scale
        self.runner = JobRunner()
        self.active_key = PANELS[0].key
        self._panel_state: dict[str, dict] = {}

        self.title(f"ConvertAll {__version__}")
        self.geometry("1180x820")
        self.minsize(980, 660)
        with contextlib.suppress(Exception):
            self.iconbitmap(str(ASSETS / "icon.ico"))

        self._build()
        self._bind_shortcuts()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- construction ------------------------------------------------------- #

    def _build(self) -> None:
        p = self.palette
        self.configure(fg_color=p.bg)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=1, sticky="nsew", padx=(0, 18), pady=(0, 0))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # Each panel sits in its own plain holder frame. CTkScrollableFrame
        # delegates its geometry calls to an internal parent frame, so raising
        # the panel directly would not change what is on top - the holder is
        # what we stack.
        self.panels: dict[str, ToolPanel] = {}
        self.holders: dict[str, ctk.CTkFrame] = {}
        for cls in PANELS:
            holder = ctk.CTkFrame(self.content, fg_color="transparent")
            holder.grid(row=0, column=0, sticky="nsew")
            holder.grid_rowconfigure(0, weight=1)
            holder.grid_columnconfigure(0, weight=1)

            panel = cls(holder, self)
            panel.grid(row=0, column=0, sticky="nsew")
            panel.build_footer(holder)

            self.panels[cls.key] = panel
            self.holders[cls.key] = holder

        self._build_activity()
        self.select_tool(self.active_key)

    def _build_header(self) -> None:
        p = self.palette
        header = ctk.CTkFrame(self, fg_color=p.surface, corner_radius=0, border_width=0, height=84)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w", padx=(22, 0), pady=14)
        ctk.CTkLabel(
            titles,
            text="ConvertAll",
            text_color=p.accent,
            font=(FONT_FAMILY, sized("display", self.scale), "bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="Media conversion, built for clarity",
            text_color=p.text_muted,
            font=(FONT_FAMILY, sized("small", self.scale)),
            anchor="w",
        ).pack(anchor="w")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=2, sticky="e", padx=(0, 22), pady=14)
        for text, command in (
            ("A−", lambda: self.change_scale(-SCALE_STEP)),
            ("A+", lambda: self.change_scale(SCALE_STEP)),
            ("Contrast", self.toggle_palette),
            ("Help (F1)", self.show_help),
        ):
            AccessibleButton(
                controls,
                p,
                text,
                command,
                variant="secondary",
                scale=self.scale,
                height=42,
                width=96 if len(text) > 3 else 56,
            ).pack(side="left", padx=5)

    def _build_sidebar(self) -> None:
        p = self.palette
        bar = ctk.CTkFrame(self, fg_color=p.surface, corner_radius=0, width=250)
        bar.grid(row=1, column=0, sticky="nsw", padx=(0, 18))
        bar.grid_propagate(False)

        self.nav_buttons: dict[str, AccessibleButton] = {}
        index = 0
        for position, (heading, group) in enumerate(TOOL_GROUPS):
            ctk.CTkLabel(
                bar,
                text=heading.upper(),
                text_color=p.text_muted,
                font=(FONT_FAMILY, sized("small", self.scale), "bold"),
                anchor="w",
            ).pack(fill="x", padx=20, pady=(18 if position == 0 else 16, 8))

            for cls in group:
                index += 1
                button = AccessibleButton(
                    bar,
                    p,
                    f"{index}.  {cls.title}",
                    lambda k=cls.key: self.select_tool(k),
                    variant="secondary",
                    scale=self.scale,
                    height=46,
                    anchor="w",
                )
                button.pack(fill="x", padx=16, pady=4)
                self.nav_buttons[cls.key] = button

        ctk.CTkLabel(
            bar,
            text=f"v{__version__}",
            text_color=p.text_muted,
            font=(FONT_FAMILY, sized("small", self.scale)),
        ).pack(side="bottom", pady=16)

    def _build_activity(self) -> None:
        p = self.palette
        card = Card(self, p, scale=self.scale)
        card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 12))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 6))
        top.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(
            top,
            text="Ready.",
            text_color=p.text,
            anchor="w",
            font=(FONT_FAMILY, sized("body", self.scale), "bold"),
        )
        self.status.grid(row=0, column=0, sticky="w")
        AccessibleButton(
            top,
            p,
            "Clear log",
            self._clear_log,
            variant="quiet",
            scale=self.scale,
            height=34,
            width=110,
        ).grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(
            card,
            height=14,
            corner_radius=7,
            fg_color=p.surface_alt,
            progress_color=p.accent,
            border_color=p.border,
            border_width=2,
        )
        self.progress.set(0)
        self.progress.pack(fill="x", padx=16, pady=(0, 8))

        self.log = LogView(card, p, scale=self.scale, height=5)
        self.log.pack(fill="x", padx=16, pady=(0, 12))
        self.log_line(
            "ConvertAll ready. Choose a tool on the left, add files, then press Convert.", "head"
        )
        if not DND_AVAILABLE:
            self.log_line("Tip: pip install tkinterdnd2 to enable drag and drop.", "warn")

    # -- behaviour ---------------------------------------------------------- #

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda e: self.current_panel().add_files())
        self.bind("<Control-O>", lambda e: self.current_panel().add_folder())
        self.bind("<Control-Return>", lambda e: self.current_panel().run())
        self.bind("<Escape>", lambda e: self.cancel_job())
        self.bind("<Control-d>", lambda e: self.toggle_palette())
        self.bind("<Control-plus>", lambda e: self.change_scale(SCALE_STEP))
        self.bind("<Control-equal>", lambda e: self.change_scale(SCALE_STEP))
        self.bind("<Control-minus>", lambda e: self.change_scale(-SCALE_STEP))
        self.bind("<Control-0>", lambda e: self.set_scale(1.0))
        self.bind("<F1>", lambda e: self.show_help())
        for index, cls in enumerate(PANELS, start=1):
            self.bind(f"<Control-Key-{index}>", lambda e, k=cls.key: self.select_tool(k))

    def current_panel(self) -> ToolPanel:
        return self.panels[self.active_key]

    def select_tool(self, key: str) -> None:
        self.active_key = key
        self.holders[key].tkraise()
        for panel_key, button in self.nav_buttons.items():
            button.set_active(panel_key == key)
        self.set_status(f"{self.panels[key].title} - ready.")

    def log_line(self, text: str, tag: str | None = None) -> None:
        self.log.write(text, tag)

    def _clear_log(self) -> None:
        self.log.clear()

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    # -- jobs --------------------------------------------------------------- #

    def run_job(self, files, worker, title: str, **kwargs) -> None:
        if self.runner.busy:
            self.log_line("A job is already running.", "warn")
            return
        self.log_line("")
        self.log_line(f"{title}: {len(files)} file(s) -> {kwargs.get('out_dir')}", "head")
        self.progress.set(0)
        self.current_panel().set_running(True)
        self.runner.start(files, worker, **kwargs)

    def cancel_job(self) -> None:
        if self.runner.busy:
            self.runner.cancel()
            self.set_status("Stopping after the current file…")

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.runner.events.get_nowait()
            except Exception:
                break
            self._handle_event(kind, payload)
        self.after(80, self._drain_events)

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "progress":
            index, total, name = payload
            self.progress.set((index - 1) / max(total, 1))
            self.set_status(f"[{index}/{total}] {name}")
        elif kind == "result":
            self.log_line("  " + payload.summary(), "ok" if payload.ok else "bad")
        elif kind == "log":
            if payload:
                self.log_line("  " + str(payload))
        elif kind == "trace":
            pass  # full traceback stays available for debugging if needed
        elif kind == "done":
            self._finish(payload)

    def _finish(self, summary: JobSummary) -> None:
        self.progress.set(1.0 if not summary.cancelled else 0)
        self.current_panel().set_running(False)

        parts = [f"{summary.succeeded} succeeded"]
        if summary.failed:
            parts.append(f"{summary.failed} failed")
        if summary.cancelled:
            parts.append("cancelled")
        if summary.bytes_in and summary.bytes_out:
            parts.append(
                f"{human(summary.bytes_in)} -> {human(summary.bytes_out)} "
                f"({summary.saved_pct:+.0f}%)"
            )
        message = "Done: " + ", ".join(parts) + "."
        self.set_status(message)
        self.log_line(message, "bad" if summary.failed else "ok")
        if summary.outputs:
            self.log_line(f"  {len(summary.outputs)} file(s) written.", "ok")

    # -- accessibility controls --------------------------------------------- #

    def toggle_palette(self) -> None:
        keys = list(PALETTES)
        nxt = keys[(keys.index(self.palette.key) + 1) % len(keys)]
        self._restart(nxt, self.scale)

    def change_scale(self, delta: float) -> None:
        self.set_scale(self.scale + delta)

    def set_scale(self, value: float) -> None:
        value = round(min(MAX_SCALE, max(MIN_SCALE, value)), 2)
        if value != self.scale:
            self._restart(self.palette.key, value)

    def _restart(self, palette_key: str, scale: float) -> None:
        """Rebuild the window with new theme settings, keeping the file lists."""
        state = {
            key: {
                "files": list(panel.files.paths),
                "output": panel.output_dir,
            }
            for key, panel in self.panels.items()
        }
        active, geometry = self.active_key, self.geometry()

        for child in self.winfo_children():
            child.destroy()

        self.palette = PALETTES[palette_key]
        self.scale = scale
        self._build()

        for key, saved in state.items():
            panel = self.panels[key]
            panel.files.add(saved["files"])
            if saved["output"]:
                panel.set_output(saved["output"])
            panel.refresh_count()

        self.select_tool(active)
        self.geometry(geometry)
        self.log_line(f"Display: {self.palette.label}, text size {int(self.scale * 100)}%.", "head")

    def show_help(self) -> None:
        p = self.palette
        window = ctk.CTkToplevel(self)
        window.title("ConvertAll - keyboard shortcuts")
        window.geometry("560x520")
        window.configure(fg_color=p.bg)
        window.transient(self)

        shortcuts = [
            ("Ctrl + 1 … 4", "Switch tool"),
            ("Ctrl + O", "Add files"),
            ("Ctrl + Shift + O", "Add a folder (searched recursively)"),
            ("Ctrl + Enter", "Start converting"),
            ("Esc", "Stop after the current file"),
            ("Delete", "Remove the selected files from the list"),
            ("Tab / Shift + Tab", "Move between controls"),
            ("Enter or Space", "Activate the focused control"),
            ("Ctrl + D", "Switch between the two high-contrast palettes"),
            ("Ctrl + +  /  Ctrl + -", "Grow or shrink every text size"),
            ("Ctrl + 0", "Reset the text size"),
            ("F1", "This window"),
        ]
        frame = ctk.CTkScrollableFrame(window, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        for keys, meaning in shortcuts:
            row = ctk.CTkFrame(frame, fg_color=p.surface, corner_radius=8)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(
                row,
                text=keys,
                text_color=p.accent,
                width=170,
                anchor="w",
                font=(FONT_FAMILY, sized("body", self.scale), "bold"),
            ).pack(side="left", padx=12, pady=9)
            ctk.CTkLabel(
                row,
                text=meaning,
                text_color=p.text,
                anchor="w",
                font=(FONT_FAMILY, sized("body", self.scale)),
            ).pack(side="left", padx=6)

        AccessibleButton(
            window, p, "Close", window.destroy, variant="primary", scale=self.scale, height=44
        ).pack(pady=(0, 18))
        window.after(120, window.focus_force)

    def _on_close(self) -> None:
        if self.runner.busy:
            if not messagebox.askokcancel("ConvertAll", "A job is still running. Quit anyway?"):
                return
            self.runner.cancel()
        self.destroy()
