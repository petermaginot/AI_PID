"""Repo policy checks: the skill, docs and manifests agree with each other.

Pure stdlib. Run from the repo root:

    python -m unittest discover -s tests
"""
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
MAX_BYTES = 5 * 1024 * 1024

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SECTION_REF_RE = re.compile(r"§(\d+(?:\.\d+)*)")
HEADING_NUM_RE = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\.?\s", re.M)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def skill_names():
    return sorted(d for d in os.listdir(SKILLS)
                  if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))


def skill_md_files(skill):
    out = []
    for dirpath, _, files in os.walk(os.path.join(SKILLS, skill)):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".md")]
    return sorted(out)


def strip_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def repo_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, capture_output=True, check=True).stdout
        return [p for p in out.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for dirpath, dirs, names in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "private", "__pycache__")]
            files += [os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                      for n in names]
        return files


class Skills(unittest.TestCase):

    def test_frontmatter(self):
        for name in skill_names():
            text = read(os.path.join(SKILLS, name, "SKILL.md"))
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            with self.subTest(skill=name):
                self.assertIsNotNone(m, "SKILL.md has no frontmatter")
                fields = dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l)
                self.assertEqual(fields.get("name", "").strip(), name)
                self.assertTrue(fields.get("description", "").strip())

    def test_section_refs_resolve(self):
        for name in skill_names():
            defined = set()
            for p in skill_md_files(name):
                defined.update(HEADING_NUM_RE.findall(read(p)))
            for p in skill_md_files(name):
                for ref in SECTION_REF_RE.findall(re.sub(r"```.*?```", "", read(p), flags=re.S)):
                    with self.subTest(file=os.path.relpath(p, ROOT), ref="§" + ref):
                        self.assertIn(ref, defined)


class Links(unittest.TestCase):

    def test_relative_links_resolve(self):
        docs = [os.path.join(ROOT, f) for f in ("README.md", "AGENTS.md")]
        docs.append(os.path.join(ROOT, "pid", "README.md"))
        for name in skill_names():
            docs += skill_md_files(name)
        for doc in docs:
            for target in LINK_RE.findall(strip_code(read(doc))):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                path = os.path.normpath(os.path.join(os.path.dirname(doc), target.split("#")[0]))
                with self.subTest(doc=os.path.relpath(doc, ROOT), link=target):
                    self.assertTrue(os.path.exists(path), "broken link")

    def test_every_skill_is_listed(self):
        names = set(skill_names())
        for doc in ("README.md", "AGENTS.md"):
            linked = set(re.findall(r"skills/([\w-]+)/SKILL\.md", read(os.path.join(ROOT, doc))))
            with self.subTest(doc=doc):
                self.assertEqual(linked, names)


class Manifests(unittest.TestCase):

    def test_plugin_manifests(self):
        plugin = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        market = json.loads(read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", plugin.get("version", "")))
        self.assertIn(plugin["name"], [p["name"] for p in market["plugins"]])


class Generated(unittest.TestCase):

    def test_symbol_files_match_catalogue(self):
        """symbols/*.svg are generated from the catalogue: none missing, none stale."""
        import sys
        sys.path.insert(0, os.path.join(ROOT, "pid"))
        import pid_symbols as S
        d = os.path.join(ROOT, "pid", "symbols")
        on_disk = {f[:-4] for f in os.listdir(d) if f.endswith(".svg") and not f.startswith("_")}
        self.assertEqual(on_disk, set(S.CATALOGUE))
        for n in S.CATALOGUE:
            with self.subTest(symbol=n):
                self.assertEqual(read(os.path.join(d, n + ".svg")), S.svg_text(n),
                                 "stale: run python pid/pid_symbols.py")


class PublicRepo(unittest.TestCase):

    def test_nothing_under_private(self):
        self.assertEqual([p for p in repo_files() if p.startswith("private/")], [])

    def test_file_size(self):
        for p in repo_files():
            full = os.path.join(ROOT, p)
            if os.path.isfile(full):
                with self.subTest(file=p):
                    self.assertLessEqual(os.path.getsize(full), MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
