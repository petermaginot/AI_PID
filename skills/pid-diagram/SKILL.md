---
name: pid-diagram
description: Build or revise a P&ID (piping and instrumentation diagram) as a draw.io (diagrams.net) file the user can hand-edit, using the reusable symbol library in pid/ (house-style valves, pumps, meters, ISA instrument bubbles, relays), with connectors glued to symbol ports, gaps at line crossings, targeted scripted patches by cell ID, and PDF/SVG/PNG export through the draw.io CLI. Use when the user asks for a P&ID, PFD-style schematic, instrument diagram, a change to an existing .drawio P&ID, or new or changed P&ID symbols. Not for 3D piping models, fabrication drawings or isometrics, which are FreeCAD work covered by the AI_Piping_Design skills.
---

# P&IDs in draw.io with the pid/ library

A P&ID is a schematic that people edit by hand. It lives in a **draw.io
file** (`.drawio`, plain XML) and is edited in **draw.io desktop**
(Apache-2.0, free; install with `winget install JGraph.Draw`, or from
[GitHub releases](https://github.com/jgraph/drawio-desktop/releases)).

The life of a P&ID:

1. **Seed** (§3). A script writes the first version from the symbol catalogue
   in [`pid/`](../../pid/README.md), with `pid_drawio.Diagram`.
2. **Hand-edit.** The user drags symbols and lines, edits tags and notes, and
   adds symbols from the custom library. The `.drawio` is now the master.
3. **Patch** (§4). When the agent changes the P&ID, it edits cells by ID with
   `pid_drawio.DrawioFile`. It never regenerates over the user's work.
4. **Export** (§6) to PDF, SVG and PNG with the draw.io CLI.

The worked example,
[`examples/pid_drawio_example/make_example_pid.py`](../../examples/pid_drawio_example/make_example_pid.py),
runs all four steps on a small skid. Read it before writing a P&ID script.

## 1. Golden rules

1. **Seed once; then the `.drawio` is the master.** A seeding script must
   refuse to overwrite an existing file without `--force`, and say why in
   its docstring: overwriting discards the user's hand edits. Record this in
   the project's CLAUDE.md too.
2. **Every cell's ID is its tag:** `P-101A`, `HV-103`, `PT-102`. Use
   `L-006` (or `L-006a`, `L-006b` for pieces) for lines, `SIG-FT-101` for
   signals and `TEE-MANIFOLD` for junctions. Edits find cells by ID, never by
   position or by order in the file. Both `Diagram` and `DrawioFile` refuse
   a duplicate ID.
3. **Glue every line end to a port.** Use catalogue port names (`suction`,
   `discharge`, `motor`, `in`, `out`, `top`, ...). A box port is an
   `(x, y)` point on its edge. A connector glued with no port lands on the
   shape's perimeter, in the wrong place.
4. **Tees are junction vertices** (`junction()`). They are invisible and
   draggable, and they keep the branch attached. Never end one edge on
   another edge.
5. **Patch with `DrawioFile`, then `check()`.** An empty list means every ID
   is unique, every `source`/`target` exists, and every glued end sits on a
   real catalogue port. Don't save a file that fails the check.
6. **Respect the user's open file.** draw.io desktop doesn't reload a file
   changed on disk, and saving from the editor overwrites a scripted patch.
   Before patching, ask the user to save and close the file. Afterwards, tell
   them to reopen it.
7. **Verify the export, not the XML.** Run the CLI export, look at the PNG,
   and count the crossing gaps in the SVG (§7).

## 2. The library

| File | Role |
|---|---|
| `pid/pid_symbols.py` | Catalogue: SVG geometry (mm, Y up, about an anchor), half-extents, named ports; `port()` gives a port's sheet coordinates |
| `pid/pid_drawio.py` | `Diagram` (write a new file), `DrawioFile` (patch an existing one), `ansi_b_sheet()`, `library()` |
| `pid/symbols/*.svg`, `_sheet.svg` | Generated symbol SVGs, and the contact sheet with the ports in red |
| `pid/symbols/pid_library.xml` | draw.io custom library (File → Open Library). The user drags symbols from it, and they arrive with their connection points |

Coordinates everywhere are **sheet mm with Y up** (ANSI B landscape is
431.8 × 279.4). A symbol's position is its anchor, which is its centre. The
writer converts to draw.io pixels (96 dpi, Y down).

**`Diagram` methods:**
- `symbol(name, x, y, rot, label, label_pos, cid)`. `rot` is counter-clockwise
  degrees, and draw.io rotates the connection points with the shape. The
  label is the tag, e.g. `["PT", "102"]` inside a bubble, so it moves with
  the symbol. **draw.io also rotates the label**, so give a rotated symbol a
  separate `text()` tag instead.
- `junction(x, y, cid)`.
- `box(x0, y0, x1, y1, label, open_top, cid)`. Use it for vessels
  (`open_top=True` uses draw.io's `partialRectangle`) and for panels.
- `edge(src, dst, src_port, dst_port, kind, via, arrow, cid)`. `src` and
  `dst` are cell IDs, or an `(x, y)` point for a free end. `kind` is one of:
  - `process`: 0.6 mm.
  - `tap`: instrument process connection, 0.3 mm.
  - `signal`: dashed, takes the crossing gap.
  - `level`: thin dashed, no jumps.
  - `sheet`: title-block rule.

  `via` waypoints fix the route; draw.io keeps lines orthogonal when shapes
  move. `arrow=True` puts an open arrowhead at the destination.
- `text(x, y, lines, size, align, cid)`. The block is centred on (x, y),
  `size` is the cap height in mm, and `align` sets how lines align within
  the block.
- `save(path)`.

**`ansi_b_sheet(D, title, number, rev, drawn, ...)`** draws the frame and
title block on a locked **Sheet** layer, under the **P&ID** layer. Within the
P&ID layer the z-order is process lines, then shapes, then signals, then
text. The white-filled symbols hide the line ends under them.

**`DrawioFile(path)`:**
- **Reading:** `ids()`, `cell(id)`, and `kind(id)`. `kind()` returns the
  catalogue name, `junction`, `box`, `edge` or `layer`.
- **Editing:** `set_label(id, lines)`, `move(id, x, y)` (glued lines follow),
  and `set_style(id, key=value)` (`None` removes a key).
- **Removing:** `remove(id, cascade=False)` refuses while edges are attached.
- **Adding:** `add_symbol`, `add_junction`, `add_edge` and `add_text`, with
  the same arguments as `Diagram`, plus `before=id` to set the z-order.
- **Finishing:** `check()`, then `save()`. The file is always saved as plain
  XML; compressed pages load too.

**Changing a symbol:** edit `CATALOGUE` in `pid_symbols.py`, then run
`python pid/pid_symbols.py && python pid/pid_drawio.py` and look at
`pid/symbols/_sheet.svg`. The house style (the user's preferences) is listed
in `pid/README.md`; keep it unless the user changes it.

**What `kind()` reports:** symbol cells carry `pidSymbol=<name>` in their
style. `kind()` reads that, and falls back to matching the embedded SVG
against the catalogue. A symbol whose geometry changed after the file was
written, without `pidSymbol`, reports as `box`.

## 3. Seeding a new P&ID

Write a project script (`make_pid_drawio.py`) that lays the sheet out in mm
and builds it with `Diagram`, following `seed()` in the worked example:
- **Tags:** every symbol and line gets its tag as `cid` (§1 rule 2).
- **Lines:**
  - Put a junction at every tee, and break each run into one edge per
    segment between symbols and junctions.
  - Use `via` waypoints for doglegs.
  - Pump suction arrows: `arrow=True` on the edge into the `suction` port.
- **Text:**
  - Lists and notes are left-aligned `text()` blocks with IDs
    (`NOTES`, `LINE-LIST`, ...).
  - Label instruments inside the bubble (`["PT", "101"]`).
- **Signals:** add them after every process line and shape, ordered so the
  crossings break the right line (§5).
- **Overwrites:** the script refuses to overwrite without `--force` (§1
  rule 1).

draw.io lays text out in Helvetica, which runs wider than most CAD fonts.
Leave room in the layout, and check the export for text running into
symbols or lines.

## 4. Changing an existing P&ID

1. Ask the user to save and close the file in draw.io.
2. Load it with `DrawioFile`, and make only the changes asked for. Leave every
   other cell's geometry alone: the positions are the user's work.
3. **To insert something into an existing line,** remove the edge and add two
   edges that meet at a new junction or symbol. Don't leave a symbol sitting
   on a line it isn't connected to. `patch()` in the worked example inserts a
   drain tee this way.
4. Keep the IDs as tags. If a renamed instrument's ID must change, remove
   the cell and add it back with the new ID, along with its edges.
5. `check()` must return `[]`. Save, export (§6), look at the result (§7),
   and tell the user to reopen the file.

**Keep project lists in sync.** If the project keeps instrument or line lists
elsewhere (a BOM, design docs), update them with the P&ID's list cells.

## 5. Line crossings

The rule (the user's preference): a process line never breaks; otherwise the
line running vertically on the page breaks. draw.io draws the gap
(`jumpStyle=gap`, `jumpSize=12` px ≈ 3 mm) on **whichever edge comes later
in z-order**, so:

- **Signal over process:** signal edges come after process edges. A signal
  crossing a pipe breaks, and the pipe stays whole. `DrawioFile.add_edge`
  keeps this order.
- **Signal over signal:** write the horizontal one first, so the vertical
  one comes later and takes the gap. With `DrawioFile`, pass
  `before=<vertical signal id>` when adding a horizontal signal that crosses
  existing verticals.
- **Process over process:** whichever comes later breaks. In the editor,
  To Front and To Back change it.
- **Say what a break means.** Put a note on the sheet: "A BREAK IN A LINE AT
  A CROSSING MEANS NO CONNECTION."

## 6. Export

draw.io desktop's CLI lives at `%LOCALAPPDATA%\Programs\draw.io\draw.io.exe`
for a per-user install, or `C:\Program Files\draw.io\draw.io.exe`. Let
`DRAWIO_EXE` override it.

```
draw.io.exe --export --format pdf --output PID.pdf PID.drawio
draw.io.exe --export --format svg --border 8 --output PID.svg PID.drawio
draw.io.exe --export --format png --scale 3 --border 8 --output PID.png PID.drawio
```

- **PDF** uses the page size.
- **SVG and PNG** crop to the content, so pass `--border` or the frame's
  outer stroke is clipped.
- **Failures:** treat a non-zero exit, or a missing output file, as a
  failure.

## 7. Verification

1. **`check()` returns `[]`** after every build and every patch.
2. **The export runs.** That also proves draw.io can parse the file.
3. **Look at the PNG.** Check for text overlapping symbols or lines, labels
   on the wrong side, and lines that don't meet a symbol.
4. **Count the gaps in the SVG.** A signal path with a jump gap has extra
   `M` moves in its `d`. List those paths and confirm each break is on the
   intended line:

   ```python
   import re
   s = open("PID.svg", encoding="utf-8").read()
   for m in re.finditer(r'<path d="([^"]+)"[^>]*stroke-dasharray', s):
       if m.group(1).count("M") > 1:
           print(m.group(1)[:100])
   ```
5. **Run the tests:** `python -m unittest discover -s tests` covers the
   writer and the patcher (`tests/test_pid_drawio.py`).

## 8. MCP servers for draw.io (checked 2026-10-14)

Neither available server edits a diagram open in draw.io **desktop**, so
patch the file (§4).

- **Official, [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp):**
  creates a diagram from XML, CSV or Mermaid and opens it in the editor. It
  can't read or change a diagram the user has open.
- **Community, [lgazo/drawio-mcp-server](https://github.com/lgazo/drawio-mcp-server):**
  can inspect and edit shapes live, but only in draw.io running in a
  browser (its built-in editor or a browser extension). Desktop support is
  experimental and blocked upstream.

If the user wants live editing, the community server's browser editor is the
route, but it means working in the browser instead of the desktop app.
