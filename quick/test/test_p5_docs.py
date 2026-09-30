"""quick/P5-guide.md, quick/P5-handoff.md and quick/runbook.md: what the person at the desktop follows (P5).

The rehearsals (T5.4) and the demo are run by hand from these files, so these checks keep them consistent with
the rest of the repo: the questions are the ones of design §10, in order, in both the guide and the runbook; the
act 2 reference tables are the ones the P4 guide checked; every tool named exists behind the Gateway and the
permission table follows D7; the skills to import are exactly the folders under quick/skills/; the reply
templates in the handoff are copies of the guide's; every script the runbook runs exists; and nothing that must
not leave the repo is in them.

quick/P5-guide.en.md and quick/runbook.en.md are the English versions for English-speaking listeners. They are
checked against the Chinese ones: the same headings at the same levels; each pinned English question next to its
Chinese original, in order; the same reference values, in the table cells and in the prose; the same skills,
permissions and commands; reply templates of the same shape; and a pointer from each version to the other.
"""

from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUICK = ROOT / "quick"
INSTRUCTIONS = QUICK / "agent-instructions.md"
GUIDE = QUICK / "P5-guide.md"
GUIDE_EN = QUICK / "P5-guide.en.md"
HANDOFF = QUICK / "P5-handoff.md"
RUNBOOK = QUICK / "runbook.md"
RUNBOOK_EN = QUICK / "runbook.en.md"
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
QUESTIONS_EN = (  # the English questions of the demo, verbatim and in the order of QUESTIONS
    "Check the Doris connection status",
    "This year's monthly GMV, order count and average order value: how do they compare with the same period last "
    "year? And by channel, what is the mini program's share?",
    "Which category contributed the most during the 618 and Double 11 promotions?",
    "Which shop has had an abnormal refund rate recently? What is the cause? Is there a logistics problem?",
    "Why does the query that counts daily UV of the tracking events take so long? Give the profile evidence",
    "Review the table design of fact_user_event: are the VARIANT column, partitioning and bucketing reasonable? "
    "Give improved DDL",
    "Recommend a data model for scenarios like agg_daily_traffic",
)
ASK_EACH_TIME = {"reload_semantic_layer"}  # D7: execute_query is Always Allow for rehearsals and the demo
RUNBOOK_PARTS = ["演示前", "设置", "演示流程", "出问题时", "演示后", "每步耗时"]
RUNBOOK_PARTS_EN = ["Before the demo", "Setup", "Demo flow", "If something goes wrong", "After the demo",
                    "Time per step"]
