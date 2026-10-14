"""Write P&IDs as draw.io (diagrams.net) files from the pid_symbols catalogue.

Pure Python. Coordinates passed in are sheet mm, Y up (the same frame as
pid_symbols); the writer converts to draw.io pixels (96 dpi, Y
down). Symbols become SVG image shapes at true size with their catalogue
ports as draw.io connection points, so connectors stay glued to them when a
symbol is dragged in the editor.

    D = Diagram()
    p = D.symbol("pump_centrifugal", 82, 112, label="P-101A", label_pos="top")
    v = D.symbol("ball_valve", 134, 117.75, label="HV-101", label_pos="top")
    D.edge(p, v, "discharge", "in")
    D.save("pid.drawio")

Z-order is process edges, then shapes, then signal edges, then text. Signal
edges carry jumpStyle=gap, and draw.io draws a jump on the edge that is on
top, so a signal crossing a process line is the one that breaks.

DrawioFile patches an existing file by cell ID (relabel, move, restyle, add,
remove) and check()s that every line is still glued to a real port; use it
on a hand-edited P&ID instead of regenerating it.

library() writes a draw.io custom library (File > Open Library) of every
catalogue symbol, for dragging new symbols in by hand.
"""
import base64
import html
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import pid_symbols as S

PX = 96 / 25.4                  # draw.io px per mm
SHEET = (431.8, 279.4)          # ANSI B landscape, mm
LINE = {"process": 0.6, "symbol": 0.3, "signal": 0.25}     # mm


def _px(mm):
    return round(mm * PX, 2)


def _style(d):
    return "".join("%s=%s;" % (k, v) if v is not None else "%s;" % k for k, v in d.items())


def _image_uri(name):
    return "data:image/svg+xml," + base64.b64encode(S.svg_text(name).encode()).decode()


def _symbol_size(name):
    return S._size(name)            # (w, h) mm, including the viewBox margin


def _port_frac(name, which):
    """Catalogue port -> draw.io constraint fraction (0..1, Y down), unrotated."""
    w, h = _symbol_size(name)
    px, py = S.SYMBOLS[name]["ports"][which]
    return round(0.5 + px / w, 5), round(0.5 - py / h, 5)


def symbol_style(name, rot=0.0, label_pos="center"):
    pts = [[*_port_frac(name, p), 0] for p in S.SYMBOLS[name]["ports"]]
    st = {"shape": "image", "image": _image_uri(name), "imageAspect": "0", "aspect": "fixed",
          "pidSymbol": name,
          "points": json.dumps(pts).replace(" ", ""), "html": "1", "fontSize": "10",
          "rotation": round(-rot, 3) if rot else None}
    st.update(_LABEL[label_pos])
    if rot == 0:
        del st["rotation"]
    return st


_LABEL = {
    "center": {"verticalLabelPosition": "middle", "verticalAlign": "middle",
               "labelPosition": "center", "align": "center"},
    "top": {"verticalLabelPosition": "top", "verticalAlign": "bottom",
            "labelPosition": "center", "align": "center"},
    "bottom": {"verticalLabelPosition": "bottom", "verticalAlign": "top",
               "labelPosition": "center", "align": "center"},
    "left": {"verticalLabelPosition": "middle", "verticalAlign": "middle",
             "labelPosition": "left", "align": "right"},
    "right": {"verticalLabelPosition": "middle", "verticalAlign": "middle",
              "labelPosition": "right", "align": "left"},
}


def _label(text):
    """Lines (list or str with \\n) -> draw.io html label."""
    lines = text if isinstance(text, (list, tuple)) else str(text).split("\n")
    return "<br>".join(html.escape(l) for l in lines)


