"""Accessible building blocks used by the ConvertAll window.

Accessibility notes that drive the code below:

* Every interactive control is reachable with Tab and activates with Enter or
  Space, and shows a 3px warm focus ring. The accent is a cool mint and the
  ring is orange - about 125 degrees apart - so "where am I" and "what is
  under the mouse" can never be confused, and focus always outranks hover.
* Hover changes *both* the label colour and the border, not just the fill, so
  it stays readable for users who cannot separate the two hues.
* Help text is rendered as visible labels rather than hover tooltips, because
  tooltips are invisible to keyboard and screen-reader users.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

import customtkinter as ctk

from .core.common import human, size_of
from .theme import FONT_FAMILY, MONO_FAMILY, Palette, sized

CORNER = 8


def _force(widget, **options) -> None:
    """Set raw Tk options CustomTkinter does not expose (e.g. takefocus)."""
    with contextlib.suppress(Exception):
        tk.Frame.configure(widget, **options)


def add_focus_ring(button: ctk.CTkButton, palette: Palette, resting_border: str) -> None:
    """Give a CTk button real keyboard focus, with a visible ring."""
    _force(button, takefocus=1)

    def on_focus(_event=None):
        button._has_focus_ring = True
        button.configure(border_color=palette.focus, border_width=3)

    def off_focus(_event=None):
        button._has_focus_ring = False
        button.configure(
            border_color=getattr(button, "_resting_border", resting_border), border_width=2
        )

    def activate(_event=None):
        button.invoke()
        return "break"

    button.bind("<FocusIn>", on_focus, add="+")
    button.bind("<FocusOut>", off_focus, add="+")
    button.bind("<Return>", activate, add="+")
    button.bind("<KP_Enter>", activate, add="+")
    button.bind("<space>", activate, add="+")
    button.bind("<Button-1>", lambda e: button.focus_set(), add="+")


class AccessibleButton(ctk.CTkButton):
    """A button with high-contrast hover, focus ring and keyboard activation."""

    def __init__(
        self,
        master,
        palette: Palette,
        text: str,
        command: Callable[[], None] | None = None,
        variant: str = "primary",
        scale: float = 1.0,
        **kwargs,
    ) -> None:
        self.palette = palette
        weight = "bold" if variant in ("primary", "nav") else "normal"
        size = sized("title" if variant == "primary" else "body", scale)

        # Only the primary action fills with the accent. Everything else hovers
        # to a quiet surface tint and switches its *label* to the accent - a
        # whole button flooding with colour on every mouse-over is what makes an
        # interface tiring to use.
        styles = {
            "primary": {
                "fill": palette.accent,
                "hover": palette.accent_hover,
                "fg": palette.on_accent,
                "hover_fg": palette.on_accent,
                "border": palette.accent,
                "hover_border": palette.accent_hover,
            },
            "secondary": {
                "fill": "transparent",
                "hover": palette.surface_alt,
                "fg": palette.text,
                "hover_fg": palette.accent,
                "border": palette.border_strong,
                "hover_border": palette.accent,
            },
            "quiet": {
                "fill": "transparent",
                "hover": palette.surface_alt,
                "fg": palette.text_muted,
                "hover_fg": palette.text,
                "border": palette.border,
                "hover_border": palette.border_strong,
            },
            "danger": {
                "fill": "transparent",
                "hover": palette.surface_alt,
                "fg": palette.error,
                "hover_fg": palette.error,
                "border": palette.error,
                "hover_border": palette.error,
            },
        }
        style = styles.get(variant, styles["primary"])
        fill, hover = style["fill"], style["hover"]
        border = style["border"]
        self._has_focus_ring = False
        self._resting_border = border
        self._label_fg = style["fg"]
        self._hover_fg = style["hover_fg"]
        self._hover_border = style["hover_border"]

        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=fill,
            hover_color=hover,
            text_color=style["fg"],
            border_color=border,
            border_width=2,
            corner_radius=CORNER,
            font=(FONT_FAMILY, size, weight),
            cursor="hand2",
            **kwargs,
        )
        self.bind("<Enter>", self._hover_on, add="+")
        self.bind("<Leave>", self._hover_off, add="+")
        add_focus_ring(self, palette, border)

    # These deliberately avoid CTkButton's own _on_enter/_on_leave names.
    # Defining methods with those names silently overrides the parent's, and
    # CTkButton sets self._mouse_inside inside them - which _on_release checks
    # before calling the command. Shadowing them makes every button dead to the
    # mouse while still looking and hovering correctly.
    def _hover_on(self, _event=None) -> None:
        self.configure(text_color=self._hover_fg)
        # Never paint over the focus ring: keyboard position outranks the mouse.
        if not self._has_focus_ring:
            self.configure(border_color=self._hover_border)

    def _hover_off(self, _event=None) -> None:
        self.configure(text_color=self._label_fg)
        if not self._has_focus_ring:
            self.configure(border_color=self._resting_border)

    def set_active(self, active: bool) -> None:
        """Mark the current tool in the sidebar.

        The selected item gets a filled accent pill - one small saturated block
        on screen, which reads instantly without the eye strain of colouring
        every control.
        """
        if active:
            self._label_fg = self.palette.on_accent
            self._hover_fg = self.palette.on_accent
            self._resting_border = self.palette.accent
            self._hover_border = self.palette.accent_hover
            self.configure(
                fg_color=self.palette.accent,
                hover_color=self.palette.accent_hover,
                text_color=self.palette.on_accent,
                border_color=self.palette.accent,
            )
        else:
            self._label_fg = self.palette.text
            self._hover_fg = self.palette.accent
            self._resting_border = self.palette.border_strong
            self._hover_border = self.palette.accent
            self.configure(
                fg_color="transparent",
                hover_color=self.palette.surface_alt,
                text_color=self.palette.text,
                border_color=self.palette.border_strong,
            )


class Card(ctk.CTkFrame):
    """A titled surface panel."""

    def __init__(self, master, palette: Palette, title: str = "", scale: float = 1.0, **kwargs):
        super().__init__(
            master,
            fg_color=palette.surface,
            border_color=palette.border,
            border_width=1,
            corner_radius=CORNER + 2,
            **kwargs,
        )
        self.palette = palette
        self.body = self
        if title:
            heading = ctk.CTkLabel(
                self,
                text=title,
                text_color=palette.text,
                font=(FONT_FAMILY, sized("title", scale), "bold"),
                anchor="w",
            )
            heading.pack(fill="x", padx=16, pady=(14, 6))


class FileList(ctk.CTkFrame):
    """A real table: name, original size, estimated size after.

    ttk.Treeview rather than a hand-rolled widget - it gives resizable column
    headings, keyboard navigation and screen-reader support for free, none of
    which a stack of custom frames would.
    """

    COLUMNS = (("size", "Size", 110), ("estimate", "Est. after", 110))

    def __init__(self, master, palette: Palette, scale: float = 1.0, height: int = 10):
        super().__init__(master, fg_color="transparent")
        self.palette = palette
        self.paths: list[str] = []
        self._estimator = None

        self._style_treeview(palette, scale)
        self.tree = ttk.Treeview(
            self,
            columns=[c[0] for c in self.COLUMNS],
            selectmode="extended",
            height=height,
            style="ConvertAll.Treeview",
        )
        self.tree.heading("#0", text="File", anchor="w")
        self.tree.column("#0", width=430, minwidth=180, stretch=True, anchor="w")
        for key, title, width in self.COLUMNS:
            self.tree.heading(key, text=title, anchor="e")
            self.tree.column(key, width=width, minwidth=70, stretch=False, anchor="e")

        scrollbar = ctk.CTkScrollbar(
            self,
            command=self.tree.yview,
            button_color=palette.border_strong,
            button_hover_color=palette.accent,
            fg_color=palette.surface,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(6, 0))
        scrollbar.configure(height=1)

        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<BackSpace>", lambda e: self.remove_selected())

    def _style_treeview(self, palette: Palette, scale: float) -> None:
        style = ttk.Style()
        # "clam" is the only built-in theme that honours these colour options on
        # Windows; the native theme ignores them and renders light grey.
        with contextlib.suppress(Exception):
            style.theme_use("clam")
        row_height = max(22, int(sized("body", scale) * 1.9))
        style.configure(
            "ConvertAll.Treeview",
            background=palette.surface_alt,
            fieldbackground=palette.surface_alt,
            foreground=palette.text,
            borderwidth=0,
            rowheight=row_height,
            font=(FONT_FAMILY, sized("small", scale)),
        )
        style.configure(
            "ConvertAll.Treeview.Heading",
            background=palette.surface,
            foreground=palette.text_muted,
            relief="flat",
            borderwidth=1,
            font=(FONT_FAMILY, sized("small", scale), "bold"),
        )
        style.map(
            "ConvertAll.Treeview.Heading",
            background=[("active", palette.surface_alt)],
            foreground=[("active", palette.text)],
        )
        style.map(
            "ConvertAll.Treeview",
            background=[("selected", palette.accent)],
            foreground=[("selected", palette.on_accent)],
        )

    @property
    def drop_target(self):
        return self.tree

    def set_estimator(self, estimator) -> None:
        """Called by the panel whenever an option changes the likely output."""
        self._estimator = estimator
        self.refresh_estimates()

    def refresh_estimates(self) -> None:
        for item, path in zip(self.tree.get_children(), self.paths, strict=False):
            self.tree.set(item, "estimate", self._estimate(path))

    def _estimate(self, path: str) -> str:
        if self._estimator is None:
            return "—"
        try:
            return self._estimator(Path(path))
        except Exception:
            return "—"

    def add(self, paths) -> int:
        known = {p.lower() for p in self.paths}
        added = 0
        for path in paths:
            text = str(path)
            if text.lower() in known:
                continue
            known.add(text.lower())
            self.paths.append(text)
            self.tree.insert(
                "",
                "end",
                text=Path(text).name,
                values=(human(size_of(Path(text))), self._estimate(text)),
            )
            added += 1
        return added

    def remove_selected(self) -> None:
        for item in self.tree.selection():
            index = self.tree.index(item)
            self.tree.delete(item)
            del self.paths[index]

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()

    def __len__(self) -> int:
        return len(self.paths)


class LogView(ctk.CTkFrame):
    """Read-only, selectable, colour-coded activity log."""

    def __init__(self, master, palette: Palette, scale: float = 1.0, height: int = 9):
        super().__init__(master, fg_color="transparent")
        self.palette = palette

        self.text = tk.Text(
            self,
            height=height,
            wrap="word",
            bg=palette.surface_alt,
            fg=palette.text_muted,
            insertbackground=palette.text,
            selectbackground=palette.accent,
            selectforeground=palette.on_accent,
            highlightthickness=2,
            highlightbackground=palette.border,
            highlightcolor=palette.focus,
            borderwidth=0,
            relief="flat",
            padx=12,
            pady=10,
            font=(MONO_FAMILY, sized("mono", scale)),
        )
        scrollbar = ctk.CTkScrollbar(
            self,
            command=self.text.yview,
            button_color=palette.border_strong,
            button_hover_color=palette.accent,
            fg_color=palette.surface,
        )
        self.text.configure(yscrollcommand=scrollbar.set, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(6, 0))

        for tag, colour in (
            ("ok", palette.success),
            ("bad", palette.error),
            ("warn", palette.warning),
            ("head", palette.accent),
        ):
            self.text.tag_configure(tag, foreground=colour)

        # See FileList: stop the scrollbar's default height from driving the
        # frame, so `height` really means "this many lines".
        scrollbar.configure(height=1)

    def write(self, line: str, tag: str | None = None, link: bool = False) -> None:
        self.text.configure(state="normal")
        tags = tuple(t for t in (tag, "link" if link else None) if t)
        self.text.insert("end", line + "\n", tags)
        self.text.see("end")
        self.text.configure(state="disabled")

    def on_link_click(self, command) -> None:
        """Make lines written with link=True clickable, as the log promises."""
        self.text.tag_configure("link", underline=True)
        self.text.tag_bind("link", "<Button-1>", lambda _e: command())
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.configure(cursor=""))

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


def label(
    master,
    palette: Palette,
    text: str,
    *,
    kind: str = "body",
    scale: float = 1.0,
    muted: bool = False,
    **kwargs,
) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        text_color=palette.text_muted if muted else palette.text,
        font=(
            FONT_FAMILY,
            sized(kind, scale),
            "bold" if kind in ("title", "display") else "normal",
        ),
        anchor="w",
        justify="left",
        **kwargs,
    )


def option_menu(
    master,
    palette: Palette,
    values: list[str],
    variable,
    scale: float = 1.0,
    width: int = 220,
    command=None,
) -> ctk.CTkOptionMenu:
    menu = ctk.CTkOptionMenu(
        master,
        values=values,
        variable=variable,
        command=command,
        width=width,
        height=38,
        corner_radius=CORNER,
        fg_color=palette.surface_alt,
        button_color=palette.border_strong,
        button_hover_color=palette.accent,
        text_color=palette.text,
        dropdown_fg_color=palette.surface_alt,
        dropdown_text_color=palette.text,
        dropdown_hover_color=palette.accent,
        font=(FONT_FAMILY, sized("body", scale)),
        dropdown_font=(FONT_FAMILY, sized("body", scale)),
        cursor="hand2",
    )
    _force(menu, takefocus=1)
    menu.bind("<FocusIn>", lambda e: menu.configure(button_color=palette.focus), add="+")
    menu.bind("<FocusOut>", lambda e: menu.configure(button_color=palette.border_strong), add="+")
    return menu


def checkbox(master, palette: Palette, text: str, variable, scale: float = 1.0) -> ctk.CTkCheckBox:
    box = ctk.CTkCheckBox(
        master,
        text=text,
        variable=variable,
        onvalue=True,
        offvalue=False,
        text_color=palette.text,
        fg_color=palette.accent,
        hover_color=palette.accent_hover,
        checkmark_color=palette.on_accent,
        border_color=palette.border_strong,
        border_width=2,
        corner_radius=6,
        font=(FONT_FAMILY, sized("body", scale)),
        cursor="hand2",
    )
    _force(box, takefocus=1)
    box.bind("<FocusIn>", lambda e: box.configure(border_color=palette.focus), add="+")
    box.bind("<FocusOut>", lambda e: box.configure(border_color=palette.border_strong), add="+")
    box.bind("<Return>", lambda e: box.toggle(), add="+")
    box.bind("<space>", lambda e: box.toggle(), add="+")
    return box
