"""quick/skills/doris-mcp-adapter/SKILL.md: how the doris-* skills reach Doris in Quick (P5 / T5.2).

The imported doris-* skills are written for doriscli; every one of their SKILL.md files starts with a hint that
points here. These checks keep the adapter complete and honest: every command and flag of upstream's doriscli
contract and every doriscli command the copies use is mapped, the tool names are the ones behind the Gateway,
the profile recipe uses parameters the server accepts, the read-only boundary and the 60-second limit are
stated, and nothing that must not leave the repo is in it.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "quick" / "skills"
ADAPTER = SKILLS / "doris-mcp-adapter" / "SKILL.md"
CONTRACT = SKILLS / "CLI-CONTRACT.md"  # copied unmodified from apache/doris-skills (T5.1)
UPSTREAM_SKILLS = ("doris-architecture-advisor", "doris-best-practices", "doris-debug", "doris-profile-reader")
GATEWAY_PREFIX = "doris___"  # <target>___<tool>, design §4.5
DESCRIPTION_LIMIT = 1024  # characters; Quick skills
MAX_CHARS_RANGE = (1000, 200000)  # get_query_profile, mcp-server/src/tools/profile.py
SERVER_SOURCES = ("mcp-server/src/server.py", "mcp-server/src/tools/profile.py")  # where the tools are registered
FE_HTTP_PORT = ":8030"  # how the copies write FE HTTP calls (curl http://$FE:8030/...)


def _text() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def _frontmatter() -> dict:
    match = re.match(r"---\n(.*?)\n---\n", _text(), re.S)
    if match is None:
        raise AssertionError("no YAML frontmatter")
    return yaml.safe_load(match.group(1))


def _section(title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(), re.M | re.S)
    if match is None:
        raise AssertionError(f"no section '## {title}'")
    return match.group(1)


def _words(title: str) -> str:
    """A section with its line breaks and indentation folded to single spaces."""
    return " ".join(_section(title).split())


def _map_rows() -> list[str]:
    """The rows of the command map table, header and rule excluded."""
    return [line for line in _section("doriscli command map").splitlines()
            if line.startswith("| ") and not line.startswith("| The skill says")]


def _has_flag(flag: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is not None


def _contract_commands() -> list[tuple[str | None, list[str]]]:
    """(command, flags) per row of the contract's Commands table; command None for the global flags row."""
    section = re.search(r"^## Commands\n(.*?)(?=^## )", CONTRACT.read_text(encoding="utf-8"), re.M | re.S)
    rows = []
    for line in section.group(1).splitlines():
        if not line.startswith("| ") or line.startswith("| Command"):
            continue
        cell = line.split("|")[1]
        codes = re.findall(r"`([^`]+)`", cell)
        if cell.strip().startswith("global"):
            rows.append((None, [c.split()[0] for c in codes]))
        else:
            rows.append((re.match(r"doriscli(?: [a-z]+)*", codes[0]).group(0), [c.split()[0] for c in codes[1:]]))
    return rows


def _gateway_tools() -> set[str]:
    calls = json.loads((ROOT / "scripts" / "smoke_calls.json").read_text(encoding="utf-8"))
    return {GATEWAY_PREFIX + c["tool"] for c in calls}


def _bullet(title: str, start: str) -> str:
    """The bullet of a section that starts with `start`, folded to single spaces ("" when there is none)."""
    bullets = re.split(r"\n(?=- )", _section(title))
    return next((" ".join(b.split()) for b in bullets if b.startswith(start)), "")