PART_A = {GUIDE: "Part A：导入 skills（T5.3）", GUIDE_EN: "Part A: Import the skills (T5.3)"}
PART_B = {GUIDE: "Part B：完整彩排 × 2", GUIDE_EN: "Part B: Full rehearsals × 2"}
PREPARATION = {GUIDE: "准备", GUIDE_EN: "Preparation"}
TEMPLATES = {GUIDE: "回复模板", GUIDE_EN: "Reply templates"}
DEMO_FLOW = {RUNBOOK: "演示流程", RUNBOOK_EN: "Demo flow"}
TROUBLE = {RUNBOOK: "出问题时", RUNBOOK_EN: "If something goes wrong"}
AFTER = {RUNBOOK: "演示后", RUNBOOK_EN: "After the demo"}
TIMES = {RUNBOOK: ("每步耗时", "| 步骤 |"), RUNBOOK_EN: ("Time per step", "| Step |")}  # section, table header
ENGLISH = {GUIDE: GUIDE_EN, RUNBOOK: RUNBOOK_EN}
FIXED_STRINGS = (  # the other strings the presenter copies: the English verbatim, its Chinese original, and where
    ("Are there any slow queries running on the cluster right now?", "现在集群上有没有正在运行的慢查询？",
     {GUIDE: (PART_A[GUIDE], "A5 "), GUIDE_EN: (PART_A[GUIDE_EN], "A5 ")}),
    ("Write your own query that counts daily UV on ecom.fact_user_event and run it with profile",
     "你自己写一条按天统计 ecom.fact_user_event UV 的查询，带 profile 执行",
     {GUIDE: (PART_B[GUIDE], "步骤 5"), GUIDE_EN: (PART_B[GUIDE_EN], "Step 5 "),
      RUNBOOK: (TROUBLE[RUNBOOK],), RUNBOOK_EN: (TROUBLE[RUNBOOK_EN],)}),
    ("There is no command line here. Use only the Doris MCP tools, following the doris-mcp-adapter mapping table",
     "这里没有命令行，只能用 Doris MCP 工具，按 doris-mcp-adapter 的对照表来",
     {RUNBOOK: (TROUBLE[RUNBOOK],), RUNBOOK_EN: (TROUBLE[RUNBOOK_EN],)}),
    ("Recompute with the start and end dates of 2026年618 and 2025年双11 in ecom.dim_promotion",
     "按 ecom.dim_promotion 里 2026年618 和 2025年双11 的起止日期重算",
     {RUNBOOK: (TROUBLE[RUNBOOK],), RUNBOOK_EN: (TROUBLE[RUNBOOK_EN],)}),
)
DEMO_FLOW_HEADER_EN = "| Step | Part | Question | Chinese original | What to show / say | Expected |"
REFERENCE_TABLES = (  # the start of the header line in the Chinese guide and in the English one
    ("| 月份 | GMV |", "| Month | GMV |"),
    ("| 渠道 | GMV |", "| Channel | GMV |"),
    ("| 类目 | 2026年618 |", "| Category | 618 (2026) |"),
    ("| 类目 | 2025年双11 |", "| Category | Double 11 (2025) |"),
)
# A reference value in a table or in the prose: a decimal, a percentage, a date, a comma-grouped number, a range
# (1–3), a count before and after (0 → 52), a number of ms, days or months, a bucket count, or a bare number of two
# or more digits, also when Chinese text touches it (2026年618). Every one carries over to the English version
# unchanged. Single digits in other places are step numbers, rounds and counts of questions, which the headings and
# the templates already pin.
VALUE = re.compile(r"[+-]?\d[\d,]*\.\d+%?|[+-]?\d+(?:\.\d+)?%|\d{4}-\d{2}-\d{2}|\d{1,3}(?:,\d{3})+|\d+–\d+"
                   r"|\d+ → \d+|\d+ (?:ms|days|months)(?![A-Za-z])|BUCKETS \d+|(?<!\d)\d{2,}(?!\d)")
CHINESE_CODE = re.compile(r"`[^`\n]*[\u4e00-\u9fff][^`\n]*`")  # a backticked span with Chinese in it


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(path), re.M | re.S)
    if match is None:
        raise AssertionError(f"{path.name}: no section '## {title}'")
    return match.group(1)


def _fenced(text: str) -> list[str]:
    return re.findall(r"^```\n(.*?)^```$", text, re.M | re.S)


def _commands(text: str) -> list[tuple[str, str]]:
    """(indent, body) of every fenced block, also those indented in a list item, with each <placeholder> blanked:
    the English versions translate the placeholders and nothing else."""
    return [(indent, re.sub(r"<[^<>\n]+>", "<>", body))
            for indent, body in re.findall(r"^( *)```\n(.*?)^\1```$", text, re.M | re.S)]


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


def _data_rows(table: list[str]) -> list[list[str]]:
    """The cells of the data rows of a table from _table (not the header line and the |---| line)."""
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in table[2:]]


def _headings(path: Path) -> list[str]:
    return re.findall(r"^(#+) ", _text(path), re.M)


def _top_block(path: Path) -> str:
    return _text(path).split("\n## ", 1)[0]


def _values(text: str) -> Counter:
    """The reference values of a text. N 万 counts as N/100, as the English writes it (102 万 is 1.02 million), and
    天 / 个月 as days / months."""
    text = re.sub(r"(\d+(?:\.\d+)?) ?万", lambda m: str(Decimal(m.group(1)) / 100), text)
    text = re.sub(r"(\d+) ?(?:天|days?\b)", r"\1 days", text)
    text = re.sub(r"(\d+) ?(?:个月|months?\b)", r"\1 months", text)
    return Counter(VALUE.findall(text))


def _without_chinese_code(text: str) -> str:
    """An English text without its backticked Chinese spans: the Chinese originals of the questions it quotes
    next to the English ones would otherwise count the values of a question twice."""
    return CHINESE_CODE.sub("", text)