class Diagram:
    """One draw.io page. Two draw.io layers: "Sheet" (border and title block,
    locked so it can't be dragged by accident) under "P&ID". Within the P&ID
    layer the z-order is process lines, shapes, signal lines, text.

    Every add method takes an optional cid: give symbols and lines their tag
    (HV-101, L-006, ...) so later scripted edits can find them by ID."""

    BUCKETS = ("sheet", "process", "shape", "signal", "text")

    def __init__(self, sheet=SHEET, name="P&ID"):
        self.W, self.H = sheet
        self.name = name
        self.cells = {b: [] for b in self.BUCKETS}
        self.geom = {}              # id -> (x0, y0, w, h) mm, Y up, for vertices
        self.kind = {}              # id -> catalogue name or "box"/"junction"
        self._n = 1

    # -------------------------------------------------------------------
    def _id(self, prefix, cid=None):
        if cid:
            if cid in self.kind or any('id="%s"' % cid in c for b in self.cells.values() for c in b):
                raise ValueError("duplicate cell id %r" % cid)
            return cid
        self._n += 1
        return "%s-%d" % (prefix, self._n)

    def _add(self, bucket, xml):
        parent = "sheet" if bucket == "sheet" else "pid"
        self.cells[bucket].append(xml.replace('parent="?"', 'parent="%s"' % parent))

    def _vertex(self, cid, value, style, x0, y0, w, h, bucket="shape"):
        """x0, y0 = lower-left corner in sheet mm."""
        self.geom[cid] = (x0, y0, w, h)
        self._add(bucket,
                  '<mxCell id="%s" value="%s" style="%s" vertex="1" parent="?">'
                  '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/></mxCell>'
                  % (cid, html.escape(value), html.escape(_style(style)),
                     _px(x0), _px(self.H - y0 - h), _px(w), _px(h)))
        return cid

    def symbol(self, name, x, y, rot=0.0, label="", label_pos="center", cid=None):
        """Catalogue symbol with its anchor at (x, y), rotated rot deg CCW."""
        w, h = _symbol_size(name)
        cid = self._id(name, cid)
        self.kind[cid] = name
        return self._vertex(cid, _label(label) if label else "", symbol_style(name, rot, label_pos),
                            x - w / 2, y - h / 2, w, h)

    def junction(self, x, y, cid=None):
        """Invisible tee / branch point that lines meet at; draggable in the editor."""
        cid = self._id("tee", cid)
        self.kind[cid] = "junction"
        s = 20 / PX                 # draw.io's own waypoint size, 20 px
        st = {"shape": "waypoint", "size": "6", "fillColor": "none", "strokeColor": "none",
              "pointerEvents": "1", "points": "[]", "resizable": "0", "rotatable": "0",
              "perimeter": "centerPerimeter", "snapToPoint": "1"}
        return self._vertex(cid, "", st, x - s / 2, y - s / 2, s, s)

    def box(self, x0, y0, x1, y1, label="", open_top=False, weight="symbol", style=None, cid=None,
            sheet=False):
        cid = self._id("box", cid)
        self.kind[cid] = "box"
        st = {"rounded": "0", "whiteSpace": "wrap", "html": "1", "fillColor": "none",
              "strokeWidth": _px(LINE[weight]), "fontSize": "10", "verticalAlign": "top",
              "align": "center"}
        if open_top:
            st = dict({"shape": "partialRectangle", "top": "0"}, **st)
        st.update(style or {})
        return self._vertex(cid, _label(label) if label else "", st, x0, y0, x1 - x0, y1 - y0,
                            "sheet" if sheet else "shape")

    def text(self, x, y, lines, size=2.0, align="center", bold=False, cid=None, sheet=False):
        """Text block centred on (x, y); size is the cap height in mm. align sets
        how lines align within the block (a left-aligned block is still centred)."""
        lines = [lines] if isinstance(lines, str) else list(lines)
        fs = round(size * PX / 0.7)
        w = max(len(l) for l in lines) * size * 0.78 + 2
        h = len(lines) * fs * 1.2 / PX + 1
        st = {"text": None, "html": "1", "align": align, "verticalAlign": "middle",
              "whiteSpace": "nowrap", "fontSize": str(fs), "spacing": "0",
              "fontStyle": "1" if bold else None}
        if not bold:
            del st["fontStyle"]
        return self._vertex(self._id("txt", cid), _label(lines), st, x - w / 2, y - h / 2, w, h,
                            "sheet" if sheet else "text")

    # -------------------------------------------------------------------
    def _terminal(self, cid, port, end):
        """Style keys gluing one line end to a vertex port."""
        k = "exit" if end == "src" else "entry"
        kind = self.kind[cid]
        if port is None or kind == "junction":
            return {}
        if kind == "box":
            x0, y0, w, h = self.geom[cid]
            fx, fy = (port[0] - x0) / w, 1 - (port[1] - y0) / h
        else:
            fx, fy = _port_frac(kind, port)
        return {k + "X": round(fx, 5), k + "Y": round(fy, 5), k + "Dx": "0", k + "Dy": "0",
                k + "Perimeter": "0"}

    def edge(self, src, dst, src_port=None, dst_port=None, kind="process", via=(),
             arrow=False, label="", style=None, cid=None):
        """Orthogonal connector.

        src/dst: a vertex id, or an (x, y) mm point for a free end.
        src_port/dst_port: a catalogue port name; for a box, an (x, y) point on its edge.
        kind: process | tap (instrument process connection) | signal (dashed, takes
        the jump gap) | level (thin dashed, no jumps) | sheet (title-block rule).
        via: waypoints in mm. arrow: open arrowhead at dst."""
        weight = {"tap": "symbol", "level": "symbol", "sheet": "symbol"}.get(kind, kind)
        st = {"edgeStyle": "orthogonalEdgeStyle", "rounded": "0", "html": "1",
              "endArrow": "open" if arrow else "none", "endSize": "8", "startArrow": "none",
              "strokeWidth": _px(LINE[weight]), "jettySize": "auto", "orthogonalLoop": "1"}
        if kind == "signal":
            st.update({"dashed": "1", "dashPattern": "8 5", "jumpStyle": "gap", "jumpSize": "12"})
        elif kind == "level":
            st.update({"dashed": "1", "dashPattern": "6 6", "edgeStyle": "none"})
        elif kind == "sheet":
            st.update({"edgeStyle": "none"})
        st.update(style or {})
        attrs = ""
        if isinstance(src, str):
            st.update(self._terminal(src, src_port, "src"))
            attrs += ' source="%s"' % src
        if isinstance(dst, str):
            st.update(self._terminal(dst, dst_port, "dst"))
            attrs += ' target="%s"' % dst
        geo = []
        if not isinstance(src, str):
            geo.append('<mxPoint x="%s" y="%s" as="sourcePoint"/>' % (_px(src[0]), _px(self.H - src[1])))
        if not isinstance(dst, str):
            geo.append('<mxPoint x="%s" y="%s" as="targetPoint"/>' % (_px(dst[0]), _px(self.H - dst[1])))
        if via:
            pts = "".join('<mxPoint x="%s" y="%s"/>' % (_px(x), _px(self.H - y)) for x, y in via)
            geo.append('<Array as="points">%s</Array>' % pts)
        cid = self._id("line", cid)
        bucket = {"signal": "signal", "sheet": "sheet"}.get(kind, "process")
        self._add(bucket,
                  '<mxCell id="%s" value="%s" style="%s" edge="1" parent="?"%s>'
                  '<mxGeometry relative="1" as="geometry">%s</mxGeometry></mxCell>'
                  % (cid, html.escape(label), html.escape(_style(st)), attrs, "".join(geo)))
        return cid

    # -------------------------------------------------------------------
    def xml(self):
        sheet = "".join(self.cells["sheet"])
        pid = "".join(c for b in self.BUCKETS[1:] for c in self.cells[b])
        return ('<mxfile host="pid_drawio"><diagram id="pid-page" name="%s">'
                '<mxGraphModel grid="1" gridSize="5" guides="1" tooltips="1" connect="1" arrows="0" '
                'fold="1" page="1" pageScale="1" pageWidth="%d" pageHeight="%d" math="0" shadow="0">'
                '<root><mxCell id="0"/>'
                '<mxCell id="sheet" value="Sheet" style="locked=1;" parent="0"/>%s'
                '<mxCell id="pid" value="P&amp;ID" parent="0"/>%s'
                '</root></mxGraphModel></diagram></mxfile>\n'
                % (html.escape(self.name), round(self.W * PX), round(self.H * PX), sheet, pid))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.xml())
        return path


