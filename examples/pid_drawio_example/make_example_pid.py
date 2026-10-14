"""Worked example for the pid-diagram skill: seed a P&ID, patch it, export it.

    python examples/pid_drawio_example/make_example_pid.py

1. seed()  writes example_pid.drawio with pid_drawio.Diagram: a tank, two
   pumps in parallel off one suction tee, ball and check valves, a manifold,
   an oval-gear meter with FT, a PT, a relay, and a control panel. It has a
   signal crossing a process line and a signal crossing a signal.
2. patch() opens that file with DrawioFile, as the agent would a P&ID the
   user has been hand-editing, and inserts a drain: a tee is put into an
   existing line (the line is replaced by two that meet at the tee), then a
   ball valve and a cap go on the branch, and a tag is relabelled.
   check() must come back empty.
3. export() writes example_pid.png with the draw.io desktop CLI, if it is
   installed.

All coordinates are sheet mm, Y up (ANSI B landscape, 431.8 x 279.4).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pid"))
import pid_drawio                    # noqa: E402
from pid_drawio import DrawioFile, ansi_b_sheet   # noqa: E402

OUT = os.path.join(HERE, "example_pid.drawio")
PUMP = "pump_centrifugal"
TANK = (40.0, 130.0, 80.0, 190.0)
PA, PB = (100.0, 110.0), (100.0, 75.0)
YA, YB = PA[1] + 5.75, PB[1] + 5.75        # discharge nozzle centrelines
X_MAN, X_FE, X_PT = 160.0, 180.0, 200.0
PANEL = (230.0, 180.0, 330.0, 230.0)
XY = (250.0, 95.0)


def seed(path=OUT):
    D = pid_drawio.Diagram(name="EXAMPLE-PID-001")
    ansi_b_sheet(D, ["EXAMPLE TRANSFER SKID", "PIPING & INSTRUMENTATION DIAGRAM"],
                 "EXAMPLE-PID-001", rev="A", drawn="AI PIPING DESIGN")
    sym, edge, j = D.symbol, D.edge, D.junction

    x0, y0, x1, y1 = TANK
    tank = D.box(x0, y0, x1, y1, ["TK-1", "FEED TANK"], open_top=True, weight="process",
                 style={"verticalAlign": "middle"}, cid="TK-1")
    edge((x0 + 2, 175.0), (x1 - 2, 175.0), kind="level", cid="TK-1-level")

    pa = sym(PUMP, *PA, label=["P-1A"], label_pos="top", cid="P-1A")
    pb = sym(PUMP, *PB, label=["P-1B"], label_pos="bottom", cid="P-1B")
    tee = j(60.0, PA[1], cid="TEE-SUCTION")
    edge(tank, tee, (60.0, y0), None, cid="L-1a")
    edge(tee, pa, None, "suction", arrow=True, cid="L-1b")
    edge(tee, pb, None, "suction", via=[(60.0, PB[1])], arrow=True, cid="L-1c")

    man = j(X_MAN, YA, cid="TEE-MANIFOLD")
    for n, (p, yd) in enumerate(((pa, YA), (pb, YB)), 1):
        hv = sym("ball_valve", 130.0, yd, label="HV-%d" % n, label_pos="top", cid="HV-%d" % n)
        cv = sym("check_valve", 142.0, yd, label="CV-%d" % n, label_pos="top", cid="CV-%d" % n)
        edge(p, hv, "discharge", "in", cid="L-%da" % (n + 1))
        edge(hv, cv, "out", "in", cid="L-%db" % (n + 1))
        edge(cv, man, "out", None, via=[] if n == 1 else [(X_MAN, yd)], cid="L-%dc" % (n + 1))

    fe = sym("oval_gear_meter", X_FE, YA, label="FE-1", label_pos="bottom", cid="FE-1")
    ft = sym("instrument_field", X_FE, YA + 15, label=["FT", "1"], cid="FT-1")
    pt = sym("instrument_field", X_PT, YA + 15, label=["PT", "1"], cid="PT-1")
    tpt = j(X_PT, YA, cid="TEE-PT-1")
    edge(man, fe, None, "in", cid="L-4a")
    edge(fe, tpt, "out", None, cid="L-4b")
    edge(tpt, (310.0, YA), arrow=True, cid="L-4c")
    edge(fe, ft, "top", "bottom", kind="tap", cid="TAP-FT-1")
    edge(tpt, pt, None, "bottom", kind="tap", cid="TAP-PT-1")
    D.text(300.0, YA + 4, "TO PROCESS  -  1\"-L-4", 2.0)

    te = sym("instrument_field", 95.0, 165.0, label=["TE", "1"], cid="TE-1")
    edge(te, (x1, 165.0), "left", None, kind="tap", cid="TAP-TE-1")

    cx0, cy0, cx1, cy1 = PANEL
    panel = D.box(cx0, cy0, cx1, cy1, ["CP-1  CONTROL PANEL"], cid="CP-1")
    xy = sym("relay", *XY, label=["XY", "1"], cid="XY-1")

    # Signals. The horizontal TE-1 signal goes first: draw.io breaks the later
    # line at a crossing, and the FT/PT risers are the vertical ones.
    sig = dict(kind="signal")
    edge(te, panel, "right", (cx0, 190.0), via=[(215.0, 165.0), (215.0, 190.0)], cid="SIG-TE-1",
         **sig)
    edge(ft, panel, "top", (cx0, 220.0), via=[(X_FE, 220.0)], cid="SIG-FT-1", **sig)
    edge(pt, panel, "top", (cx0, 205.0), via=[(X_PT, 205.0)], cid="SIG-PT-1", **sig)
    edge(xy, panel, "top", (XY[0], cy0), cid="SIG-XY-1-in", **sig)          # crosses L-4c
    edge(xy, pa, "left", "motor", via=[(PA[0], XY[1])], cid="SIG-XY-1-out", **sig)  # crosses riser

    D.text(80.0, 40.0, ["NOTES",
                        "1. EXAMPLE ONLY. SEEDED BY make_example_pid.py, THEN PATCHED.",
                        "2. DASHED LINES ARE ELECTRICAL SIGNALS.",
                        "3. A BREAK IN A LINE AT A CROSSING MEANS NO CONNECTION."], 1.8,
           align="left", cid="NOTES")
    D.text(200.0, 40.0, ["LINE LIST", "L-1  2\"  TK-1 TO SUCTION TEE TO PUMPS",
                         "L-2/3  1\"  PUMP DISCHARGES", "L-4  1\"  MANIFOLD TO PROCESS"], 1.8,
           align="left", cid="LINE-LIST")
    return D.save(path)


def patch(path=OUT):
    """What an agent does to a hand-edited P&ID: targeted edits by cell ID."""
    F = DrawioFile(path)
    y = YA
    # Insert a drain tee into L-4c: replace the line by two that meet at the tee
    F.remove("L-4c")
    F.add_junction(270.0, y, cid="TEE-DRAIN")
    F.add_edge("TEE-PT-1", "TEE-DRAIN", cid="L-4c")
    F.add_edge("TEE-DRAIN", (310.0, y), arrow=True, cid="L-4d")
    F.add_symbol("ball_valve", 270.0, y - 8, rot=90, cid="HV-3")
    F.add_text(278.0, y - 8, ["HV-3", "DRAIN"], 2.0)      # a rotated symbol's own label rotates too
    F.add_symbol("cap", 270.0, y - 14, cid="CAP-3")
    F.add_edge("TEE-DRAIN", "HV-3", None, "out", cid="L-DRAIN-a")
    F.add_edge("HV-3", "CAP-3", "in", "in", cid="L-DRAIN-b")
    F.set_label("P-1B", ["P-1B", "(SPARE)"])
    problems = F.check()
    if problems:
        raise SystemExit("check() failed:\n  " + "\n  ".join(problems))
    return F.save()


def export(path=OUT):
    exe = next((p for p in (os.environ.get("DRAWIO_EXE", ""),
                            os.path.expandvars(r"%LOCALAPPDATA%\Programs\draw.io\draw.io.exe"),
                            r"C:\Program Files\draw.io\draw.io.exe", "/usr/bin/drawio",
                            "/Applications/draw.io.app/Contents/MacOS/draw.io")
                if p and os.path.exists(p)), None)
    if not exe:
        print("draw.io desktop not found; skipped the PNG export")
        return None
    png = os.path.splitext(path)[0] + ".png"
    subprocess.run([exe, "--export", "--format", "png", "--scale", "2", "--border", "8",
                    "--output", png, path], check=True, capture_output=True, timeout=180)
    return png


if __name__ == "__main__":
    print("seeded ", seed())
    print("patched", patch())
    print("png    ", export())