def _value_parts(section: str) -> list[str]:
    """The parts of a section whose values must match part for part: the text before the first ### heading and each
    ### subsection; in a section without subsections, the text outside the table and each table line."""
    if re.search(r"^### ", section, re.M):
        return re.split(r"^(?=### )", section, flags=re.M)
    lines = section.splitlines()
    rows = [line for line in lines if line.startswith("|")]
    return ["\n".join(line for line in lines if not line.startswith("|")), *rows]


def _part(path: Path, title: str, heading: str | None = None) -> str:
    """The section `## title`, or its ### subsection whose heading starts with `heading`."""
    section = _section(path, title)
    if heading is None:
        return section
    match = re.search(rf"^### {re.escape(heading)}.*?\n(.*?)(?=^### |\Z)", section, re.M | re.S)
    if match is None:
        raise AssertionError(f"{path.name}: no '### {heading}…' in '## {title}'")
    return match.group(1)


def _one_line(text: str, key: str, strip_backticks: bool = False) -> str:
    """The one line of `text` that holds `key`, without its backticks if asked; fails on no line or several."""
    lines = [line for line in text.splitlines() if key in line]
    if len(lines) != 1:
        raise AssertionError(f"{len(lines)} lines hold {key!r}: {lines}")
    return lines[0].replace("`", "") if strip_backticks else lines[0]


def _scripts(path: Path) -> list[str]:
    return re.findall(r"(?:bash|python) ((?:scripts|infra|doris)/[\w./-]+)", _text(path))


def _skill_rows(path: Path) -> list[tuple[str, str]]:
    return re.findall(r"^\| (\d) \| `([a-z0-9-]+)` \|", _section(path, PART_A[path]), re.M)


def _gateway_tools() -> set[str]:
    calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
    return {c["tool"] for c in calls}


def _in_order(text: str, items: tuple[str, ...]) -> bool:
    positions = [text.find(f"`{item}`") for item in items]
    return -1 not in positions and positions == sorted(positions)