def _server_tools() -> dict[str, tuple[list[str], str]]:
    """Tool name -> (parameter names in order, source of the function) for every tool the server registers:
    the `@mcp.tool(...)` functions of server.py and the `mcp.tool(function, name=...)` calls of tools/profile.py."""
    tools = {}
    for source in SERVER_SOURCES:
        text = (ROOT / source).read_text(encoding="utf-8")
        tree = ast.parse(text)
        functions = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(isinstance(d, ast.Call) and ast.unparse(d.func) == "mcp.tool" for d in node.decorator_list):
                    tools[node.name] = (node, text)
            elif isinstance(node, ast.Call) and ast.unparse(node.func) == "mcp.tool" and node.args:
                name = next(k.value.value for k in node.keywords if k.arg == "name")
                tools[name] = (functions[node.args[0].id], text)
    return {name: ([a.arg for a in f.args.args], ast.get_source_segment(text, f)) for name, (f, text) in tools.items()}


def _fe_http_paths() -> set[str]:
    """Every FE HTTP path the copies call (`...:8030/<path>`), up to `?`, whitespace, a quote or a bracket."""
    used = set()
    for skill in UPSTREAM_SKILLS:
        for path in (SKILLS / skill).rglob("*.md"):
            used.update(re.findall(rf"{re.escape(FE_HTTP_PORT)}(/[^?\s\"'`)]+)", path.read_text(encoding="utf-8")))
    return used


