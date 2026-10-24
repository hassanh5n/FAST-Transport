"""
The printable transport card (PDF).

One A4 page carrying a real ID-card-sized (CR80, 85.6 x 54 mm) card: the front
and back sit side by side and share a fold line, so a rider prints at 100%, cuts
the dashed outline, folds it and has a wallet card. Below it, the same details
in full (pickup times included) for anyone reading the PDF on screen.

Drawn straight onto a canvas rather than with platypus, because the card is a
fixed-size object with absolute positions, not flowing text.
"""

import io
import os
from dataclasses import dataclass

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Brand guide colours, plus the app's own navy/sky tokens (frontend/src/theme.js).
NAVY = HexColor("#00254D")
NAVY_MID = HexColor("#0f3a55")
NAVY_LIGHT = HexColor("#1a4a68")
TEAL = HexColor("#03D2C7")
SKY = HexColor("#288dc4")
INK = HexColor("#0f1f2d")
MUTED = HexColor("#4a6178")
FAINT = HexColor("#8faabb")
LINE = HexColor("#e2e8f0")
TINT = HexColor("#f4f7fa")
GREEN = HexColor("#22c55e")
AMBER = HexColor("#f59e0b")

CARD_W, CARD_H = 85.6 * mm, 53.98 * mm   # ISO/IEC 7810 ID-1, a bank-card size
RADIUS = 3.18 * mm


# ── Fonts ────────────────────────────────────────────────────────────────────
# DM Sans is the app's typeface (SIL OFL). If the files are missing the card
# still renders, in Helvetica: a missing asset must never break the download.

_FALLBACK = {"regular": "Helvetica", "medium": "Helvetica", "bold": "Helvetica-Bold", "black": "Helvetica-Bold"}
_FILES = {"regular": "DMSans-Regular", "medium": "DMSans-Medium", "bold": "DMSans-Bold", "black": "DMSans-ExtraBold"}


def _register_fonts():
    fonts = {}
    for weight, name in _FILES.items():
        try:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, os.path.join(ASSETS, "fonts", f"{name}.ttf")))
            fonts[weight] = name
        except Exception:  # noqa: BLE001 - any font problem means "use Helvetica"
            return dict(_FALLBACK)
    return fonts


FONTS = _register_fonts()


def _font(weight, text=""):
    """The DM Sans weight, or Helvetica when the text has a character DM Sans lacks."""
    name = FONTS[weight]
    if name.startswith("DMSans") and text:
        glyphs = pdfmetrics.getFont(name).face.charToGlyph
        if any(ord(ch) not in glyphs for ch in text if not ch.isspace()):
            return _FALLBACK[weight]
    return name


def _fit(text, weight, size, max_width, min_size):
    """(text, font, size) shrunk to fit max_width, then cut with an ellipsis if still too long."""
    font = _font(weight, text)
    while size > min_size and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.25
    if pdfmetrics.stringWidth(text, font, size) > max_width:
        while text and pdfmetrics.stringWidth(text + "…", font, size) > max_width:
            text = text[:-1]
        text = text.rstrip() + "…"
    return text, font, size


def _text(c, x, y, text, weight, size, color, *, align="left", spacing=0, max_width=None, min_size=None):
    text = str(text)
    if max_width:
        text, font, size = _fit(text, weight, size, max_width, min_size or size)
    else:
        font = _font(weight, text)
    width = pdfmetrics.stringWidth(text, font, size) + spacing * max(len(text) - 1, 0)
    if align == "right":
        x -= width
    elif align == "center":
        x -= width / 2
    obj = c.beginText(x, y)
    obj.setFont(font, size)
    obj.setCharSpace(spacing)
    obj.setFillColor(color)
    obj.textOut(text)
    c.drawText(obj)
    return width


# ── Brand mark ───────────────────────────────────────────────────────────────
# Path data from branding/01_Master_Vector/Fleetcentric_icon.svg (500 x 500,
# translate(10.81, 0) scale(1.351351)), drawn as vectors so it stays sharp in
# print and can be recoloured: the navy stroke would vanish on the dark card.