class Questions(unittest.TestCase):
    def _assert_asked_in_order(self, sections: dict[Path, str]):
        """Both versions ask the Chinese questions in order; the English version also asks the English ones."""
        for path, title in sections.items():
            for questions in (QUESTIONS, QUESTIONS_EN) if path.name.endswith(".en.md") else (QUESTIONS,):
                with self.subTest(doc=path.name, english=questions is QUESTIONS_EN):
                    self.assertTrue(_in_order(_section(path, title), questions))

    def test_the_guide_asks_the_design_questions_in_order(self):
        self._assert_asked_in_order(PART_B)

    def test_the_runbook_asks_the_same_questions_in_order(self):
        self._assert_asked_in_order(DEMO_FLOW)

    def test_each_english_step_has_its_question_and_under_it_the_chinese_original(self):
        steps = re.findall(r"^### (Step .*)\n\n(.*)$", _section(GUIDE_EN, PART_B[GUIDE_EN]), re.M)
        self.assertEqual(len(steps), len(QUESTIONS))
        for i, (heading, first_line) in enumerate(steps):
            with self.subTest(step=i + 1):
                self.assertTrue(heading.startswith(f"Step {i + 1} "), heading)
                self.assertTrue(heading.endswith(f": `{QUESTIONS_EN[i]}`"), heading)
                self.assertEqual(first_line, f"Chinese original: `{QUESTIONS[i]}`")

    def test_each_english_runbook_row_has_its_question_and_the_chinese_original(self):
        rows = [row for row in _data_rows(_table(_section(RUNBOOK_EN, DEMO_FLOW[RUNBOOK_EN]), DEMO_FLOW_HEADER_EN))
                if row[0] != "—"]  # the two acts the presenter does outside Quick
        self.assertEqual([row[0] for row in rows], [str(i) for i in range(1, len(QUESTIONS) + 1)])
        for row, question_en, question in zip(rows, QUESTIONS_EN, QUESTIONS):
            with self.subTest(step=row[0]):
                self.assertEqual(row[2:4], [f"`{question_en}`", f"`{question}`"])

    def test_the_act_2_reference_tables_are_the_p4_ones(self):
        for header in ("| 月份 | GMV |", "| 渠道 | GMV |"):
            with self.subTest(header=header):
                self.assertEqual(_table(_text(GUIDE), header), _table(_text(P4_GUIDE), header))

    def test_the_english_reference_tables_have_the_chinese_values(self):
        for header, header_en in REFERENCE_TABLES:
            with self.subTest(table=header_en):
                rows = _data_rows(_table(_text(GUIDE), header))
                rows_en = _data_rows(_table(_text(GUIDE_EN), header_en))
                self.assertTrue(rows)
                self.assertEqual(len(rows_en), len(rows))
                for row, row_en in zip(rows, rows_en):
                    self.assertEqual(row_en[1:], row[1:])
                    name = row[0].split("（")[0]  # the data value, then its gloss: 家用电器 (Home appliances)
                    self.assertTrue(row_en[0].startswith("Total" if name.startswith("合计") else name), row_en[0])

    def test_every_reference_value_carries_over_to_the_same_part_of_the_english_version(self):
        # Part for part (the steps of the guide, the rows of the runbook), so that a value moved to another step
        # is caught too.
        for path, path_en, sections in ((GUIDE, GUIDE_EN, PART_B), (RUNBOOK, RUNBOOK_EN, DEMO_FLOW)):
            parts = _value_parts(_section(path, sections[path]))
            parts_en = _value_parts(_section(path_en, sections[path_en]))
            self.assertEqual(len(parts_en), len(parts), path_en.name)  # zip would pair the wrong parts
            with self.subTest(doc=path_en.name):
                self.assertTrue(sum(map(_values, parts), Counter()))
            for part, part_en in zip(parts, parts_en):
                with self.subTest(doc=path_en.name, part=part_en.strip().partition("\n")[0][:60]):
                    self.assertEqual(dict(_values(part) - _values(_without_chinese_code(part_en))), {})

    def test_the_other_fixed_strings_stand_in_their_place_in_both_versions(self):
        for english, chinese, places in FIXED_STRINGS:
            for path, place in places.items():
                with self.subTest(string=english, doc=path.name):
                    part = _part(path, *place)
                    self.assertIn(chinese, part)
                    if path in ENGLISH:
                        self.assertIn(ENGLISH[path], places)  # and in the same place of the English version
                    else:
                        self.assertIn(f"`{english}`", part)

    def test_step_3_expects_the_promotion_periods_of_the_instructions(self):
        # The two periods are written in quick/agent-instructions.md (they are the dim_promotion dates), so the
        # agent need not query dim_promotion first; one query to check them is fine.
        for path, heading, key, terms in (
                (GUIDE, "步骤 3", "- 期望：", ("按指令里写的两个活动期过滤", "`ecom.dim_promotion` 里的起止日期",
                                            "先查一次 `ecom.dim_promotion` 核对也可以")),
                (GUIDE_EN, "Step 3", "- Expected:", ("the two promotion periods written in the instructions",
                                                     "the start and end dates in `ecom.dim_promotion`",
                                                     "query `ecom.dim_promotion` once to check them"))):
            with self.subTest(doc=path.name):
                line = _one_line(_part(path, PART_B[path], heading), key)
                for term in terms:
                    self.assertIn(term, line)


