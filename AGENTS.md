# Instructions for an AI agent working in this repo

The instructions live in one skill under [`skills/`](skills/). If your agent
loads skills, it triggers on its own. If it does not, open it and follow it
before you draw anything:

| Task | Skill |
|---|---|
| Draw or revise a P&ID as a hand-editable draw.io file, with the reusable symbol library in [`pid/`](pid/README.md) | [`skills/pid-diagram/SKILL.md`](skills/pid-diagram/SKILL.md) |

The short version, which is no substitute for reading the skill:

- **The `.drawio` belongs to the user once they have edited it.** Never
  regenerate over it. Patch it by cell ID with `pid_drawio.DrawioFile`, and
  call `check()` before saving.
- **Glue every line end to a named port** of a catalogue symbol, or to a
  junction. Give every cell its tag as its ID.
- **draw.io desktop doesn't reload a file changed on disk.** Ask the user to
  save and close it before you patch it, and to reopen it afterwards.
- **Verify the export:** run the draw.io CLI, look at the PNG, and count the
  crossing gaps in the SVG.
- **Change symbols in `pid/pid_symbols.py` only,** then regenerate with
  `python pid/pid_symbols.py && python pid/pid_drawio.py`.

`examples/pid_drawio_example/` shows the shape a P&ID script should take.

## Do not commit non-public material

This repo is public. Client P&IDs, site or asset tags, and drawings
reconstructed from them don't belong here. Use them in the session and keep
them out of the repo; `private/` is gitignored for exactly this.