class Frontmatter(unittest.TestCase):
    def test_name_is_the_folder_name(self):
        self.assertEqual(_frontmatter()["name"], ADAPTER.parent.name)

    def test_description_fits_and_names_what_it_is_for(self):
        description = _frontmatter()["description"]
        self.assertLessEqual(len(description), DESCRIPTION_LIMIT)
        for term in (*UPSTREAM_SKILLS, "doriscli", f"{GATEWAY_PREFIX}*", "read-only", "60-second"):
            self.assertIn(term, description)

    def test_the_hint_in_every_copy_names_this_skill(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_skills import HINT  # noqa: E402  (the line T5.1 puts into every copied SKILL.md)
        self.assertIn(f"`{_frontmatter()['name']}`", HINT)


class CommandMap(unittest.TestCase):
    def test_every_contract_command_and_flag_is_mapped(self):
        rows = _map_rows()
        contract = _contract_commands()
        self.assertGreaterEqual(len(contract), 8)
        for command, flags in contract:
            mine = rows if command is None else [r for r in rows if command in r]
            with self.subTest(command=command):
                self.assertTrue(mine, f"{command} is not mapped")
                for flag in flags:
                    self.assertTrue(any(_has_flag(flag, r) for r in mine), f"{command} {flag} is not mapped")

    def test_every_doriscli_command_the_copies_use_is_mapped(self):
        verbs = {"sql", "profile", "tablet", "auth", "use"}
        used = set()
        for skill in UPSTREAM_SKILLS:
            for path in (SKILLS / skill).rglob("*.md"):
                for words in re.findall(r"doriscli ((?:[a-z]+ ?){1,2})", path.read_text(encoding="utf-8")):
                    words = words.split()
                    if words[0] in verbs:
                        used.add(" ".join(words[:2] if words[0] in {"profile", "auth"} else words[:1]))
        self.assertGreaterEqual(used, {"sql", "profile get", "profile list", "profile diff", "profile history",
                                       "tablet", "auth status"})
        rows = "\n".join(_map_rows())
        for command in sorted(used):
            with self.subTest(command=command):
                self.assertIn(command if command.startswith("auth add") else f"doriscli {command}", rows)

    def test_doriscli_tablet_becomes_the_table_statements(self):
        # Track B (doris-best-practices) collects its table evidence with doriscli tablet.
        row = next((r for r in _map_rows() if r.startswith("| `doriscli tablet <db.t>` |")), "")
        for statement in ("SHOW CREATE TABLE", "SHOW PARTITIONS", "SHOW DATA SKEW", "SHOW TABLE STATS"):
            self.assertIn(statement, row)

    def test_set_is_a_hint_not_a_statement(self):
        rows = "\n".join(_map_rows())
        self.assertIn("/*+SET_VAR(k=v)*/", rows)
        self.assertIn("`SET` statements are rejected", rows)

    def test_the_fe_http_paths_the_skills_use_are_mapped(self):
        rows = "\n".join(_map_rows())
        for path, tool in (("/rest/v2/manager/query/query_info", "list_recent_queries"),
                           ("/rest/v2/manager/query/profile/text/", "get_query_profile"),
                           ("/api/query_profile", "get_query_profile")):
            row = next((r for r in _map_rows() if path in r), "")
            self.assertIn(GATEWAY_PREFIX + tool, row, path)
        self.assertIn("any other FE / BE HTTP call", rows)
        # Every FE HTTP path the copies call has a row of its own; the catch-all row is for the rest.
        used = _fe_http_paths()
        self.assertGreaterEqual(used, {"/api/query_profile", "/api/health", "/api/bootstrap", "/api/tablets_distribution"})
        own = [r for r in _map_rows() if "any other FE / BE HTTP call" not in r]
        for path in sorted(used):
            with self.subTest(path=path):
                self.assertTrue(any(path in r for r in own), f"{path} only falls into the catch-all row")
        self.assertNotIn(FE_HTTP_PORT, _text())  # paths only: no host, port or URL

    def test_the_health_check_is_connectivity_only_and_the_version_is_a_variable(self):
        # doriscli auth status also reports the version (CLI-CONTRACT.md); the server's check_service_health only
        # runs SELECT 1 (mcp-server/src/server.py), so the version has to come from a session variable.
        contract = next(line for line in CONTRACT.read_text(encoding="utf-8").splitlines()
                        if line.startswith("| `doriscli auth status` |"))
        self.assertIn("version", contract)
        source = _server_tools()["check_service_health"][1]
        self.assertIn('"SELECT 1"', source)
        self.assertNotRegex(source, r"(?i)version_comment|version\(\)")
        tool = next((r for r in _section("Tools").splitlines() if f"`{GATEWAY_PREFIX}check_service_health()`" in r), "")
        for term in ("`SELECT 1`", "not the Doris version"):
            self.assertIn(term, tool)
        row = next((r for r in _map_rows() if r.startswith("| `doriscli auth status` |")), "")
        self.assertIn("SHOW VARIABLES LIKE 'version_comment'", row)


class ProfileRecipe(unittest.TestCase):
    def test_run_with_a_profile_and_find_it_again(self):
        recipe = _words("Run a query with a profile")
        for term in ("/*+SET_VAR(enable_profile=true)*/", "/* trace:", f"{GATEWAY_PREFIX}list_recent_queries",
                     "sql_contains=", f"{GATEWAY_PREFIX}get_query_profile", "query_id"):
            self.assertIn(term, recipe)

    def test_truncation_full_mode_and_a_missing_profile(self):
        recipe = _words("Run a query with a profile")
        for term in ("truncated: true", "max_chars=60000", 'mode="full"', "profile_found: false"):
            self.assertIn(term, recipe)

    def test_no_matching_row_is_looked_up_once_more_then_reported(self):
        recipe = _words("Run a query with a profile")
        for term in ("If no row matches", "once more", "the profile could not be collected", "do not loop"):
            self.assertIn(term, recipe)

    def test_max_chars_values_are_accepted_by_the_server(self):
        values = [int(v) for v in re.findall(r"max_chars=(\d+)", _text())]
        self.assertTrue(values)
        for value in values:
            self.assertTrue(MAX_CHARS_RANGE[0] <= value <= MAX_CHARS_RANGE[1], value)

    def test_the_profile_text_sections_replace_the_json_fields(self):
        text = _section("doriscli command map")
        for term in ("`Summary:`", "`Execution Summary:`", "`MergedProfile:`", "`PhysicalPlan:`", "profile_text"):
            self.assertIn(term, text)


class Boundaries(unittest.TestCase):
    def test_what_works_and_what_is_denied(self):
        sql = _words("SQL that works and SQL that does not")
        for term in ("SHOW CREATE TABLE", "SHOW DATA SKEW", "SHOW PROCESSLIST", "EXPLAIN",
                     "SHOW TABLETS", "SHOW PROC", "1105", "CONNECTION_ERROR", "try it once", "do not retry"):
            self.assertIn(term, sql)

    def test_processlist_shows_only_the_service_accounts_own_sessions(self):
        # The service account has SELECT only, and Doris shows a user without ADMIN only its own connections.
        bullet = _bullet("SQL that works and SQL that does not", "- `SHOW PROCESSLIST`")
        for term in ("only the service account's own sessions", "other users", "not evidence that nothing is running",
                     "ask the user", "SQL", "query_id"):
            self.assertIn(term, bullet)

    def test_the_tablet_evidence_that_cannot_be_collected_is_named(self):
        denied = _bullet("SQL that works and SQL that does not", "- Denied by Doris")
        for term in ("`SHOW TABLETS`", "replica state", "version counts", "cannot be collected"):
            self.assertIn(term, denied)

    def test_max_rows_does_not_make_a_query_cheaper(self):
        # max_rows only caps the rows fetched from the cursor (mcp-server/src/core/connection.py).
        self.assertIn("fetchmany(_max_rows)", (ROOT / "mcp-server/src/core/connection.py").read_text(encoding="utf-8"))
        row = next((r for r in _map_rows() if r.startswith('| `doriscli sql "<SELECT')), "")
        for term in ("`LIMIT`", "aggregate", "`max_rows` only trims the rows returned", "still runs the whole query"):
            self.assertIn(term, row)

    def test_writes_and_admin_actions_are_handed_to_a_person(self):
        writes = _words("Writes and admin actions")
        never, found, _ = writes.partition("Never run ")[2].partition(". When")  # the list, up to the next sentence
        self.assertTrue(found)
        for term in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE", "KILL", "ADMIN",
                     "SET GLOBAL"):
            self.assertIn(f"`{term}", never)
        self.assertIn("a person runs it", writes)

    def test_the_60_second_limit_and_how_to_stay_under_it(self):
        limit = _words("The 60-second limit")
        for term in ("EXPLAIN", "LIMIT", "424", "retry once"):
            self.assertIn(term, limit)
        self.assertIn("60 s", _words("The environment"))

    def test_evidence_first_and_no_connection_details(self):
        evidence = _words("Evidence first")
        for term in ("tool result", "evidence gates", "host names", "IP addresses", "URLs"):
            self.assertIn(term, evidence)


