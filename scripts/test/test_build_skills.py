"""scripts/build_skills.py: quick/skills/ copies of apache/doris-skills with the adapter hint (P5 / T5.1).

Runs against a small fixture upstream built in a temp git repo (no clone, no network); the builder's constants are
patched to the fixture's.

    .venv/bin/python -m unittest discover -s scripts/test -p 'test_build_skills.py' -v
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_skills  # noqa: E402

HINT = build_skills.HINT


def _folded(text: str) -> str:
    return "".join(f"  {line}\n" for line in textwrap.wrap(text, 80, break_on_hyphens=False))


LONG_DESCRIPTION = " ".join(f"Alpha trigger {i}: time-series, ETL/ELT and Lambda-style platforms." for i in range(20))
# Wrapped at 88 columns with breaks at hyphens it would split "point-query", which YAML reads back as "point- query".
OVERRIDE = " ".join(["Alpha, shorter: multi-engine, Lambda-style, time-series, ad-hoc and point-query workloads."] * 4)
ALPHA_FRONTMATTER = ("name: alpha\ndescription: >\n" + _folded(LONG_DESCRIPTION)
                     + 'license: Apache-2.0\nmetadata:\n  author: t\n  version: "1.0.0"\n')
ALPHA_BODY = ("\n# Alpha\n\n"
              "Read [the guide](references/guide.md#usage), [beta](../beta/SKILL.md) and [its scripts](../beta/scripts/).\n"
              "Cases: [index](references/old-index.md).\n"
              "Format: `Per [rule-name](references/rule-name.md)`.\n"
              "See [docs](https://docs.example.test/x), [mail](mailto:t@example.test) and [top](#alpha).\n")
FILES = {
    "LICENSE.txt": "Fixture licence text.\n",
    "CLI-CONTRACT.md": "# fixture contract\n\n`fixcli sql` runs SQL.\n",
    "README.md": "# fixture upstream\n",
    "verify/run.sh": "#!/bin/sh\necho verify\n",
    "skills/alpha/SKILL.md": f"---\n{ALPHA_FRONTMATTER}---\n{ALPHA_BODY}",
    "skills/alpha/references/guide.md": "# Guide\n\n## Usage\n",
    "skills/alpha/references/case-index.md": "# Cases\n",
    "skills/beta/SKILL.md": ("---\nname: beta\ndescription: Beta skill for short checks.\nversion: 0.2.0\n---\n"
                             "# Beta\n\nBody starts right after the frontmatter.\n"),
    "skills/beta/sub/SKILL.md": "---\nname: beta-sub\ndescription: >\n  Nested beta skill.\n---\n\n\n## Sub\n\nNested body.\n",
    "skills/beta/scripts/tool.py": "print('tool')\n",
    "skills/gamma/SKILL.md": "---\nname: gamma\ndescription: Excluded skill.\n---\n\n# Gamma\n",
}
CONFIG = {
    "SKILLS": ("alpha", "beta"),
    "TOP_LEVEL_FILES": ("LICENSE.txt", "CLI-CONTRACT.md"),
    "EXCLUDED": {"skills/gamma/": "reviews something else", "README.md": "upstream overview",
                 "verify/": "upstream tests"},
    "DESCRIPTION_OVERRIDES": {"alpha": OVERRIDE},
    "LINK_FIXES": {("alpha/SKILL.md", "old-index.md"): ("case-index.md", 1)},
    "BROKEN_LINKS_ALLOWED": {("alpha/SKILL.md", "references/rule-name.md"): "placeholder in the format template"},
}
COPIED = ["CLI-CONTRACT.md", "LICENSE.txt", "UPSTREAM.md", "alpha/SKILL.md", "alpha/references/case-index.md",
          "alpha/references/guide.md", "beta/SKILL.md", "beta/scripts/tool.py", "beta/sub/SKILL.md"]
GIT_ENV = {**os.environ, "GIT_AUTHOR_DATE": "2026-09-14T12:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-09-14T12:00:00+00:00"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def commit(repo: Path, changes: dict) -> str:
    """Write `changes` (path -> text, None deletes) into `repo` (created on first use), commit, return the sha."""
    if not repo.exists():
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
    for path, text in changes.items():
        target = repo / path
        if text is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    return _git(repo, "rev-parse", "HEAD")


def skill_md_with_hint(upstream: str) -> str:
    """What the builder must make of an upstream SKILL.md whose frontmatter it does not change."""
    end = upstream.index("\n---\n", 3) + 5
    return upstream[:end] + HINT + "\n\n" + upstream[end:].lstrip("\n")


def frontmatter_without_description(text: str) -> str:
    frontmatter = text[4:text.index("\n---\n", 3) + 1]
    return re.sub(r"^description: >\n(?: +\S.*\n)+", "", frontmatter, flags=re.M)


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.src = self.tmp / "upstream"
        self.sha = commit(self.src, FILES)
        self.out = self.tmp / "skills"
        self.patch(**CONFIG, LOCKED_COMMIT=self.sha)

    def patch(self, **values):
        for name, value in values.items():
            patcher = mock.patch.object(build_skills, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def render(self) -> dict[str, str]:
        return {p: b.decode("utf-8") for p, b in build_skills.render(self.src, self.sha).items()}

    def assert_build_error(self, *parts: str) -> str:
        with self.assertRaises(build_skills.BuildError) as cm:
            build_skills.render(self.src, self.sha)
        for part in parts:
            self.assertIn(part, str(cm.exception))
        return str(cm.exception)

    def main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = build_skills.main(["--source", str(self.src), "--out", str(self.out), *argv], out=out)
        return rc, out.getvalue()


class TestHint(_Case):
    def test_every_skill_md_starts_its_body_with_the_hint_and_is_otherwise_upstream(self):
        files = self.render()
        for rel in ("beta/SKILL.md", "beta/sub/SKILL.md"):
            with self.subTest(rel):
                self.assertEqual(files[rel], skill_md_with_hint(FILES[f"skills/{rel}"]))
                self.assertEqual(files[rel].count(HINT), 1)

    def test_a_body_right_after_the_frontmatter_gets_the_same_blank_line(self):
        self.assertIn(f"---\n{HINT}\n\n# Beta\n\nBody starts", self.render()["beta/SKILL.md"])

    def test_leading_blank_lines_of_the_body_collapse_into_the_one_after_the_hint(self):
        self.assertIn(f"---\n{HINT}\n\n## Sub\n", self.render()["beta/sub/SKILL.md"])

    def test_the_overridden_skill_md_gets_the_hint_too(self):
        alpha = self.render()["alpha/SKILL.md"]
        body = alpha[alpha.index("\n---\n", 3) + 5:]
        self.assertEqual(body, HINT + "\n\n" + ALPHA_BODY.lstrip("\n").replace("old-index.md", "case-index.md"))
        self.assertEqual(alpha.count(HINT), 1)

    def test_other_files_are_byte_identical(self):
        files = self.render()
        for rel in ("LICENSE.txt", "CLI-CONTRACT.md", "alpha/references/guide.md", "beta/scripts/tool.py"):
            with self.subTest(rel):
                self.assertEqual(files[rel], FILES[rel if "/" not in rel else f"skills/{rel}"])

    def test_a_skill_md_without_frontmatter_fails(self):
        self.sha = commit(self.src, {"skills/beta/sub/SKILL.md": "# Sub\n\nNo frontmatter.\n"})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/sub/SKILL.md", "frontmatter")


class TestDescriptions(_Case):
    def test_the_override_replaces_only_the_description(self):
        alpha = self.render()["alpha/SKILL.md"]
        self.assertEqual(frontmatter_without_description(alpha), frontmatter_without_description(FILES["skills/alpha/SKILL.md"]))
        meta = yaml.safe_load(alpha[4:alpha.index("\n---\n", 3) + 1])
        self.assertEqual(" ".join(meta["description"].split()), OVERRIDE)
        self.assertEqual((meta["name"], meta["license"], meta["metadata"]),
                         ("alpha", "Apache-2.0", {"author": "t", "version": "1.0.0"}))

    def test_the_override_is_a_folded_block_at_upstreams_indentation(self):
        alpha = self.render()["alpha/SKILL.md"]
        block = re.search(r"^description: >\n((?:.*\n)*?)license:", alpha, re.M).group(1).splitlines()
        self.assertGreater(len(block), 1)
        for line in block:
            self.assertRegex(line, r"^  \S")
            self.assertLessEqual(len(line), 88)

    def test_an_overlong_description_without_override_fails(self):
        self.patch(DESCRIPTION_OVERRIDES={})
        self.assert_build_error("alpha/SKILL.md", "1024")

    def test_an_overlong_override_fails(self):
        self.patch(DESCRIPTION_OVERRIDES={"alpha": "Alpha " * 200})
        self.assert_build_error("alpha/SKILL.md", "1024")

    def test_an_overlong_nested_description_fails(self):
        self.sha = commit(self.src, {"skills/beta/sub/SKILL.md": "---\nname: beta-sub\ndescription: >\n"
                                     + _folded(LONG_DESCRIPTION) + "---\n\n## Sub\n"})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/sub/SKILL.md", "1024")

    def test_an_override_that_yaml_does_not_read_back_fails(self):
        # YAML keeps the last of two `description` keys while the builder rewrites the first one.
        second = "description: >\n" + _folded(LONG_DESCRIPTION)
        alpha = FILES["skills/alpha/SKILL.md"].replace("license: Apache-2.0\n", second + "license: Apache-2.0\n")
        self.sha = commit(self.src, {"skills/alpha/SKILL.md": alpha})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("alpha/SKILL.md", "read back")

    def test_an_override_of_a_description_within_the_limit_fails(self):
        # Upstream shortened it: drop the override instead of hiding upstream's new text.
        self.patch(DESCRIPTION_OVERRIDES={"alpha": OVERRIDE, "beta": "Beta, shorter."})
        self.assert_build_error("beta/SKILL.md", "DESCRIPTION_OVERRIDES")


class TestSelection(_Case):
    def test_exactly_the_listed_skills_and_top_level_files_are_copied(self):
        self.assertEqual(sorted(self.render()), COPIED)

    def test_an_upstream_entry_neither_imported_nor_excluded_fails(self):
        self.sha = commit(self.src, {"NOTICE": "Fixture notice.\n", "skills/delta/SKILL.md": FILES["skills/gamma/SKILL.md"]})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("NOTICE", "skills/delta")

    def test_an_excluded_entry_upstream_no_longer_has_fails(self):
        self.patch(EXCLUDED={**CONFIG["EXCLUDED"], "skills/omega/": "gone"})
        self.assert_build_error("skills/omega")

    def test_the_files_come_from_the_commit_not_the_working_tree(self):
        (self.src / "LICENSE.txt").write_text("edited, not committed\n")
        (self.src / "skills" / "beta" / "untracked.md").write_text("untracked\n")
        files = self.render()
        self.assertEqual(files["LICENSE.txt"], FILES["LICENSE.txt"])
        self.assertNotIn("beta/untracked.md", files)

    def test_a_skill_without_skill_md_at_its_root_fails(self):
        self.sha = commit(self.src, {"skills/beta/SKILL.md": None})
        self.patch(LOCKED_COMMIT=self.sha)
        self.assert_build_error("beta/SKILL.md", "root")

    def test_the_source_must_be_at_the_locked_commit(self):
        head = commit(self.src, {"README.md": "# fixture upstream, newer\n"})
        message = self.assert_build_error(head, self.sha, f"git -C {self.src} fetch",
                                          f"git -C {self.src} checkout {self.sha}")
        self.assertNotIn("Traceback", message)

    def test_a_source_that_is_not_a_git_clone_fails(self):
        self.src = self.tmp / "empty"
        self.src.mkdir()
        self.assert_build_error(str(self.src))


class TestLinks(_Case):
    def test_the_link_fix_is_applied(self):
        alpha = self.render()["alpha/SKILL.md"]
        self.assertIn("[index](references/case-index.md)", alpha)
        self.assertNotIn("old-index.md", alpha)

    def test_a_link_fix_that_matches_a_different_number_of_times_fails(self):
        self.patch(LINK_FIXES={("alpha/SKILL.md", "old-index.md"): ("case-index.md", 2)})
        self.assert_build_error("LINK_FIXES", "alpha/SKILL.md")

    def test_a_link_fix_whose_text_is_gone_fails(self):
        self.patch(LINK_FIXES={**CONFIG["LINK_FIXES"], ("beta/SKILL.md", "no-such-text"): ("x", 1)})
        self.assert_build_error("LINK_FIXES", "beta/SKILL.md")

    def test_an_unlisted_broken_link_fails(self):
        self.patch(BROKEN_LINKS_ALLOWED={})
        self.assert_build_error("alpha/SKILL.md", "references/rule-name.md")

    def test_a_stale_allowed_link_fails(self):
        self.patch(BROKEN_LINKS_ALLOWED={**CONFIG["BROKEN_LINKS_ALLOWED"],
                                         ("alpha/SKILL.md", "references/guide.md#usage"): "was broken"})
        self.assert_build_error("BROKEN_LINKS_ALLOWED", "references/guide.md#usage")

    def test_which_links_count_as_broken(self):
        files = {"alpha/a.md": (b"[s](../beta/b.md#top) [d](../beta/) [u](https://example.test/x) [h](http://x) "
                                b"[m](mailto:t@example.test) [#](#here) [n](missing.md) [o](../../outside.md) "
                                b"![i](img/pic.png) [self](./a.md)"),
                 "alpha/img/pic.png": b"", "alpha/note.txt": b"[n](missing.md)", "beta/b.md": b"",
                 "other/c.md": b"[n](missing.md)"}
        self.assertEqual(build_skills.broken_links(files),
                         {("alpha/a.md", "missing.md"), ("alpha/a.md", "../../outside.md")})


class TestUpstreamMd(_Case):
    def test_records_the_source_and_every_change(self):
        text = self.render()["UPSTREAM.md"]
        for part in (build_skills.SOURCE_URL, self.sha, "2026-09-14", HINT, "`alpha/SKILL.md`",
                     f"{len(LONG_DESCRIPTION) + 1} -> {len(OVERRIDE) + 1}", "`old-index.md` -> `case-index.md`",
                     "`references/rule-name.md`", "placeholder in the format template",
                     "`skills/gamma/`: reviews something else", "`README.md`: upstream overview",
                     "`verify/`: upstream tests", "LICENSE.txt", "no NOTICE file",
                     f"build_skills.py --source", "--check"):
            self.assertIn(part, text)

    def test_lists_every_imported_skill_with_its_files_bytes_and_version(self):
        files = build_skills.render(self.src, self.sha)
        text = files["UPSTREAM.md"].decode()
        for skill, version in (("alpha", "1.0.0"), ("beta", "0.2.0")):
            inside = [p for p in files if p.startswith(skill + "/")]
            self.assertIn(f"| `{skill}/` | {len(inside)} | {sum(len(files[p]) for p in inside)} | {version} |", text)
        self.assertNotIn("gamma/` |", text)

    def test_rendering_twice_gives_identical_bytes(self):
        self.assertEqual(build_skills.render(self.src, self.sha), build_skills.render(self.src, self.sha))


class TestBuild(_Case):
    def _tree(self) -> dict[str, bytes]:
        return {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}

    def test_writes_the_rendered_tree_and_returns_its_paths(self):
        written = build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(written, COPIED)
        self.assertEqual(self._tree(), build_skills.render(self.src, self.sha))

    def test_keeps_other_entries_and_removes_stale_files_inside_the_copies(self):
        for rel, text in (("doris-mcp-adapter/SKILL.md", "hand-written\n"), ("notes.txt", "mine\n"),
                          ("alpha/stale.md", "old\n"), ("beta/old/deep/x.md", "old\n")):
            (self.out / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.out / rel).write_text(text)
        build_skills.build(self.src, self.out, self.sha)
        self.assertEqual((self.out / "doris-mcp-adapter" / "SKILL.md").read_text(), "hand-written\n")
        self.assertEqual((self.out / "notes.txt").read_text(), "mine\n")
        self.assertFalse((self.out / "alpha" / "stale.md").exists())
        self.assertFalse((self.out / "beta" / "old").exists())

    def test_building_twice_gives_identical_bytes(self):
        build_skills.build(self.src, self.out, self.sha)
        first = self._tree()
        build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(self._tree(), first)

    def test_a_failing_build_changes_nothing(self):
        (self.out / "alpha").mkdir(parents=True)
        (self.out / "alpha" / "stale.md").write_text("old\n")
        self.patch(DESCRIPTION_OVERRIDES={})
        with self.assertRaises(build_skills.BuildError):
            build_skills.build(self.src, self.out, self.sha)
        self.assertEqual(self._tree(), {"alpha/stale.md": b"old\n"})


class TestMain(_Case):
    def test_build_prints_a_short_summary(self):
        rc, out = self.main()
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, f"wrote {len(COPIED)} files to {self.out} ({self.sha[:12]})\n")

    def test_check_passes_on_a_fresh_build_and_ignores_the_adapter(self):
        build_skills.build(self.src, self.out, self.sha)
        (self.out / "doris-mcp-adapter").mkdir()
        (self.out / "doris-mcp-adapter" / "SKILL.md").write_text("hand-written\n")
        (self.out / "notes.txt").write_text("mine\n")
        rc, out = self.main("--check")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out, f"{self.out} matches {self.sha[:12]} ({len(COPIED)} files)\n")

    def test_check_lists_every_difference(self):
        build_skills.build(self.src, self.out, self.sha)
        (self.out / "beta" / "SKILL.md").write_text("tampered\n")
        (self.out / "alpha" / "references" / "guide.md").unlink()
        (self.out / "LICENSE.txt").unlink()
        (self.out / "alpha" / "extra.md").write_text("extra\n")
        (self.out / "doris-mcp-adapter").mkdir()
        (self.out / "doris-mcp-adapter" / "SKILL.md").write_text("hand-written\n")
        before = {p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}
        rc, out = self.main("--check")
        self.assertEqual(rc, 1, out)
        self.assertEqual(out.splitlines(), ["missing LICENSE.txt", "extra alpha/extra.md",
                                            "missing alpha/references/guide.md", "differs beta/SKILL.md",
                                            f"{self.out} does not match {self.sha[:12]}: 4 differences"])
        self.assertEqual({p: p.read_bytes() for p in self.out.rglob("*") if p.is_file()}, before)

    def test_check_of_a_missing_output_lists_every_file(self):
        rc, out = self.main("--check")
        self.assertEqual(rc, 1)
        self.assertEqual(out.splitlines()[:-1], [f"missing {p}" for p in COPIED])

    def test_a_wrong_commit_exits_2_with_the_fix(self):
        self.patch(LOCKED_COMMIT="0" * 40)
        for argv in ((), ("--check",)):
            with self.subTest(argv=argv):
                rc, out = self.main(*argv)
                self.assertEqual(rc, 2)
                self.assertTrue(out.startswith("FAIL: "), out)
                self.assertIn(f"git -C {self.src} checkout {'0' * 40}", out)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
