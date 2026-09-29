"""quick/skills/: the Agent Skills imported into Quick next to the "Doris 专家" agent (P5 / T5.1).

The four upstream copies are generated from apache/doris-skills by scripts/build_skills.py and committed; these
checks read the committed tree only (no builder run, no upstream clone). They protect what Quick's skill import
and the agent depend on: the folder set, a SKILL.md with valid frontmatter within Quick's limits in every folder,
the adapter hint at the top of every copied SKILL.md, the licence and provenance files, the triggers kept by the
shortened descriptions, and relative links that resolve.
"""

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_skills  # noqa: E402

SKILLS_DIR = ROOT / "quick" / "skills"
ADAPTER = "doris-mcp-adapter"
FOLDERS = {"doris-architecture-advisor", "doris-best-practices", "doris-debug", ADAPTER, "doris-profile-reader"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_LIMIT, DESCRIPTION_LIMIT, FOLDER_LIMIT = 64, 1024, 6 * 1024 * 1024  # Quick's skill import limits

# Triggers the shortened descriptions keep on purpose (upstream's when-to-use lists, condensed).
TRIGGERS = {
    "doris-architecture-advisor": (
        "MUST USE", "data architectures", "data models", "ingestion", "sizing clusters", "business requirements",
        "IoT", "sensor", "telemetry", "real-time analytics", "dashboards", "log analysis", "log search", "CDC sync",
        "time-series", "device monitoring", "point query", "ad-hoc analytics", "lakehouse federation", "ETL/ELT",
        "report", "clickstream", "user behavior", "observability", "metrics", "fleet tracking", "OLAP",
        "table design from scratch", "design a table for", "how should I store", "build an architecture for",
        "devices sending data every", "cluster size", "what data model should I use", "ingest X GB/day",
        "MySQL/PostgreSQL", "Impala", "Kudu", "Elasticsearch/ES", "Greenplum", "Presto", "HBase", "Hive",
        "Hadoop", "Redis", "Lambda-style", "even when Doris is not named"),
    "doris-best-practices": (
        "ALSO MUST USE whenever the doris-architecture-advisor skill produces DDL — apply the Pre-Flight "
        "Checklist to every CREATE TABLE before output.",
        "MUST USE when writing, reviewing, or optimizing Doris CREATE TABLE", "partition/bucket", "data models",
        "cluster configurations", "cluster sizing", "IoT", "analytics", "dashboard", "CDC", "time-series",
        "log analysis", "real-time warehouse", "point query", "data platform", "table design", "Impala", "Kudu",
        "Elasticsearch/ES", "Greenplum", "Presto", "HBase", "Hive", "Hadoop", "Redis", "Lambda-style",
        "even when Doris is not named", "connection string", "get started", "slow query", "query profiling",
        "runtime performance diagnosis", "tablet skew", "table health", "out of scope"),
}


def _split(path: Path) -> tuple[dict, str]:
    """(frontmatter as parsed YAML, body) of a SKILL.md: the YAML between the first line `---` and the next."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?\n)?---\n", text, re.S)
    if match is None:
        raise AssertionError(f"{path.relative_to(ROOT)}: no frontmatter")
    meta = yaml.safe_load(match.group(1) or "")
    if not isinstance(meta, dict):
        raise AssertionError(f"{path.relative_to(ROOT)}: frontmatter is not a mapping")
    return meta, text[match.end():]


def _folders() -> set[str]:
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}


class Layout(unittest.TestCase):
    def test_the_four_upstream_copies_are_there(self):
        self.assertEqual(_folders() - {ADAPTER}, set(build_skills.SKILLS))

    def test_exactly_the_five_skill_folders(self):
        self.assertEqual(_folders(), FOLDERS)

    def test_licence_contract_and_provenance(self):
        for name in ("LICENSE.txt", "CLI-CONTRACT.md"):
            self.assertTrue((SKILLS_DIR / name).is_file(), name)
        self.assertIn(build_skills.LOCKED_COMMIT, (SKILLS_DIR / "UPSTREAM.md").read_text(encoding="utf-8"))


class SkillFolders(unittest.TestCase):
    def _check(self, folder: str):
        meta, _ = _split(SKILLS_DIR / folder / "SKILL.md")
        self.assertEqual(meta.get("name"), folder)
        self.assertRegex(folder, NAME_RE)
        self.assertLessEqual(len(folder), NAME_LIMIT)
        description = meta.get("description")
        self.assertIsInstance(description, str)
        self.assertTrue(description.strip())
        self.assertLessEqual(len(description), DESCRIPTION_LIMIT)
        size = sum(p.stat().st_size for p in (SKILLS_DIR / folder).rglob("*") if p.is_file())
        self.assertLessEqual(size, FOLDER_LIMIT)

    def test_every_copy_has_a_skill_md_within_quicks_limits(self):
        for folder in build_skills.SKILLS:
            with self.subTest(folder):
                self._check(folder)

    def test_the_adapter_has_a_skill_md_within_quicks_limits(self):
        self._check(ADAPTER)


class Hint(unittest.TestCase):
    def test_every_copied_skill_md_starts_with_the_adapter_hint(self):
        paths = sorted(p for skill in build_skills.SKILLS for p in (SKILLS_DIR / skill).rglob("SKILL.md"))
        self.assertGreater(len(paths), len(build_skills.SKILLS))  # the nested doris-debug domain skills too
        for path in paths:
            with self.subTest(str(path.relative_to(SKILLS_DIR))):
                _, body = _split(path)
                self.assertTrue(body.startswith(build_skills.HINT + "\n\n"), body[:80])
                self.assertEqual(path.read_text(encoding="utf-8").count(build_skills.HINT), 1)


class Descriptions(unittest.TestCase):
    def test_the_overrides_are_the_builders(self):
        self.assertEqual(set(build_skills.DESCRIPTION_OVERRIDES), set(TRIGGERS))
        for skill, text in build_skills.DESCRIPTION_OVERRIDES.items():
            with self.subTest(skill):
                meta, _ = _split(SKILLS_DIR / skill / "SKILL.md")
                self.assertEqual(" ".join(meta["description"].split()), " ".join(text.split()))

    def test_the_shortened_descriptions_keep_their_triggers(self):
        for skill, phrases in TRIGGERS.items():
            meta, _ = _split(SKILLS_DIR / skill / "SKILL.md")
            description = " ".join(meta["description"].split())
            for phrase in phrases:
                with self.subTest(skill=skill, phrase=phrase):
                    self.assertIn(phrase, description)


class Links(unittest.TestCase):
    def test_every_relative_link_in_the_copies_resolves_or_is_allowed(self):
        files = {p.relative_to(SKILLS_DIR).as_posix(): p.read_bytes() for p in SKILLS_DIR.rglob("*") if p.is_file()}
        self.assertEqual(build_skills.broken_links(files), set(build_skills.BROKEN_LINKS_ALLOWED))


if __name__ == "__main__":
    unittest.main()
