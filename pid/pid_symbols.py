"""P&ID symbol library: the catalogue, its SVG files, and port coordinates.

The catalogue below is the single source of truth. Each symbol is SVG body
markup drawn in **mm, Y up, about its anchor (0, 0)**, plus named ports in the
same frame. `write_svgs()` regenerates `symbols/*.svg` (and the contact sheet
`symbols/_sheet.svg`) from it. `pid_drawio` embeds the same SVG in draw.io
image shapes and turns the ports into draw.io connection points, so lines stay
glued to the symbol when it is dragged. `port()` gives a port's sheet
coordinates, for laying lines out in a script.

Every SVG has a viewBox symmetric about the anchor, so the anchor is the
symbol's centre.

House style (user preferences):
  * ball valve: generic bowtie with an opaque white circle on top
  * check valve: two short bars with a diagonal arrow from a filled pivot dot
  * oval-gear meter: box with two touching gears
  * filled symbols (bubbles, boxes, pump casing) are white-filled, so a symbol
    drawn on top of a line hides it

Regenerate the SVGs after editing the catalogue (and then the draw.io library
with `python pid/pid_drawio.py`):

    python pid/pid_symbols.py
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SYMBOL_DIR = os.path.join(HERE, "symbols")
STROKE = 0.3            # mm; the symbol line weight (pid_drawio.LINE["symbol"])
MARGIN = 0.4            # mm of clear space around the geometry in the viewBox

W = 'fill="#fff"'       # opaque white fill
K = 'fill="#000"'       # solid black fill


def _bowtie(h=3.0, w=2.0):
    return '<path d="M%g,%g L%g,%g L%g,%g L%g,%g Z"/>' % (-h, -w, -h, w, h, -w, h, w)


def _arrowhead(tip, d, length=1.4, half=0.55):
    """Filled arrowhead: tip point, unit direction d."""
    bx, by = tip[0] - length * d[0], tip[1] - length * d[1]
    nx, ny = -d[1] * half, d[0] * half
    return '<path %s d="M%g,%g L%g,%g L%g,%g Z"/>' % (K, tip[0], tip[1], bx + nx, by + ny,
                                                      bx - nx, by - ny)


def _check():
    a, b = (-2.5, 2.0), (2.5, -2.0)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    end = (b[0] - 1.2 * d[0], b[1] - 1.2 * d[1])
    return ('<path d="M-2.5,-2 L-2.5,2 M2.5,-2 L2.5,2"/>'
            '<path d="M%g,%g L%g,%g"/>' % (a[0], a[1], end[0], end[1])
            + '<circle %s cx="-2.5" cy="2" r="0.45"/>' % K
            + _arrowhead(b, d))


# name: (svg body, half-extent (x, y) of the geometry, ports, description)
CATALOGUE = {
    "ball_valve": (
        _bowtie() + '<circle %s cx="0" cy="0" r="1.3"/>' % W,
        (3.0, 2.0), {"in": (-3.0, 0.0), "out": (3.0, 0.0)},
        "Ball valve: bowtie with an opaque white circle"),
    "gate_valve": (
        _bowtie(),
        (3.0, 2.0), {"in": (-3.0, 0.0), "out": (3.0, 0.0)},
        "Gate valve (generic two-way valve): bowtie"),
    "globe_valve": (
        _bowtie() + '<circle %s cx="0" cy="0" r="0.8"/>' % K,
        (3.0, 2.0), {"in": (-3.0, 0.0), "out": (3.0, 0.0)},
        "Globe valve: bowtie with a solid dot"),
    "check_valve": (
        _check(),
        (2.5, 2.0), {"in": (-2.5, 0.0), "out": (2.5, 0.0)},
        "Check valve: bars with a hinged arrow; flow in -> out (left to right)"),
    "pump_centrifugal": (
        '<path %s d="M-5,-9 L5,-9 L3,-5 L-3,-5 Z"/>' % W
        + '<circle %s cx="0" cy="0" r="7"/>' % W
        + '<path d="M0,7 L7,7 L7,4.5 L%g,4.5"/>' % math.sqrt(49 - 4.5 ** 2),
        (7.0, 9.0), {"suction": (-7.0, 0.0), "discharge": (7.0, 5.75), "motor": (0.0, -9.0)},
        "Centrifugal pump: casing, tangential top discharge, base; motor = power/signal point"),
    "oval_gear_meter": (
        '<rect %s x="-5" y="-3" width="10" height="6"/>' % W
        + '<circle cx="-1.6" cy="0" r="1.5"/><circle cx="1.6" cy="0" r="1.5"/>',
        (5.0, 3.0), {"in": (-5.0, 0.0), "out": (5.0, 0.0), "top": (0.0, 3.0), "bottom": (0.0, -3.0)},
        "Positive-displacement (oval-gear) flow meter, inline"),
    "instrument_field": (
        '<circle %s cx="0" cy="0" r="5"/>' % W,
        (5.0, 5.0), {"top": (0.0, 5.0), "bottom": (0.0, -5.0), "left": (-5.0, 0.0), "right": (5.0, 0.0)},
        "Instrument bubble, field mounted (ISA 5.1)"),
    "instrument_panel": (
        '<circle %s cx="0" cy="0" r="5"/>' % W + '<path d="M-5,0 L5,0"/>',
        (5.0, 5.0), {"top": (0.0, 5.0), "bottom": (0.0, -5.0), "left": (-5.0, 0.0), "right": (5.0, 0.0)},
        "Instrument bubble, panel / board mounted, accessible (ISA 5.1)"),
    "relay": (
        '<rect %s x="-5" y="-4" width="10" height="8"/>' % W,
        (5.0, 4.0), {"top": (0.0, 4.0), "bottom": (0.0, -4.0), "left": (-5.0, 0.0), "right": (5.0, 0.0)},
        "Relay / interposing device box (XY)"),
    "cap": (
        '<path d="M-2.5,0 L2.5,0"/>',
        (2.5, 0.5), {"in": (0.0, 0.0)},
        "Cap or plug on a line end; rotate so the bar is across the line"),
    "flow_arrow": (
        '<path d="M-1.5,1.5 L1.5,0 L-1.5,-1.5"/>',
        (1.5, 1.5), {"tip": (1.5, 0.0)},
        "Open flow arrow along a line, pointing +x at rot 0"),
}

SYMBOLS = {n: {"half": v[1], "ports": v[2], "desc": v[3]} for n, v in CATALOGUE.items()}


def _size(name):
    hx, hy = SYMBOLS[name]["half"]
    return 2 * (hx + MARGIN), 2 * (hy + MARGIN)


def svg_text(name):
    body = CATALOGUE[name][0]
    w, h = _size(name)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}mm" height="{h:g}mm" '
            'viewBox="{x:g} {y:g} {w:g} {h:g}">\n'
            '<g transform="scale(1,-1)" fill="none" stroke="#000" stroke-width="{s:g}" '
            'stroke-linejoin="round" stroke-linecap="butt">{b}</g>\n</svg>\n'
            ).format(w=w, h=h, x=-w / 2, y=-h / 2, s=STROKE, b=body)


def write_svgs(directory=SYMBOL_DIR):
    """Write one SVG per symbol plus a contact sheet showing ports in red."""
    os.makedirs(directory, exist_ok=True)
    for n in CATALOGUE:
        with open(os.path.join(directory, n + ".svg"), "w", encoding="utf-8") as fh:
            fh.write(svg_text(n))
    cell, cols = 34.0, 4
    rows = -(-len(CATALOGUE) // cols)
    parts = []
    for k, n in enumerate(CATALOGUE):
        cx, cy = (k % cols + 0.5) * cell, (k // cols + 0.42) * cell
        ports = "".join('<circle cx="%g" cy="%g" r="0.45" fill="#d00" stroke="none"/>' % p
                        for p in SYMBOLS[n]["ports"].values())
        parts.append('<g transform="translate(%g,%g) scale(1,-1)" fill="none" stroke="#000" '
                     'stroke-width="%g">%s%s</g>' % (cx, cy, STROKE, CATALOGUE[n][0], ports))
        parts.append('<text x="%g" y="%g" font-family="sans-serif" font-size="2.6" '
                     'text-anchor="middle">%s</text>' % (cx, cy + 0.42 * cell, n))
    W_, H_ = cols * cell, rows * cell
    with open(os.path.join(directory, "_sheet.svg"), "w", encoding="utf-8") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" '
                 'viewBox="0 0 %g %g"><rect width="100%%" height="100%%" fill="#fff"/>\n%s\n</svg>\n'
                 % (W_, H_, W_, H_, "\n".join(parts)))


# ---------------------------------------------------------------------------
# Port coordinates
# ---------------------------------------------------------------------------
def _rot(p, rot):
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return p[0] * c - p[1] * s, p[0] * s + p[1] * c


def port(name, x, y, which, rot=0.0, scale=1.0):
    """Page coordinates of a port of a symbol anchored at (x, y), rotated rot
    degrees counter-clockwise."""
    px, py = _rot(SYMBOLS[name]["ports"][which], rot)
    return (x + px * scale, y + py * scale)


if __name__ == "__main__":
    write_svgs()
    print("wrote %d symbols to %s" % (len(CATALOGUE), SYMBOL_DIR))
