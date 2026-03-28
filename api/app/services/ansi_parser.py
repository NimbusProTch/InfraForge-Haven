"""ANSI escape-code → HTML converter for build log rendering.

Converts terminal color/style codes to HTML ``<span>`` elements so that
build logs can be rendered with colors in the browser.

Supported SGR codes
-------------------
- 0  reset
- 1  bold
- 3  italic
- 4  underline
- 22 normal intensity (bold off)
- 23 italic off
- 24 underline off
- 30-37  foreground colors (standard)
- 39     default foreground
- 40-47  background colors (standard)
- 49     default background
- 90-97  bright foreground colors
- 100-107 bright background colors

Usage::

    from app.services.ansi_parser import ansi_to_html

    html = ansi_to_html("\\033[32mHello\\033[0m world")
    # '<span class="fg-green">Hello</span> world'
"""

from __future__ import annotations

import re
from html import escape

# ---------------------------------------------------------------------------
# Color / style tables
# ---------------------------------------------------------------------------

_FG_COLORS: dict[int, str] = {
    30: "fg-black",
    31: "fg-red",
    32: "fg-green",
    33: "fg-yellow",
    34: "fg-blue",
    35: "fg-magenta",
    36: "fg-cyan",
    37: "fg-white",
    # Bright variants
    90: "fg-bright-black",
    91: "fg-bright-red",
    92: "fg-bright-green",
    93: "fg-bright-yellow",
    94: "fg-bright-blue",
    95: "fg-bright-magenta",
    96: "fg-bright-cyan",
    97: "fg-bright-white",
}

_BG_COLORS: dict[int, str] = {
    40: "bg-black",
    41: "bg-red",
    42: "bg-green",
    43: "bg-yellow",
    44: "bg-blue",
    45: "bg-magenta",
    46: "bg-cyan",
    47: "bg-white",
    # Bright variants
    100: "bg-bright-black",
    101: "bg-bright-red",
    102: "bg-bright-green",
    103: "bg-bright-yellow",
    104: "bg-bright-blue",
    105: "bg-bright-magenta",
    106: "bg-bright-cyan",
    107: "bg-bright-white",
}

# Regex: matches ESC [ ... m  (SGR sequence) or ESC [ ... other-letter (non-SGR, discard)
_ANSI_RE = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")

# Regex: matches carriage-return sequences used for progress bars (\r without \n)
_CR_RE = re.compile(r"\r(?!\n)")


# ---------------------------------------------------------------------------
# State tracker
# ---------------------------------------------------------------------------


class _State:
    """Tracks current SGR state for open spans."""

    __slots__ = ("bold", "italic", "underline", "fg", "bg")

    def __init__(self) -> None:
        self.bold = False
        self.italic = False
        self.underline = False
        self.fg: str | None = None
        self.bg: str | None = None

    def reset(self) -> None:
        self.bold = False
        self.italic = False
        self.underline = False
        self.fg = None
        self.bg = None

    def has_style(self) -> bool:
        return bool(self.bold or self.italic or self.underline or self.fg or self.bg)

    def css_classes(self) -> list[str]:
        classes: list[str] = []
        if self.bold:
            classes.append("bold")
        if self.italic:
            classes.append("italic")
        if self.underline:
            classes.append("underline")
        if self.fg:
            classes.append(self.fg)
        if self.bg:
            classes.append(self.bg)
        return classes

    def apply_codes(self, codes: list[int]) -> None:
        """Apply a list of SGR numeric codes to the current state."""
        i = 0
        while i < len(codes):
            code = codes[i]
            if code == 0:
                self.reset()
            elif code == 1:
                self.bold = True
            elif code == 22:
                self.bold = False
            elif code == 3:
                self.italic = True
            elif code == 23:
                self.italic = False
            elif code == 4:
                self.underline = True
            elif code == 24:
                self.underline = False
            elif code == 39:
                self.fg = None
            elif code == 49:
                self.bg = None
            elif code in _FG_COLORS:
                self.fg = _FG_COLORS[code]
            elif code in _BG_COLORS:
                self.bg = _BG_COLORS[code]
            i += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ansi_to_html(text: str, *, newline_to_br: bool = False) -> str:
    """Convert ANSI escape sequences in *text* to HTML ``<span>`` elements.

    Parameters
    ----------
    text:
        Raw log text containing ANSI escape codes.
    newline_to_br:
        If ``True``, ``\\n`` characters are converted to ``<br>`` tags.
        Useful when the output will be displayed inline (not in ``<pre>``).

    Returns
    -------
    str
        HTML-safe string with color/style spans.
    """
    # Remove bare \r (progress-bar overwrites) — keep last line segment
    text = _CR_RE.sub("", text)

    state = _State()
    parts: list[str] = []
    last_end = 0
    open_span = False

    for match in _ANSI_RE.finditer(text):
        start, end = match.span()
        command_char = match.group(2)

        # Emit the text before this escape sequence (HTML-escaped)
        raw_segment = text[last_end:start]
        if raw_segment:
            parts.append(escape(raw_segment))

        last_end = end

        # Only process SGR ('m') — discard cursor movement etc.
        if command_char != "m":
            continue

        # Close any open span before changing state
        if open_span:
            parts.append("</span>")
            open_span = False

        # Parse codes (empty param string → treat as 0 = reset)
        param_str = match.group(1)
        if param_str == "":
            codes = [0]
        else:
            try:
                codes = [int(c) for c in param_str.split(";") if c != ""]
            except ValueError:
                codes = [0]

        state.apply_codes(codes)

        # Open new span if there is active styling
        if state.has_style():
            classes = " ".join(state.css_classes())
            parts.append(f'<span class="{classes}">')
            open_span = True

    # Emit any remaining text after the last escape sequence
    tail = text[last_end:]
    if tail:
        parts.append(escape(tail))

    # Close any still-open span
    if open_span:
        parts.append("</span>")

    result = "".join(parts)
    if newline_to_br:
        result = result.replace("\n", "<br>")
    return result


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*, returning plain text."""
    return _ANSI_RE.sub("", text)
