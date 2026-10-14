"""pid/ draw.io writer and patcher. Pure stdlib; draw.io need not be installed.

    python -m unittest discover -s tests
"""
import base64
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pid"))
import pid_drawio as P      # noqa: E402
import pid_symbols as S     # noqa: E402


def small():
    D = P.Diagram()
    P.ansi_b_sheet(D, ["T"], "X-1")
    p = D.symbol("pump_centrifugal", 100, 100, label="P-1", cid="P-1")
    v = D.symbol("ball_valve", 130, 105.75, label="HV-1", cid="HV-1")
    t = D.junction(150, 105.75, cid="TEE-1")
    b = D.box(200, 150, 260, 190, "PANEL", cid="CP-1")
    i = D.symbol("instrument_field", 150, 120, label=["PI", "1"], cid="PI-1")
    D.edge(p, v, "discharge", "in", cid="L-1")
    D.edge(v, t, "out", None, cid="L-2")
    D.edge(t, (190, 105.75), arrow=True, cid="L-3")
    D.edge(t, i, None, "bottom", kind="tap", cid="TAP-1")
    D.edge(i, b, "top", (200, 170), kind="signal", via=[(150, 170)], cid="SIG-1")
    return D


class Writer(unittest.TestCase):

    def test_ids_unique_and_edges_resolve(self):
        root = ET.fromstring(small().xml())
        cells = root.iter("mxCell")
        ids = [c.get("id") for c in root.iter("mxCell")]
        self.assertEqual(len(ids), len(set(ids)))
        for c in cells:
            for end in ("source", "target"):
                if c.get(end):
                    self.assertIn(c.get(end), ids)

    def test_glued_ends_are_catalogue_ports(self):
        root = ET.fromstring(small().xml())
        style = {c.get("id"): P._parse_style(c.get("style")) for c in root.iter("mxCell")}
        st = style["L-1"]
        self.assertEqual((float(st["exitX"]), float(st["exitY"])),
                         P._port_frac("pump_centrifugal", "discharge"))
        self.assertEqual((float(st["entryX"]), float(st["entryY"])),
                         P._port_frac("ball_valve", "in"))

    def test_z_order_and_layers(self):
        root = ET.fromstring(small().xml())
        order = [c.get("id") for c in root.iter("mxCell")]
        self.assertLess(order.index("sheet"), order.index("pid"))
        self.assertLess(order.index("L-1"), order.index("P-1"))     # process under shapes
        self.assertGreater(order.index("SIG-1"), order.index("CP-1"))  # signals above
        layer = {c.get("id"): c.get("parent") for c in root.iter("mxCell")}
        self.assertEqual(layer["tb-frame"], "sheet")
        self.assertEqual(layer["P-1"], "pid")

    def test_duplicate_id_raises(self):
        D = small()
        with self.assertRaises(ValueError):
            D.symbol("ball_valve", 0, 0, cid="HV-1")

    def test_library_decodes(self):
        with tempfile.TemporaryDirectory() as d:
            with open(P.library(os.path.join(d, "lib.xml")), encoding="utf-8") as fh:
                text = fh.read()
        lib = json.loads(re.search(r"<mxlibrary>(.*)</mxlibrary>", text, re.S).group(1))
        self.assertEqual(len(lib), len(S.CATALOGUE))
        for e in lib:
            xml = urllib.parse.unquote(zlib.decompress(base64.b64decode(e["xml"]), -15).decode())
            self.assertTrue(xml.startswith("<mxGraphModel>"))
        pump = next(e for e in lib if e["title"] == "pump centrifugal")
        self.assertAlmostEqual(pump["w"] / P.PX, 14.8, places=1)
        self.assertAlmostEqual(pump["h"] / P.PX, 18.8, places=1)


class Patcher(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = small().save(os.path.join(self.tmp.name, "t.drawio"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_and_check(self):
        F = P.DrawioFile(self.path)
        self.assertEqual(F.check(), [])
        self.assertEqual(F.kind("P-1"), "pump_centrifugal")
        self.assertEqual(F.kind("TEE-1"), "junction")
        self.assertEqual(F.kind("CP-1"), "box")
        F.set_label("HV-1", ["HV-1A"])
        F.move("HV-1", 132, 105.75)
        F.add_symbol("check_valve", 170, 105.75, cid="CV-1")
        F.add_edge("CV-1", "CP-1", "out", (200, 160), kind="signal", cid="SIG-2")
        F.add_text(170, 95, "NEW")
        F.save()
        G = P.DrawioFile(self.path)
        self.assertEqual(G.check(), [])
        self.assertEqual(G.cell("HV-1").get("value"), "HV-1A")
        g = G.cell("HV-1").find("mxGeometry")
        cx = (float(g.get("x")) + float(g.get("width")) / 2) / P.PX
        self.assertAlmostEqual(cx, 132, places=2)
        ids = G.ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLess(ids.index("CV-1"), ids.index("SIG-2"))

    def test_check_flags_bad_port_and_dangling_edge(self):
        F = P.DrawioFile(self.path)
        F.set_style("L-1", exitX="0.3")
        F.cell("L-2").set("target", "NOPE")
        problems = F.check()
        self.assertTrue(any("L-1" in p and "not a port" in p for p in problems))
        self.assertTrue(any("L-2" in p and "does not exist" in p for p in problems))

    def test_remove_guards_attached_edges(self):
        F = P.DrawioFile(self.path)
        with self.assertRaises(ValueError):
            F.remove("HV-1")
        F.remove("HV-1", cascade=True)
        self.assertNotIn("L-1", F.ids())
        self.assertEqual(F.check(), [])

    def test_reads_compressed_page(self):
        with open(self.path, encoding="utf-8") as fh:
            text = fh.read()
        model = re.search(r"<mxGraphModel.*</mxGraphModel>", text, re.S).group(0)
        packed = P._compress(model)
        text = re.sub(r"<mxGraphModel.*</mxGraphModel>", lambda m: packed, text, flags=re.S)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)
        F = P.DrawioFile(self.path)
        self.assertIn("P-1", F.ids())
        self.assertEqual(F.check(), [])


if __name__ == "__main__":
    unittest.main()