class Setup(unittest.TestCase):
    def test_the_skills_to_import_are_the_folders_under_quick_skills(self):
        folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        for name in folders:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)
        for path in (GUIDE, GUIDE_EN):
            with self.subTest(doc=path.name):
                rows = _skill_rows(path)
                self.assertEqual([int(n) for n, _ in rows], list(range(1, len(rows) + 1)))
                self.assertEqual(rows[0][1], "doris-mcp-adapter")
                self.assertEqual({name for _, name in rows}, folders)
        self.assertEqual(_skill_rows(GUIDE_EN), _skill_rows(GUIDE))

    def test_the_permission_table_lists_every_tool_as_d7_says(self):
        for path in (GUIDE, GUIDE_EN):
            rows = dict(re.findall(rf"^\| `{GATEWAY_PREFIX}(\w+)` \| ([A-Za-z ]+?) \|",
                                   _section(path, PART_A[path]), re.M))
            with self.subTest(doc=path.name):
                self.assertEqual(set(rows), _gateway_tools())
            for tool, permission in rows.items():
                with self.subTest(doc=path.name, tool=tool):
                    self.assertEqual(permission, "Ask Each Time" if tool in ASK_EACH_TIME else "Always Allow")

    def test_the_handoff_templates_are_copies_of_the_guides(self):
        guide = _fenced(_section(GUIDE, TEMPLATES[GUIDE]))
        self.assertEqual(len(guide), 2)
        self.assertEqual(_fenced(_section(HANDOFF, "做完后")), guide)

    def test_the_english_templates_have_the_shape_of_the_chinese_ones(self):
        # Line for line translations: the user may reply with either language's template.
        guide = _fenced(_section(GUIDE, TEMPLATES[GUIDE]))
        guide_en = _fenced(_section(GUIDE_EN, TEMPLATES[GUIDE_EN]))
        self.assertEqual(len(guide_en), 2)
        self.assertEqual([len(t.splitlines()) for t in guide_en], [len(t.splitlines()) for t in guide])
        steps = [str(i) for i in range(1, len(QUESTIONS) + 1)]
        self.assertEqual(re.findall(r"^Step (\d) ", guide_en[1], re.M), steps)

    def test_the_english_scp_command_is_the_chinese_one(self):
        commands = _commands(_section(GUIDE, PREPARATION[GUIDE]))
        self.assertTrue(commands)
        self.assertEqual(_commands(_section(GUIDE_EN, PREPARATION[GUIDE_EN])), commands)

    def test_the_guides_give_the_length_of_the_instructions(self):
        # A2 says how long the text to paste is, to 100 characters.
        length = (len(_text(INSTRUCTIONS)) + 50) // 100 * 100
        for path, phrase in ((GUIDE, f"约 {length} 字符"), (GUIDE_EN, f"about {length} characters")):
            with self.subTest(doc=path.name):
                self.assertIn(phrase, _section(path, PART_A[path]))

    def test_the_guides_and_the_handoff_list_the_rules_added_after_rehearsal_1(self):
        # T5.4 round 1 added three rules to quick/agent-instructions.md; the user checks the pasted text by the list.
        # The promotion rule gives the two periods of the demo, the dim_promotion dates.
        chinese = ("类目维度名", "618、双 11 的活动期（dim_promotion 的起止日期）", "差评原因用倒排索引检索")
        for path, text, key, items in (
                (GUIDE, _part(GUIDE, PART_A[GUIDE], "A2 "), "新版比 P4 多了几条", chinese),
                (GUIDE_EN, _part(GUIDE_EN, PART_A[GUIDE_EN], "A2 "), "Compared with P4, the new version adds",
                 ("the category dimension names", "the 618 and Double 11 periods (the dim_promotion dates)",
                  "review causes through the inverted index")),
                (HANDOFF, _section(HANDOFF, "当前状态"), "`quick/agent-instructions.md` 更新了", chinese)):
            with self.subTest(doc=path.name):
                line = _one_line(text, key, strip_backticks=True)
                for item in items:
                    self.assertIn(item, line)


