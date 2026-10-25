"""Generate the system block diagram for the report.

Draws the transmit and receive chains of the monitoring system with the
group's own work highlighted, mirroring the reference architecture in
Lecture 01 and the hybrid encoder block diagram in Lecture 02.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("docs/figures")
OUT.mkdir(parents=True, exist_ok=True)

WIDTH, HEIGHT = 1640, 1000
BG = (255, 255, 255)
INK = (24, 32, 43)
MUTED = (110, 122, 138)
LINE = (90, 104, 120)
OURS_FILL = (226, 240, 255)
OURS_EDGE = (40, 110, 200)
BASE_FILL = (243, 244, 246)
BASE_EDGE = (150, 158, 170)
FEEDBACK = (196, 70, 70)


def load_font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = load_font(17)
FONT_BOLD = load_font(17, bold=True)
FONT_SMALL = load_font(14)
FONT_TITLE = load_font(21, bold=True)
FONT_BAND = load_font(16, bold=True)


def box(draw, x, y, w, h, title, subtitle=None, ours=False, accent=None):
    fill = OURS_FILL if ours else BASE_FILL
    edge = OURS_EDGE if ours else BASE_EDGE
    radius = 9

    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=edge, width=2)
    if accent is not None:
        draw.rectangle([x, y, x + 6, y + h], fill=accent)

    cx = x + w / 2
    if subtitle:
        tb = draw.textbbox((0, 0), title, font=FONT_BOLD)
        draw.text((cx - (tb[2] - tb[0]) / 2, y + h / 2 - 24), title, font=FONT_BOLD, fill=INK)
        lines = subtitle.split("\n")
        offset = y + h / 2 + 2
        for line in lines:
            tb = draw.textbbox((0, 0), line, font=FONT_SMALL)
            draw.text((cx - (tb[2] - tb[0]) / 2, offset), line, font=FONT_SMALL, fill=MUTED)
            offset += 17
    else:
        tb = draw.textbbox((0, 0), title, font=FONT)
        draw.text((cx - (tb[2] - tb[0]) / 2, y + h / 2 - 10), title, font=FONT, fill=INK)


def arrow(draw, x1, y1, x2, y2, colour=LINE, width=2, head=9):
    draw.line([(x1, y1), (x2, y2)], fill=colour, width=width)
    if x2 > x1:
        draw.polygon([(x2, y2), (x2 - head, y2 - head // 2), (x2 - head, y2 + head // 2)], fill=colour)
    elif x2 < x1:
        draw.polygon([(x2, y2), (x2 + head, y2 - head // 2), (x2 + head, y2 + head // 2)], fill=colour)
    else:
        draw.polygon([(x2, y2), (x2 - head // 2, y2 + head), (x2 + head // 2, y2 + head)], fill=colour)


def band(draw, x, y, w, h, text, colour):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=7, fill=colour)
    tb = draw.textbbox((0, 0), text, font=FONT_BAND)
    draw.text((x + 14, y + (h - (tb[3] - tb[1])) / 2 - 3), text, font=FONT_BAND, fill=(255, 255, 255))


def build() -> Path:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    tb = draw.textbbox((0, 0), "RVM — Remote Video Monitoring System", font=FONT_TITLE)
    draw.text(((WIDTH - (tb[2] - tb[0])) / 2, 22), "RVM — Remote Video Monitoring System", font=FONT_TITLE, fill=INK)
    tb = draw.textbbox((0, 0), "Blue blocks are the group's own implementation", font=FONT_SMALL)
    draw.text(((WIDTH - (tb[2] - tb[0])) / 2, 54), "Blue blocks are the group's own implementation", font=FONT_SMALL, fill=MUTED)

    # ---- transmit chain -------------------------------------------------
    band(draw, 40, 96, 1560, 34, "TRANSMIT  —  video server", (58, 96, 178))

    top = 168
    h = 84
    w = 196

    draw.text((52, 142), "Capture", font=FONT_BOLD, fill=MUTED)
    box(draw, 40, top, w, h, "Camera /", "synthetic source")
    box(draw, 256, top, w, h, "Colour transform", "RGB → YCbCr, 4:2:0")
    box(draw, 472, top, w, h, "Motion search", "+ compensation")
    box(draw, 688, top, w, h, "DCT", "8×8 orthonormal")
    box(draw, 904, top, w, h, "Quantiser", "QP-scaled matrix")
    box(draw, 1120, top, w, h, "Entropy coder", "zig-zag + Exp-Golomb")
    box(draw, 1336, top, w, h, "Packetiser", "RTP header, marker bit")

    for x in (40, 256, 472, 688, 904, 1120):
        arrow(draw, x + w, top + h / 2, x + w + 20, top + h / 2)

    # ---- analysis side --------------------------------------------------
    box(draw, 40, top + 132, w, 74, "Motion detector", "background subtraction", ours=True)
    box(draw, 256, top + 132, w, 74, "Face detector", "Haar cascade", ours=True)
    box(draw, 472, top + 132, w, 74, "Recorder", "time-stamped JPEG clip", ours=True)
    draw.line([(138, top + h), (138, top + 132)], fill=LINE, width=2)
    draw.line([(138, top + 132), (266, top + 132)], fill=LINE, width=2)
    draw.line([(354, top + 132), (490, top + 132)], fill=LINE, width=2)
    draw.line([(354, top + 132), (354, top + h)], fill=LINE, width=2)

    # ---- rate control ----------------------------------------------------
    rc_y = top + 250
    box(draw, 800, rc_y, 300, 78, "Virtual buffer rate control", "QP = (d / r) × 31", ours=True)
    # QP flows up from the controller into the quantiser.
    arrow(draw, 950, rc_y, 950, top + h, colour=FEEDBACK)
    draw.text((962, rc_y - 2), "QP", font=FONT_SMALL, fill=FEEDBACK)

    # ---- network ---------------------------------------------------------
    band(draw, 40, 560, 1560, 34, "NETWORK  —  packet switched best-effort IP", (110, 116, 130))
    draw.rounded_rectangle([40, 616, 1600, 690], radius=8, fill=(248, 249, 251), outline=BASE_EDGE, width=2)
    draw.text((560, 641), "WebSocket transport  ·  optional loss / reordering injection", font=FONT, fill=INK)

    arrow(draw, 1434, top + h, 1434, 616)
    arrow(draw, 206, 690, 206, 726)

    # ---- receive chain ---------------------------------------------------
    band(draw, 40, 726, 1560, 34, "RECEIVE  —  remote station (web browser)", (22, 130, 110))
    top2 = 786
    box(draw, 40, top2, w, h, "Jitter buffer", "reorder, adaptive delay", ours=True)
    box(draw, 256, top2, w, h, "Depacketiser", "marker-bit reassembly", ours=True)
    box(draw, 472, top2, w, h, "Inverse codec", "Exp-Golomb → dequant → IDCT")
    box(draw, 688, top2, w, h, "Motion comp.", "from reference frame")
    box(draw, 904, top2, w, h, "Chroma merge", "4:2:0 → RGB")
    box(draw, 1120, top2, w, h, "Display", "live picture + dashboard")
    box(draw, 1336, top2, w, h, "RTCP feedback", "loss, jitter, bitrate", ours=True)

    for x in (40, 256, 472, 688, 904, 1120):
        arrow(draw, x + w, top2 + h / 2, x + w + 20, top2 + h / 2)

    # Delivery feedback returns from the receiver to the rate controller, routed
    # clear of the receive boxes so it never crosses their text.
    draw.line([(1336 + w, top2 + h / 2), (1584, top2 + h / 2)], fill=FEEDBACK, width=2)
    draw.line([(1584, top2 + h / 2), (1584, rc_y + 39)], fill=FEEDBACK, width=2)
    arrow(draw, 1584, rc_y + 39, 1104, rc_y + 39, colour=FEEDBACK)
    tb = draw.textbbox((0, 0), "delivery feedback closes the rate-control loop", font=FONT_SMALL)
    draw.text((1140, rc_y + 92), "delivery feedback closes the rate-control loop", font=FONT_SMALL, fill=FEEDBACK)

    # Reference-frame feedback path on the receive side.
    draw.line([(728, top2 + h), (728, top2 + h + 28)], fill=MUTED, width=2)
    draw.line([(728, top2 + h + 28), (364, top2 + h + 28)], fill=MUTED, width=2)
    draw.line([(364, top2 + h + 28), (364, top2 + h + 14)], fill=MUTED, width=2)
    tb = draw.textbbox((0, 0), "reference frame for the next predicted picture", font=FONT_SMALL)
    draw.text((404, top2 + h + 20), "reference frame for the next predicted picture", font=FONT_SMALL, fill=MUTED)

    path = OUT / "system_block_diagram.png"
    image.save(path, dpi=(200, 200))
    return path


if __name__ == "__main__":
    print(build())