def ansi_b_sheet(D, title, number, rev="A", drawn="", scale="NTS", sheet_no="1 OF 1", date=""):
    """Border and title block for ANSI B landscape (431.8 x 279.4 mm), on the
    locked Sheet layer. Drawing area: x 22-409.8, y 22-257.4; title block
    x 264-409.8, y 22-69, as on the ASME ANSI B layout."""
    D.box(12, 12, D.W - 12, D.H - 12, weight="process", sheet=True, cid="sheet-frame")
    D.box(22, 22, D.W - 22, D.H - 22, weight="process", sheet=True, cid="sheet-border")
    x0, x1, ym, y1 = 264.0, D.W - 22, 45.0, 69.0
    D.box(x0, 22, x1, y1, weight="process", sheet=True, cid="tb-frame")
    D.edge((x0, ym), (x1, ym), kind="sheet", cid="tb-rule")
    D.text((x0 + x1) / 2, (ym + y1) / 2, title, 3.0, sheet=True, cid="tb-title")
    cells = [  # (x from, x to, y from, y to, caption, value)
        (x0, 340, 33.5, ym, "DWG NO", number), (340, 360, 33.5, ym, "REV", rev),
        (360, x1, 33.5, ym, "DRAWN", drawn),
        (x0, 300, 22, 33.5, "SIZE", "B"), (300, 340, 22, 33.5, "SCALE", scale),
        (340, 380, 22, 33.5, "SHEET", sheet_no), (380, x1, 22, 33.5, "DATE", date)]
    for a, b, c, d, cap, val in cells:
        D.box(a, c, b, d, weight="symbol", sheet=True, cid="tb-" + cap.lower().replace(" ", "-"),
              style={"verticalAlign": "top", "align": "left", "spacingLeft": "4", "fontSize": "8"},
              label=[cap])
        D.text((a + b) / 2, (c + d) / 2 - 1.5, val, 2.2, sheet=True,
               cid="tb-" + cap.lower().replace(" ", "-") + "-value")