_MARK_TOP = (
    "349,10 344,6 324,7 319,6 314,1 305,0 167,0 151,2 137,6 109,20 90,38 57,97 65,137 109,57 126,41 136,35 "
    "152,29 172,26 307,26 321,27 323,29 323,32 317,51 314,55 173,55 154,60 139,68 127,80 119,98 108,116 90,152 "
    "86,157 84,164 61,205 59,213 63,230 65,233 65,238 69,240 73,236 92,200 104,181 111,165 119,154 129,130 "
    "135,119 140,114 144,102 156,87 169,81 334,81 337,78 339,68 353,26 353,17"
)
_MARK_ACCENT = (
    "289,117 264,117 254,113 247,112 169,112 150,114 144,116 142,115 139,118 123,151 135,149 147,143 169,138 "
    "256,137 258,139 256,155 251,165 243,167 168,166 144,167 141,170 93,260 83,291 72,308 72,326 61,337 62,369 "
    "65,365 67,357 88,322 157,197 160,194 166,192 264,192 272,190 278,177 283,153 291,130 292,123",
    "54,103 5,194 0,212 1,235 7,250 18,262 38,271 68,271 76,265 86,249 86,246 79,246 71,242 64,243 59,246 "
    "47,246 39,244 30,236 26,229 25,217 30,201 43,179 53,158 64,141 63,142 61,138 57,109",
)


def _draw_mark(c, x, y, size, main_color, accent_color):
    """The Fleetcentric symbol in a size x size box whose bottom-left is (x, y)."""
    def polygon(points):
        path = c.beginPath()
        for index, pair in enumerate(points.split()):
            px, py = (float(v) for v in pair.split(","))
            sx = x + (10.81 + px * 1.351351) / 500 * size
            sy = y + size - (py * 1.351351) / 500 * size
            (path.moveTo if index == 0 else path.lineTo)(sx, sy)
        path.close()
        return path

    c.saveState()
    c.setFillColor(main_color)
    c.drawPath(polygon(_MARK_TOP), stroke=0, fill=1)
    c.setFillColor(accent_color)
    for part in _MARK_ACCENT:
        c.drawPath(polygon(part), stroke=0, fill=1)
    c.restoreState()


def _wordmark(c, x, y, size, color, accent=TEAL):
    """'Fleetcentric.ai' with the brand's teal '.ai'. Returns its width."""
    font = _font("black")
    _text(c, x, y, "Fleetcentric", "black", size, color, spacing=-0.02 * size)
    first = pdfmetrics.stringWidth("Fleetcentric", font, size) - 0.02 * size * 11
    _text(c, x + first, y, ".ai", "black", size, accent)
    return first + pdfmetrics.stringWidth(".ai", font, size)


# ── Shapes ───────────────────────────────────────────────────────────────────

def _rounded_path(c, x, y, w, h, r, corners=(True, True, True, True)):
    """Rect path with a choice of rounded corners: (top-left, top-right, bottom-right, bottom-left)."""
    tl, tr, br, bl = corners
    k = 0.5523 * r  # bezier handle for a quarter circle
    p = c.beginPath()
    p.moveTo(x + (r if bl else 0), y)
    if br:
        p.lineTo(x + w - r, y)
        p.curveTo(x + w - r + k, y, x + w, y + r - k, x + w, y + r)
    else:
        p.lineTo(x + w, y)
    if tr:
        p.lineTo(x + w, y + h - r)
        p.curveTo(x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h)
    else:
        p.lineTo(x + w, y + h)
    if tl:
        p.lineTo(x + r, y + h)
        p.curveTo(x + r - k, y + h, x, y + h - r + k, x, y + h - r)
    else:
        p.lineTo(x, y + h)
    if bl:
        p.lineTo(x, y + r)
        p.curveTo(x, y + r - k, x + r - k, y, x + r, y)
    else:
        p.lineTo(x, y)
    p.close()
    return p