class Runbook(unittest.TestCase):
    def test_has_exactly_its_parts(self):
        for path, parts in ((RUNBOOK, RUNBOOK_PARTS), (RUNBOOK_EN, RUNBOOK_PARTS_EN)):
            with self.subTest(doc=path.name):
                self.assertEqual(re.findall(r"^## (.+)$", _text(path), re.M), parts)

    def test_every_script_it_runs_exists(self):
        for doc in (RUNBOOK, RUNBOOK_EN):
            paths = _scripts(doc)
            with self.subTest(doc=doc.name):
                self.assertIn("scripts/demo-check.sh", paths)
            for path in paths:
                with self.subTest(doc=doc.name, path=path):
                    self.assertTrue((ROOT / path).is_file())

    def test_the_english_commands_are_the_chinese_ones(self):
        commands = _commands(_text(RUNBOOK))
        self.assertTrue(commands)
        self.assertEqual(_scripts(RUNBOOK_EN), _scripts(RUNBOOK))
        self.assertEqual(_commands(_text(RUNBOOK_EN)), commands)

    def test_the_cleanup_keeps_the_cdk_bootstrap_stack(self):
        # CDKToolkit and its S3 bucket existed before this project (the agentcore deploy only uploaded its assets
        # to the bucket); other CDK projects of the same account and region may use them. infra/99-cleanup.sh
        # deletes only the stack STACK_NAME, never the bootstrap stack, a bucket or the uploaded assets, and the
        # runbooks say so.
        cleanup = (ROOT / "infra" / "99-cleanup.sh").read_text(encoding="utf-8")
        self.assertRegex(cleanup, r'(?m)^STACK_NAME="\$\{STACK_NAME:-AgentCore-dorismcp-default\}"$')
        self.assertNotRegex(cleanup, r"(?i)delete-stack[^\n]*CDKToolkit|cdk\s+destroy"
                                     r"|s3api\s+delete-(?:bucket|objects?)\b|s3\s+(?:rb|rm)\b")
        for path, terms in ((RUNBOOK, ("不删除", "`CDKToolkit`", "S3 桶", "本项目之前就已存在",
                                       "只往桶里上传了资产", "所以保留", "也留在这个桶里")),
                            (RUNBOOK_EN, ("does not delete", "`CDKToolkit`", "S3 bucket",
                                          "existed before this project", "only uploaded its assets",
                                          "so they are kept", "also stay in that bucket"))):
            with self.subTest(doc=path.name):
                line = _one_line(_section(path, AFTER[path]), "CDKToolkit")
                for term in terms:
                    self.assertIn(term, line)

    def test_the_step_3_shares_bullet_gives_the_same_shares_in_both_versions(self):
        # Rehearsal: the agent still computed 618 on its own dates. 31.45% (618) and 27.94% (双 11) are the top
        # shares on its own ranges (06-01..06-18, 11-01..11-11), checked on the data; the presenter compares them
        # with the answer. The value test of the demo flow does not cover 出问题时 / If something goes wrong.
        shares = {path: re.findall(r"\d+(?:\.\d+)?%", _one_line(_section(path, TROUBLE[path]), key))
                  for path, key in ((RUNBOOK, "第 3 步的占比和参照值对不上"), (RUNBOOK_EN, "shares of step 3"))}
        self.assertEqual(shares[RUNBOOK], ["31.45%", "27.94%"])
        self.assertEqual(shares[RUNBOOK_EN], shares[RUNBOOK])

    def test_the_time_table_is_filled_in_with_the_same_numbers_in_both_versions(self):
        # T5.5 fills it from rehearsal 1; round 2 was skipped (its cell reads 跳过 / skipped)
        zh, en = (_data_rows(_table(_section(path, TIMES[path][0]), TIMES[path][1]))
                  for path in (RUNBOOK, RUNBOOK_EN))
        self.assertEqual([row[0] for row in zh], [str(step) for step in range(1, 8)])
        self.assertEqual(len(en), len(zh))
        for row_zh, row_en in zip(zh, en):
            with self.subTest(step=row_zh[0]):
                self.assertNotIn("—", row_zh + row_en)
                self.assertEqual((row_zh[3], row_en[3]), ("跳过", "skipped"))
                numbers = [row_zh[0], row_zh[2], *row_zh[4:]]
                self.assertTrue(all(re.fullmatch(r"\d+(?:\.\d)?", cell) for cell in numbers), row_zh)
                self.assertEqual([row_en[0], row_en[2], *row_en[4:]], numbers)


class English(unittest.TestCase):
    """Each English version has the shape of its Chinese version and each points to the other."""

    PAIRS = ((GUIDE, GUIDE_EN), (RUNBOOK, RUNBOOK_EN))

    def test_the_same_headings_at_the_same_levels(self):
        for path, path_en in self.PAIRS:
            with self.subTest(doc=path_en.name):
                self.assertEqual(_headings(path_en), _headings(path))

    def test_each_version_points_to_the_other_at_the_top(self):
        for path, path_en in self.PAIRS:
            for doc, other in ((path, path_en), (path_en, path)):
                with self.subTest(doc=doc.name):
                    self.assertIn(f"`quick/{other.name}`", _top_block(doc))

    def test_the_english_versions_refer_to_the_english_documents(self):
        # A Chinese file that has an English version is named only where the Chinese file itself is meant: the
        # back-pointer ("Chinese version: `…`") and the Chinese template ("the Chinese one in `…`"). Backticked
        # or not: a plain quick/runbook.md in an English file points at the Chinese file just the same.
        chinese = "|".join(re.escape(f"quick/{path.name}") for path, _ in self.PAIRS)
        for _, path_en in self.PAIRS:
            for line in _text(path_en).splitlines():
                for match in re.finditer(rf"(?<![\w/.-])(?:{chinese})\b", line):
                    with self.subTest(doc=path_en.name, line=line[:60]):
                        self.assertRegex(line[:match.start()], r"\bChinese\b[^`]{0,20}`?$")


class Hygiene(unittest.TestCase):
    DOCS = (GUIDE, GUIDE_EN, HANDOFF, RUNBOOK, RUNBOOK_EN)

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