# ---------------------------------------------------------------------------
# Patching an existing file
# ---------------------------------------------------------------------------
def _parse_style(s):
    out = {}
    for part in (s or "").split(";"):
        if not part:
            continue
        k, sep, v = part.partition("=")
        out[k] = v if sep else None
    return out


def _decompress(text):
    return urllib.parse.unquote(zlib.decompress(base64.b64decode(text), -15).decode())


class DrawioFile:
    """Load an existing .drawio (first page), patch cells by ID, save it back.

    Coordinates are sheet mm, Y up, as for Diagram; a symbol's position is its
    anchor (centre). New cells are built by the same code as Diagram, so they
    glue to catalogue ports exactly as seeded ones do. Grouped cells (whose
    parent is not a layer) are not supported.

        F = DrawioFile("PID.drawio")
        F.set_label("PI-101", ["PI", "101A"])
        F.move("HV-101", 136, 117.75)
        F.add_symbol("ball_valve", 380, 105, rot=90, cid="HV-104")
        F.add_edge("TEE-DRAIN", "HV-104", None, "out", cid="L-DRAIN-2")
        assert not F.check()
        F.save()
    """

    def __init__(self, path):
        self.path = path
        self.tree = ET.parse(path)
        mxfile = self.tree.getroot()
        self.diagram = mxfile.find("diagram")
        if self.diagram is None:
            raise ValueError("%s has no <diagram>" % path)
        self.model = self.diagram.find("mxGraphModel")
        if self.model is None:                       # compressed page
            self.model = ET.fromstring(_decompress(self.diagram.text.strip()))
            self.diagram.text = None
            self.diagram.append(self.model)
        self.root = self.model.find("root")
        self.H = float(self.model.get("pageHeight", 1056)) / PX
        self.W = float(self.model.get("pageWidth", 1632)) / PX
        ids = [c.get("id") for c in self.root]
        self.layer = "pid" if "pid" in ids else "1"

    @classmethod
    def load(cls, path):
        return cls(path)

    # -------------------------------------------------------------------
    def ids(self):
        return [c.get("id") for c in self.root]

    def cell(self, cid):
        for c in self.root:
            if c.get("id") == cid:
                return c
        raise KeyError("no cell %r" % cid)

    def kind(self, cid):
        """Catalogue symbol name, 'junction', 'box', 'edge' or 'layer'."""
        c = self.cell(cid)
        if c.get("edge") == "1":
            return "edge"
        if c.get("vertex") != "1":
            return "layer"
        st = _parse_style(c.get("style"))
        if st.get("pidSymbol") in S.CATALOGUE:
            return st["pidSymbol"]
        if st.get("shape") == "waypoint":
            return "junction"
        img = st.get("image")
        for name in S.CATALOGUE:
            if img and img == _image_uri(name):
                return name
        return "box"

    def _geom_mm(self, cid):
        g = self.cell(cid).find("mxGeometry")
        x, y = float(g.get("x", 0)) / PX, float(g.get("y", 0)) / PX
        w, h = float(g.get("width", 0)) / PX, float(g.get("height", 0)) / PX
        return x, self.H - y - h, w, h

    # -------------------------------------------------------------------
    def set_label(self, cid, lines):
        self.cell(cid).set("value", _label(lines) if lines else "")

    def set_style(self, cid, **keys):
        """Set style keys; a value of None removes the key."""
        c = self.cell(cid)
        st = _parse_style(c.get("style"))
        for k, v in keys.items():
            if v is None:
                st.pop(k, None)
            else:
                st[k] = str(v)
        c.set("style", _style(st))

    def move(self, cid, x, y):
        """Put a vertex's centre at sheet (x, y) mm. Edges glued to it follow."""
        c = self.cell(cid)
        if c.get("parent") not in (self.layer, "sheet", "1", "pid"):
            raise ValueError("%s is inside a group; ungroup it in draw.io first" % cid)
        g = c.find("mxGeometry")
        w, h = float(g.get("width")), float(g.get("height"))
        g.set("x", str(_px(x) - w / 2))
        g.set("y", str(_px(self.H - y) - h / 2))

    def remove(self, cid, cascade=False):
        """Remove a cell. Edges attached to it block the removal unless cascade."""
        attached = [c for c in self.root if cid in (c.get("source"), c.get("target"))]
        if attached and not cascade:
            raise ValueError("%s has edges %s; pass cascade=True to remove them too"
                             % (cid, [c.get("id") for c in attached]))
        for c in attached + [self.cell(cid)]:
            self.root.remove(c)

    # -------------------------------------------------------------------
    def _scratch(self, refs):
        """A Diagram that knows the referenced cells, to build new cell XML."""
        D = Diagram(sheet=(self.W, self.H))
        # auto-numbered IDs (txt-12, tee-40, ...) must not reuse the file's
        D._n = max([int(m.group(1)) for m in (re.search(r"-(\d+)$", i or "") for i in self.ids())
                    if m] + [len(self.ids())])
        for r in refs:
            if isinstance(r, str):
                k = self.kind(r)
                D.kind[r] = k
                if k == "box":
                    D.geom[r] = self._geom_mm(r)
        return D

    def _insert(self, D, bucket, before):
        xml = D.cells[bucket][-1].replace('parent="pid"', 'parent="%s"' % self.layer)
        el = ET.fromstring(xml)
        if el.get("id") in self.ids():
            raise ValueError("duplicate cell id %r" % el.get("id"))
        kids = list(self.root)
        layer = [c for c in kids if c.get("parent") == self.layer]
        if before:
            ref = self.cell(before)
        elif bucket == "process":       # under every shape
            ref = next((c for c in layer if c.get("vertex") == "1"), None)
        else:                           # shapes and signals: under the text
            ref = next((c for c in layer if (c.get("style") or "").startswith("text;")), None)
        if ref is None:
            self.root.append(el)
        else:
            self.root.insert(kids.index(ref), el)
        return el.get("id")

    def add_symbol(self, name, x, y, rot=0.0, label="", label_pos="center", cid=None, before=None):
        D = self._scratch([])
        D.symbol(name, x, y, rot, label, label_pos, cid)
        return self._insert(D, "shape", before)

    def add_junction(self, x, y, cid=None, before=None):
        D = self._scratch([])
        D.junction(x, y, cid)
        return self._insert(D, "shape", before)

    def add_text(self, x, y, lines, size=2.0, align="center", cid=None):
        D = self._scratch([])
        D.text(x, y, lines, size, align, cid=cid)
        return self._insert(D, "text", None)

    def add_edge(self, src, dst, src_port=None, dst_port=None, kind="process", via=(),
                 arrow=False, label="", style=None, cid=None, before=None):
        """As Diagram.edge. Process lines go under the shapes; signals go above them,
        under the text. To make a signal take a crossing gap, it must be later than
        the line it crosses: pass before= to place it earlier."""
        D = self._scratch([src, dst])
        D.edge(src, dst, src_port, dst_port, kind, via, arrow, label, style, cid)
        return self._insert(D, "signal" if kind == "signal" else "process", before)

    # -------------------------------------------------------------------
    def check(self):
        """List of problems: duplicate IDs, dangling edges, ends off a port."""
        out = []
        ids = self.ids()
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            out.append("duplicate ids: %s" % dup)
        idset = set(ids)
        for c in self.root:
            if c.get("edge") != "1":
                continue
            st = _parse_style(c.get("style"))
            for end, k in (("source", "exit"), ("target", "entry")):
                ref = c.get(end)
                if ref is None:
                    continue
                if ref not in idset:
                    out.append("%s: %s %r does not exist" % (c.get("id"), end, ref))
                    continue
                kind = self.kind(ref)
                if kind in S.CATALOGUE and k + "X" in st:
                    fx, fy = float(st[k + "X"]), float(st[k + "Y"])
                    ports = [_port_frac(kind, p) for p in S.SYMBOLS[kind]["ports"]]
                    if not any(abs(fx - a) < 1e-3 and abs(fy - b) < 1e-3 for a, b in ports):
                        out.append("%s: %s end at (%g, %g) is not a port of %s (%s)"
                                   % (c.get("id"), end, fx, fy, ref, kind))
        return out

    def save(self, path=None):
        """Write plain (uncompressed) XML; draw.io reads it either way."""
        path = path or self.path
        self.tree.write(path, encoding="utf-8", xml_declaration=False)
        return path


# ---------------------------------------------------------------------------
# Custom library
# ---------------------------------------------------------------------------
def _compress(xml):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = c.compress(urllib.parse.quote(xml, safe="~()*!.'").encode()) + c.flush()
    return base64.b64encode(raw).decode()


def library(path=os.path.join(S.SYMBOL_DIR, "pid_library.xml")):
    """draw.io custom library of every catalogue symbol, with connection points."""
    entries = []
    for name in S.CATALOGUE:
        w, h = _symbol_size(name)
        st = symbol_style(name)
        cell = ('<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                '<mxCell id="2" value="" style="%s" vertex="1" parent="1">'
                '<mxGeometry width="%s" height="%s" as="geometry"/></mxCell></root></mxGraphModel>'
                % (html.escape(_style(st)), _px(w), _px(h)))
        entries.append({"xml": _compress(cell), "w": _px(w), "h": _px(h),
                        "aspect": "fixed", "title": name.replace("_", " ")})
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("<mxlibrary>%s</mxlibrary>\n" % json.dumps(entries))
    return path


if __name__ == "__main__":
    print(library())