def _pill(c, x, y, text, fill, fill_alpha, text_color, size=5.2):
    """A small rounded label whose right edge is at x. Returns its width."""
    font = _font("bold", text)
    spacing = 0.6
    width = pdfmetrics.stringWidth(text, font, size) + spacing * (len(text) - 1) + 3.2 * mm
    height = size + 2.2 * mm
    c.saveState()
    c.setFillColor(fill)
    c.setFillAlpha(fill_alpha)
    c.roundRect(x - width, y, width, height, height / 2, stroke=0, fill=1)
    c.restoreState()
    _text(c, x - width / 2, y + (height - size * 0.72) / 2, text, "bold", size, text_color, align="center", spacing=spacing)
    return width


# ── Card data ────────────────────────────────────────────────────────────────

@dataclass
class CardData:
    name: str
    user_type: str            # "Student" or "Faculty"
    id_value: str             # roll number, or "" for faculty
    department: str
    batch: str
    semester: str
    valid_until: str          # "15 Jan 2027", or "" when the semester has no usable end date
    route: str
    stop: str
    bus: str
    seat: str                 # "2", or "" when not allocated
    morning_eta: str          # "7:35 AM" or ""
    evening_eta: str
    status: str               # "Active", "Payment pending", ...
    status_ok: bool
    card_number: str
    portal_url: str
    generated_at: str


def _clean(value):
    value = (value or "").strip()
    return "" if value.upper() in ("N/A", "NA", "NONE") else value


def _initials(name):
    parts = [p for p in name.replace(".", " ").split() if p[:1].isalpha()]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _subline(data):
    bits = [data.id_value, _clean(data.department), _clean(data.batch)]
    if data.user_type == "Faculty" and not data.id_value:
        bits[0] = "Faculty"
    return "  ·  ".join(b for b in bits if b)


# ── Front ────────────────────────────────────────────────────────────────────

def _front(c, x, y, data):
    W, H = CARD_W, CARD_H
    c.saveState()
    c.clipPath(_rounded_path(c, x, y, W, H, RADIUS, (True, False, False, True)), stroke=0, fill=0)

    c.linearGradient(x, y + H, x + W, y, (NAVY_LIGHT, NAVY_MID, NAVY), positions=(0, 0.45, 1), extend=True)

    # Rings in the top-right corner, echoing the dashboard card.
    c.setStrokeColor(white)
    for radius, alpha in ((30 * mm, 0.05), (22 * mm, 0.06), (14 * mm, 0.07)):
        c.setStrokeAlpha(alpha)
        c.setLineWidth(5)
        c.circle(x + W + 2 * mm, y + H + 4 * mm, radius, stroke=1, fill=0)
    c.setStrokeAlpha(1)

    # Brand.
    _draw_mark(c, x + 4.6 * mm, y + H - 12.4 * mm, 7.8 * mm, white, TEAL)
    _wordmark(c, x + 13.4 * mm, y + H - 7.9 * mm, 8.2, white)
    _text(c, x + 13.5 * mm, y + H - 11.5 * mm, "TRANSPORT CARD", "bold", 4.6, TEAL, spacing=0.9)
    _pill(c, x + W - 4.6 * mm, y + H - 10.6 * mm, data.user_type.upper(), white, 0.12, white)

    # Holder.
    cx, cy, r = x + 11 * mm, y + 27.4 * mm, 6.4 * mm
    c.setFillColor(SKY)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setStrokeColor(TEAL)
    c.setLineWidth(0.9)
    c.circle(cx, cy, r + 0.9 * mm, stroke=1, fill=0)
    initials = _initials(data.name)
    _text(c, cx, cy - 3.1, initials, "black", 9 if len(initials) > 1 else 10, white, align="center")

    left = x + 20.6 * mm
    room = x + W - 4.6 * mm - left
    _text(c, left, y + 28.6 * mm, data.name.upper(), "black", 11.5, white, spacing=0.15, max_width=room, min_size=7.5)
    sub = _subline(data)
    if sub:
        c.saveState()
        c.setFillAlpha(0.7)
        _text(c, left, y + 23.9 * mm, sub, "medium", 6.2, white, max_width=room, min_size=5)
        c.restoreState()

    # Bottom band: route, stop, seat.
    band = 13.6 * mm
    c.setFillColor(Color(0, 0.05, 0.12))
    c.setFillAlpha(0.32)
    c.rect(x, y, W, band, stroke=0, fill=1)
    c.setFillAlpha(1)
    c.setFillColor(TEAL)
    c.rect(x, y + band, W, 0.45 * mm, stroke=0, fill=1)

    def cell(cx, label, value, width, align="left"):
        c.saveState()
        c.setFillAlpha(0.55)
        _text(c, cx, y + 8.6 * mm, label, "bold", 4.4, white, spacing=0.7, align=align)
        c.restoreState()
        _text(c, cx, y + 3.9 * mm, value or "Not set", "bold", 7.4, white, align=align, max_width=width, min_size=5.2)

    cell(x + 4.6 * mm, "ROUTE", data.route, 27 * mm)
    cell(x + 34 * mm, "STOP", data.stop, 30 * mm)
    seat_label_x = x + W - 4.6 * mm
    c.saveState()
    c.setFillAlpha(0.55)
    _text(c, seat_label_x, y + 8.6 * mm, "SEAT", "bold", 4.4, white, spacing=0.7, align="right")
    c.restoreState()
    if data.seat:
        _text(c, seat_label_x, y + 3.5 * mm, f"#{data.seat}", "black", 11, TEAL, align="right")
    else:
        _text(c, seat_label_x, y + 3.9 * mm, "Pending", "bold", 7.4, white, align="right")

    c.restoreState()


