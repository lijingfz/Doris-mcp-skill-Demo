"""quick/P5-guide.md, quick/P5-handoff.md and quick/runbook.md: what the person at the desktop follows (P5).

The rehearsals (T5.4) and the demo are run by hand from these files, so these checks keep them consistent with
the rest of the repo: the questions are the ones of design §10, in order, in both the guide and the runbook; the
act 2 reference tables are the ones the P4 guide checked; every tool named exists behind the Gateway and the
permission table follows D7; the skills to import are exactly the folders under quick/skills/; the reply
templates in the handoff are copies of the guide's; every script the runbook runs exists; and nothing that must
not leave the repo is in them.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUICK = ROOT / "quick"
GUIDE = QUICK / "P5-guide.md"
HANDOFF = QUICK / "P5-handoff.md"
RUNBOOK = QUICK / "runbook.md"
P4_GUIDE = QUICK / "P4-guide.md"
SKILLS = QUICK / "skills"
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
QUESTIONS = (  # design §10, verbatim and in order
    "检查一下 Doris 连接状态",
    "今年每月 GMV、订单数和客单价，跟去年同期比呢？分渠道看小程序占比",
    "618 和双 11 哪个类目贡献最大？",
    "最近哪家店的退款率异常？原因是什么？物流有没有问题？",
    "按天统计埋点 UV 这个查询为什么要这么久？给出 profile 证据",
    "评审 fact_user_event 的建表：VARIANT、分区、分桶合理吗？给出改进 DDL",
    "为 agg_daily_traffic 这类场景推荐数据模型",
)
ASK_EACH_TIME = {"reload_semantic_layer"}  # D7: execute_query is Always Allow for rehearsals and the demo
RUNBOOK_PARTS = ["演示前", "设置", "演示流程", "出问题时", "演示后", "每步耗时"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(path), re.M | re.S)
    if match is None:
        raise AssertionError(f"{path.name}: no section '## {title}'")
    return match.group(1)


def _fenced(text: str) -> list[str]:
    return re.findall(r"^```\n(.*?)^```$", text, re.M | re.S)


def _table(text: str, header: str) -> list[str]:
    """The lines of the Markdown table whose header line starts with `header`."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    table = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        table.append(line)
    return table


def _gateway_tools() -> set[str]:
    calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
    return {c["tool"] for c in calls}


def _in_order(text: str, items: tuple[str, ...]) -> bool:
    positions = [text.find(f"`{item}`") for item in items]
    return -1 not in positions and positions == sorted(positions)


class Questions(unittest.TestCase):
    def test_the_guide_asks_the_design_questions_in_order(self):
        self.assertTrue(_in_order(_section(GUIDE, "Part B：完整彩排 × 2"), QUESTIONS))

    def test_the_runbook_asks_the_same_questions_in_order(self):
        self.assertTrue(_in_order(_section(RUNBOOK, "演示流程"), QUESTIONS))

    def test_the_act_2_reference_tables_are_the_p4_ones(self):
        for header in ("| 月份 | GMV |", "| 渠道 | GMV |"):
            with self.subTest(header=header):
                self.assertEqual(_table(_text(GUIDE), header), _table(_text(P4_GUIDE), header))


class Setup(unittest.TestCase):
    def test_the_skills_to_import_are_the_folders_under_quick_skills(self):
        rows = re.findall(r"^\| (\d) \| `([a-z0-9-]+)` \|", _section(GUIDE, "Part A：导入 skills（T5.3）"), re.M)
        self.assertEqual([int(n) for n, _ in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(rows[0][1], "doris-mcp-adapter")
        folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual({name for _, name in rows}, folders)
        for name in folders:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)

    def test_the_permission_table_lists_every_tool_as_d7_says(self):
        rows = dict(re.findall(rf"^\| `{GATEWAY_PREFIX}(\w+)` \| ([A-Za-z ]+?) \|", _text(GUIDE), re.M))
        self.assertEqual(set(rows), _gateway_tools())
        for tool, permission in rows.items():
            with self.subTest(tool=tool):
                self.assertEqual(permission, "Ask Each Time" if tool in ASK_EACH_TIME else "Always Allow")

    def test_the_handoff_templates_are_copies_of_the_guides(self):
        guide = _fenced(_section(GUIDE, "回复模板"))
        self.assertEqual(len(guide), 2)
        self.assertEqual(_fenced(_section(HANDOFF, "做完后")), guide)


class Runbook(unittest.TestCase):
    def test_has_exactly_its_parts(self):
        self.assertEqual(re.findall(r"^## (.+)$", _text(RUNBOOK), re.M), RUNBOOK_PARTS)

    def test_every_script_it_runs_exists(self):
        paths = re.findall(r"(?:bash|python) ((?:scripts|infra|doris)/[\w./-]+)", _text(RUNBOOK))
        self.assertIn("scripts/demo-check.sh", paths)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())


class Hygiene(unittest.TestCase):
    DOCS = (GUIDE, HANDOFF, RUNBOOK)

    def test_every_tool_named_exists_behind_the_gateway(self):
        tools = _gateway_tools()
        for path in self.DOCS:
            with self.subTest(doc=path.name):
                named = set(re.findall(rf"\b{GATEWAY_PREFIX}(\w+)", _text(path)))
                self.assertEqual(named - tools, set())

    def test_no_urls_addresses_arns_or_account_ids(self):
        for path in self.DOCS:
            text = _text(path)
            for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
                            r"amazonaws\.com"):
                with self.subTest(doc=path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text))


if __name__ == "__main__":
    unittest.main()
