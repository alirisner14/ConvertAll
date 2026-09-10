"""Accessible building blocks used by the ConvertAll window.

Accessibility notes that drive the code below:

* Every interactive control is reachable with Tab and activates with Enter or
  Space, and shows a 3px cyan focus ring that is visually distinct from the
  amber hover state - so "where am I" and "what will react to my mouse" are
  never the same signal.
* Hover states change *both* fill and border, not just fill, which keeps them
  readable for users who cannot distinguish the two colours.
* Help text is rendered as visible labels rather than hover tooltips, because
  tooltips are invisible to keyboard and screen-reader users.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from .theme import FONT_FAMILY, MONO_FAMILY, Palette, sized

CORNER = 10


def _force(widget, **options) -> None:
    """Set raw Tk options CustomTkinter does not expose (e.g. takefocus)."""
    with contextlib.suppress(Exception):
        tk.Frame.configure(widget, **options)


def add_focus_ring(button: ctk.CTkButton, palette: Palette, resting_border: str) -> None:
    """Give a CTk button real keyboard focus, with a visible ring."""
    _force(button, takefocus=1)

    def on_focus(_event=None):
        button.configure(border_color=palette.focus, border_width=3)

    def off_focus(_event=None):
        button.configure(border_color=resting_border, border_width=2)

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

        styles = {
            # variant: (fill, hover fill, label, hover label, border)
            "primary": (
                palette.accent,
                palette.accent_hover,
                palette.on_accent,
                palette.on_accent,
                palette.accent,
            ),
            "secondary": (
                "transparent",
                palette.accent,
                palette.text,
                palette.on_accent,
                palette.border_strong,
            ),
            "quiet": (
                "transparent",
                palette.surface_alt,
                palette.text_muted,
                palette.text,
                palette.border,
            ),
            "danger": ("transparent", palette.error, palette.error, palette.bg, palette.error),
        }
        fill, hover, label_fg, hover_fg, border = styles.get(variant, styles["primary"])
        self._resting_border = border
        self._label_fg = label_fg
        self._hover_fg = hover_fg

        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=fill,
            hover_color=hover,
            text_color=label_fg,
            border_color=border,
            border_width=2,
            corner_radius=CORNER,
            font=(FONT_FAMILY, size, weight),
            cursor="hand2",
            **kwargs,
        )
        # Flip the label colour on hover too, so contrast never drops.
        self.bind("<Enter>", lambda e: self.configure(text_color=self._hover_fg), add="+")
        self.bind("<Leave>", lambda e: self.configure(text_color=self._label_fg), add="+")
        add_focus_ring(self, palette, border)

    def set_active(self, active: bool) -> None:
        """Used by the sidebar to mark the current tool."""
        if active:
            self.configure(
                fg_color=self.palette.accent,
                text_color=self.palette.on_accent,
                border_color=self.palette.accent,
            )
            self._label_fg = self.palette.on_accent
        else:
            self.configure(
                fg_color="transparent",
                text_color=self.palette.text,
                border_color=self._resting_border,
            )
            self._label_fg = self.palette.text


class Card(ctk.CTkFrame):
    """A titled surface panel."""

    def __init__(self, master, palette: Palette, title: str = "", scale: float = 1.0, **kwargs):
        super().__init__(
            master,
            fg_color=palette.surface,
            border_color=palette.border,
            border_width=2,
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
    """A native Listbox - it gives real keyboard navigation and screen-reader
    support that a stack of custom frames cannot."""

    def __init__(self, master, palette: Palette, scale: float = 1.0, height: int = 10):
        super().__init__(master, fg_color="transparent")
        self.palette = palette
        self.paths: list[str] = []

        self.listbox = tk.Listbox(
            self,
            height=height,
            activestyle="none",
            selectmode="extended",
            bg=palette.surface_alt,
            fg=palette.text,
            selectbackground=palette.accent,
            selectforeground=palette.on_accent,
            highlightthickness=2,
            highlightbackground=palette.border,
            highlightcolor=palette.focus,
            borderwidth=0,
            relief="flat",
            font=(MONO_FAMILY, sized("mono", scale)),
            exportselection=False,
        )
        scrollbar = ctk.CTkScrollbar(
            self,
            command=self.listbox.yview,
            button_color=palette.border_strong,
            button_hover_color=palette.accent,
            fg_color=palette.surface,
        )
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(6, 0))

        self.listbox.bind("<Delete>", lambda e: self.remove_selected())
        self.listbox.bind("<BackSpace>", lambda e: self.remove_selected())

        # A CTkScrollbar asks for 200px by default, which would drive this
        # frame's height instead of the Listbox doing it. Ask for nothing and
        # let fill="y" stretch it, so `height` really means "this many rows".
        scrollbar.configure(height=1)

    def add(self, paths) -> int:
        known = {p.lower() for p in self.paths}
        added = 0
        for path in paths:
            text = str(path)
            if text.lower() in known:
                continue
            known.add(text.lower())
            self.paths.append(text)
            self.listbox.insert("end", text)
            added += 1
        return added

    def remove_selected(self) -> None:
        for index in sorted(self.listbox.curselection(), reverse=True):
            self.listbox.delete(index)
            del self.paths[index]

    def clear(self) -> None:
        self.listbox.delete(0, "end")
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

    def write(self, line: str, tag: str | None = None) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag or ())
        self.text.see("end")
        self.text.configure(state="disabled")

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