# ── Back ─────────────────────────────────────────────────────────────────────

def _back(c, x, y, data):
    W, H = CARD_W, CARD_H
    c.saveState()
    shape = _rounded_path(c, x, y, W, H, RADIUS, (False, True, True, False))
    c.clipPath(shape, stroke=0, fill=0)
    c.setFillColor(white)
    c.rect(x, y, W, H, stroke=0, fill=1)

    # Top band: semester and validity.
    band = 9.4 * mm
    c.linearGradient(x, y + H, x + W, y + H - band, (NAVY_MID, NAVY), extend=True)
    c.setFillColor(white)
    c.rect(x, y, W, H - band, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.rect(x, y + H - band - 0.45 * mm, W, 0.45 * mm, stroke=0, fill=1)
    _text(c, x + 4.6 * mm, y + H - 6 * mm, data.semester.upper(), "black", 7.2, white, spacing=0.5, max_width=38 * mm, min_size=5.5)
    if data.valid_until:
        c.saveState()
        c.setFillAlpha(0.75)
        _text(c, x + W - 4.6 * mm, y + H - 5.9 * mm, f"Valid until {data.valid_until}", "medium", 5.6, white, align="right")
        c.restoreState()

    left = x + 4.6 * mm
    inner = W - 9.2 * mm

    # Row 1, the rider's two times, set large: the thing they check most.
    top = y + H - band - 6.4 * mm
    half = inner / 2
    for j, (label, value) in enumerate((("MORNING PICKUP", data.morning_eta), ("EVENING DROP-OFF", data.evening_eta))):
        cx = left + j * half
        _text(c, cx, top, label, "bold", 4.4, FAINT, spacing=0.6)
        _text(c, cx, top - 6 * mm, value or "Not set", "black", 12, INK, max_width=half - 2 * mm, min_size=7)

    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(left, top - 9.4 * mm, left + inner, top - 9.4 * mm)

    # Row 2: bus, status, card number.
    row = top - 13.6 * mm
    third = inner / 3
    _text(c, left, row, "BUS", "bold", 4.2, FAINT, spacing=0.55)
    _text(c, left, row - 4.4 * mm, data.bus or "Not assigned", "bold", 7.2, INK, max_width=third - 2 * mm, min_size=5)

    sx = left + third
    _text(c, sx, row, "STATUS", "bold", 4.2, FAINT, spacing=0.55)
    c.setFillColor(GREEN if data.status_ok else AMBER)
    c.circle(sx + 0.9 * mm, row - 3.35 * mm, 0.85 * mm, stroke=0, fill=1)
    _text(c, sx + 2.6 * mm, row - 4.4 * mm, data.status, "bold", 7.2, INK, max_width=third - 4.6 * mm, min_size=5)

    nx = left + 2 * third
    _text(c, nx, row, "CARD NO.", "bold", 4.2, FAINT, spacing=0.55)
    _text(c, nx, row - 4.4 * mm, data.card_number, "bold", 6.4, INK, max_width=third, min_size=5)

    # Footer.
    _text(c, left, y + 4.2 * mm, "If found, please return it to the university transport office.",
          "medium", 4.6, MUTED, max_width=inner - 9 * mm, min_size=3.8)
    _draw_mark(c, x + W - 10 * mm, y + 2.4 * mm, 5.4 * mm, NAVY, TEAL)

    c.restoreState()

    # Hairline so the white back still has an edge on white paper.
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.drawPath(shape, stroke=1, fill=0)
    c.restoreState()


# ── Page ─────────────────────────────────────────────────────────────────────

def build_transport_card_pdf(data: CardData) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Transport Card - {data.name} - {data.semester}")
    c.setAuthor("Fleetcentric.ai")
    c.setSubject("Transport card")
    PW, PH = A4
    M = 20 * mm

    # Header.
    _draw_mark(c, M, PH - M - 8.6 * mm, 9.2 * mm, NAVY, TEAL)
    _wordmark(c, M + 11.4 * mm, PH - M - 6.2 * mm, 14, NAVY)
    _text(c, PW - M, PH - M - 3.4 * mm, "TRANSPORT CARD", "bold", 7, FAINT, align="right", spacing=1.2)
    _text(c, PW - M, PH - M - 7.6 * mm, data.semester, "bold", 10, INK, align="right")
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, PH - M - 13 * mm, PW - M, PH - M - 13 * mm)

    # Title.
    first_name = data.name.split()[0] if data.name.split() else data.name
    _text(c, M, PH - M - 27 * mm, f"Your transport card, {first_name}", "bold", 20, INK, max_width=PW - 2 * M, min_size=13)
    _text(c, M, PH - M - 34 * mm,
          "Print this page at 100% (actual size). Cut along the dashed line, fold on the centre line and laminate it.",
          "regular", 9.5, MUTED, max_width=PW - 2 * M, min_size=7.5)

    # Card pair: front | back, sharing the fold line.
    pair_w = 2 * CARD_W
    cx = (PW - pair_w) / 2
    cy = PH - M - 104 * mm
    _text(c, cx, cy + CARD_H + 4 * mm, "FRONT", "bold", 6.5, FAINT, spacing=1)
    _text(c, cx + CARD_W + 3 * mm, cy + CARD_H + 4 * mm, "BACK", "bold", 6.5, FAINT, spacing=1)

    # Soft shadow under the pair, for the on-screen view.
    c.saveState()
    for i, alpha in enumerate((0.05, 0.04, 0.03)):
        grow = (i + 1) * 0.8 * mm
        c.setFillColor(NAVY)
        c.setFillAlpha(alpha)
        c.roundRect(cx - grow, cy - grow - 1.2 * mm, pair_w + 2 * grow, CARD_H + 2 * grow, RADIUS + grow, stroke=0, fill=1)
    c.restoreState()

    _front(c, cx, cy, data)
    _back(c, cx + CARD_W, cy, data)

    # Cut outline and fold line.
    c.saveState()
    c.setStrokeColor(FAINT)
    c.setLineWidth(0.6)
    c.setDash(3, 2.2)
    gap = 2.2 * mm
    c.roundRect(cx - gap, cy - gap, pair_w + 2 * gap, CARD_H + 2 * gap, RADIUS + gap, stroke=1, fill=0)
    c.setDash(1, 1.6)
    c.line(cx + CARD_W, cy - gap - 3 * mm, cx + CARD_W, cy - gap)
    c.line(cx + CARD_W, cy + CARD_H + gap, cx + CARD_W, cy + CARD_H + gap + 3 * mm)
    c.restoreState()
    _text(c, cx + CARD_W, cy - gap - 6.4 * mm, "FOLD", "bold", 5.5, FAINT, align="center", spacing=1)
    _text(c, cx - gap, cy - gap - 6.4 * mm, "CUT ALONG THE DASHED LINE", "bold", 5.5, FAINT, spacing=1)

    # Details panel.
    top = cy - 20 * mm
    _text(c, M, top, "Trip details", "bold", 13, INK)
    rows = [
        ("Route", data.route or "Not set"),
        ("Your stop", data.stop or "Not set"),
        ("Morning pickup", data.morning_eta or "Not set"),
        ("Evening drop-off", data.evening_eta or "Not set"),
        ("Bus", data.bus or "Not assigned yet"),
        ("Seat", f"#{data.seat}" if data.seat else "Not allocated yet"),
        ("Semester", data.semester + (f", valid until {data.valid_until}" if data.valid_until else "")),
        ("Status", data.status),
    ]
    panel_top = top - 5 * mm
    row_h = 9.4 * mm
    half = (len(rows) + 1) // 2
    panel_h = half * row_h + 4 * mm
    col_w = (PW - 2 * M) / 2
    c.setFillColor(TINT)
    c.roundRect(M, panel_top - panel_h, PW - 2 * M, panel_h, 3 * mm, stroke=0, fill=1)
    for i, (label, value) in enumerate(rows):
        column, row = divmod(i, half)
        rx = M + 6 * mm + column * col_w
        ry = panel_top - 2 * mm - row * row_h
        _text(c, rx, ry - 4 * mm, label.upper(), "bold", 6.2, FAINT, spacing=0.8)
        if label == "Status":
            c.setFillColor(GREEN if data.status_ok else AMBER)
            c.circle(rx + 1.1 * mm, ry - 7.35 * mm, 1.1 * mm, stroke=0, fill=1)
            _text(c, rx + 3.4 * mm, ry - 8.2 * mm, value, "bold", 10, INK, max_width=col_w - 14 * mm, min_size=7)
        else:
            _text(c, rx, ry - 8.2 * mm, value, "bold", 10, INK, max_width=col_w - 10 * mm, min_size=7)
        if row < half - 1:
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.line(rx, ry - row_h - 0.2 * mm, rx + col_w - 12 * mm, ry - row_h - 0.2 * mm)

    # Rules.
    ny = panel_top - panel_h - 12 * mm
    _text(c, M, ny, "Good to know", "bold", 13, INK)
    notes = [
        "Show this card to the driver when you board.",
        "It is valid only for the semester shown, on your assigned route and bus.",
        "Lost it, or changed your route or stop? Download a fresh copy from the portal.",
    ]
    for i, note in enumerate(notes):
        ly = ny - 8 * mm - i * 6.6 * mm
        c.setFillColor(TEAL)
        c.circle(M + 1.2 * mm, ly + 1.15 * mm, 0.9 * mm, stroke=0, fill=1)
        _text(c, M + 4.6 * mm, ly, note, "regular", 9.5, MUTED, max_width=PW - 2 * M - 5 * mm, min_size=7.5)

    # Footer.
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, M + 6 * mm, PW - M, M + 6 * mm)
    _text(c, M, M, f"Card No. {data.card_number}  ·  Generated {data.generated_at}", "regular", 7.5, FAINT)
    _text(c, PW - M, M, data.portal_url, "medium", 7.5, SKY, align="right")

    c.showPage()
    c.save()
    return buffer.getvalue()