class Hygiene(unittest.TestCase):
    def test_every_tool_named_exists_behind_the_gateway_and_all_are_listed(self):
        tools = _gateway_tools()
        self.assertEqual(len(tools), 12)
        named = set(re.findall(rf"\b{GATEWAY_PREFIX}\w+", _text()))
        self.assertEqual(named, tools)

    def test_every_tool_name_has_the_gateway_prefix(self):
        bare = {t[len(GATEWAY_PREFIX):] for t in _gateway_tools()}
        text = re.sub(rf"\b{GATEWAY_PREFIX}\w+", "", _text())
        self.assertEqual({t for t in bare if re.search(rf"\b{t}\b", text)}, set())

    def test_the_tool_signatures_follow_the_server(self):
        server = _server_tools()
        self.assertEqual({GATEWAY_PREFIX + t for t in server}, _gateway_tools())
        shown = re.findall(rf"`{GATEWAY_PREFIX}(\w+)\(([^)]*)\)`", _section("Tools"))
        self.assertGreaterEqual(len(shown), 8)
        for tool, params in shown:
            names = [p.split("=")[0].strip() for p in params.split(",") if p.strip()]
            order = server[tool][0]
            with self.subTest(tool=tool):
                self.assertLessEqual(set(names), set(order), names)
                self.assertEqual(names, sorted(names, key=order.index))

    def test_no_urls_addresses_arns_or_account_ids(self):
        text = _text()
        for pattern in (r"https?://", r"\b\d{1,3}(?:\.\d{1,3}){3}\b", r"\barn:aws", r"\b\d{12}\b",
                        r"amazonaws\.com"):
            self.assertIsNone(re.search(pattern, text), pattern)


if __name__ == "__main__":
    unittest.main()
