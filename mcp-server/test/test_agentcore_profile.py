"""P-05: Doris query-profile tools (src/tools/profile.py) against a mocked FE HTTP API.

The mock reproduces Doris 4.1.4 behavior measured in design §4.1: errors are
HTTP 200 + JSON {"code": ...}; v2 profile/text only serves the caller's own
profiles (others -> data: {}); /api/profile/text returns plain text, including
"query id <id> not found" for unknown ids (seen on the demo cluster in T1.8 drafting).
"""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client, FastMCP  # noqa: E402

from tools.profile import (  # noqa: E402
    FeHttpTarget,
    get_query_profile,
    list_recent_queries,
    register_profile_tools,
    summarize_profile,
)

QID = "0123456789abcdef-fedcba9876543210"
OTHER_QID = "aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb"
TARGET = FeHttpTarget("http://fe.test:8030", "mcp_svc", "s3cret-pw")

PROFILE = "\n".join([
    "Summary:",
    f"  - Profile ID: {QID}",
    "  - Task Type: QUERY",
    "  - Workload Group: N/A",
    "Execution Summary:",
    "  - Parse SQL Time: 1ms",
    "  - Plan Time: N/A",
    "ChangedSessionVariables:",
    "MergedProfile:",
    "  Fragments:",
    "    Fragment 0:",
    "      RESULT_SINK_OPERATOR(id=0):",
    "        - ExecTime: 1.2ms",
    "        - MemoryUsage: sum 0.00 , avg 0.00 , max 0.00 , min 0.00 ",
    "        - WaitForDependencyTime: avg 0ns, max 0ns, min 0ns",
    "        - InputRows: sum 0, avg 0, max 7, min 0",
    "        - group by: ",
    f"DetailProfile({QID}):",
    "  Fragments:",
    "    Fragment 0:",
    "      - InstanceId: 1",
    "      - InstanceId: 2",
    "Appendix:",
    "PhysicalPlan:",
    "PhysicalResultSink[182] ( outputExprs=[n#31] )",
    "     PhysicalOlapScan[158]@0 ( table=fact_order, stats=100,240 )",
    "       order_id#0 -> ndv=100201.0000, min=1.000000(1), max=9.000000(9), count=100240.0000",
    "       order_date#1 -> ndv=630.0000, min=20250101000000.000000(2025-01-01)",
    "       __DORIS_DELETE_SIGN__#27 -> unknown(1.0)",
    "     PhysicalFilter[162]@1 ( predicates=(__DORIS_DELETE_SIGN__#27 = 0) )",
])


def _row(qid, user, start, sql, db="ecom"):
    return {
        "Profile ID": qid, "Task Type": "QUERY", "Start Time": start, "End Time": start,
        "Total": "12ms", "Task State": "OK", "User": user, "Default Catalog": "internal",
        "Default Db": db, "Sql Statement": sql, "__hrefPaths": [],
    }


ROWS = [
    _row(OTHER_QID, "root", "2026-09-26 10:00:00", "SELECT 1"),
    _row(QID, "mcp_svc", "2026-09-26 11:00:00", "SELECT /*+SET_VAR(enable_profile=true)*/ 2 /* trace:AbC123 */"),
    _row("cccccccccccccccc-dddddddddddddddd", "mcp_svc", "2026-09-26 09:00:00", "SELECT " + "x, " * 200 + "1"),
]


def _ok(data):
    return httpx.Response(200, json={"msg": "success", "code": 0, "data": data, "count": 0})


class FakeFe:
    """Programmable FE HTTP API; records every request."""

    def __init__(self, v2=None, api_text=None, listing=None):
        self.requests: list[httpx.Request] = []
        self.v2 = v2 or (lambda qid: _ok({}))
        self.api_text = api_text or (lambda qid: httpx.Response(200, text=f"query id {qid} not found"))
        self.listing = listing or (lambda: _ok({"column_names": [], "rows": ROWS}))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/rest/v1/query_profile":
            return self.listing()
        if path.startswith("/rest/v2/manager/query/profile/text/"):
            return self.v2(path.rsplit("/", 1)[1])
        if path == "/api/profile/text":
            return self.api_text(request.url.params.get("query_id"))
        return httpx.Response(404, text="no route")

    def paths(self):
        return [r.url.path for r in self.requests]


def _body(result: str) -> dict:
    return json.loads(result)


class TestListRecentQueries(unittest.IsolatedAsyncioTestCase):
    async def test_newest_first_with_meta(self):
        fe = FakeFe()
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertTrue(body["success"])
        ids = [q["query_id"] for q in body["data"]["queries"]]
        self.assertEqual(ids, [QID, OTHER_QID, "cccccccccccccccc-dddddddddddddddd"])
        self.assertEqual(body["meta"], {"returned": 3, "matched": 3, "source": "/rest/v1/query_profile"})
        first = body["data"]["queries"][0]
        self.assertEqual(
            set(first),
            {"query_id", "user", "default_db", "task_type", "state", "start_time", "end_time", "total", "sql"},
        )
        self.assertEqual(body["data"]["scope"], "all")

    async def test_sql_preview_is_capped_at_200_chars(self):
        body = _body(await list_recent_queries(TARGET, transport=FakeFe().transport()))
        self.assertTrue(all(len(q["sql"]) <= 200 for q in body["data"]["queries"]))

    async def test_filters_and_limit(self):
        fe = FakeFe()
        body = _body(await list_recent_queries(TARGET, limit=1, user="mcp_svc", transport=fe.transport()))
        self.assertEqual([q["query_id"] for q in body["data"]["queries"]], [QID])
        self.assertEqual(body["meta"]["matched"], 2)
        body = _body(await list_recent_queries(TARGET, sql_contains="abc123", transport=fe.transport()))
        self.assertEqual([q["query_id"] for q in body["data"]["queries"]], [QID])

    async def test_scope_self_forces_own_user(self):
        body = _body(await list_recent_queries(TARGET, user="root", scope="self", transport=FakeFe().transport()))
        self.assertEqual({q["user"] for q in body["data"]["queries"]}, {"mcp_svc"})
        self.assertEqual(body["data"]["scope"], "self")

    async def test_limit_out_of_range_makes_no_request(self):
        for limit in (0, 101):
            fe = FakeFe()
            body = _body(await list_recent_queries(TARGET, limit=limit, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS")
            self.assertEqual(fe.requests, [])

    async def test_sends_basic_auth(self):
        fe = FakeFe()
        await list_recent_queries(TARGET, transport=fe.transport())
        expected = "Basic " + base64.b64encode(b"mcp_svc:s3cret-pw").decode()
        self.assertEqual(fe.requests[0].headers["authorization"], expected)

    async def test_body_code_401_is_unauthenticated(self):
        fe = FakeFe(listing=lambda: httpx.Response(
            200, json={"msg": "Unauthorized", "code": 401, "data": "Access denied for mcp_svc"}))
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")
        self.assertNotIn("s3cret-pw", json.dumps(body))

    async def test_http_401_is_unauthenticated(self):
        fe = FakeFe(listing=lambda: httpx.Response(401, text="denied"))
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")

    async def test_http_500_and_non_json_are_connection_errors(self):
        for resp in (httpx.Response(500, text="boom"), httpx.Response(200, text="<html>")):
            fe = FakeFe(listing=lambda resp=resp: resp)
            body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")

    async def test_timeout_and_connect_errors(self):
        def raise_timeout(request):
            raise httpx.ReadTimeout("slow", request=request)

        def raise_connect(request):
            raise httpx.ConnectError("refused", request=request)

        for handler, code in ((raise_timeout, "QUERY_TIMEOUT"), (raise_connect, "CONNECTION_ERROR")):
            body = _body(await list_recent_queries(TARGET, transport=httpx.MockTransport(handler)))
            self.assertEqual(body["error"]["code"], code)
            self.assertNotIn("s3cret-pw", json.dumps(body))


class TestGetQueryProfile(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_query_ids_make_no_request(self):
        for qid in ("", "abc", "../../api/x", QID + "/../x", "0123456789abcdeg-fedcba9876543210",
                    "0123456789abcdef0-1", "1-0123456789abcdef0", "-1", "1-", "-", "1-2-3",
                    "g-1", "1-g", "1 -2", "1/-2", "1-/2"):
            fe = FakeFe()
            body = _body(await get_query_profile(TARGET, qid, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS", qid)
            self.assertEqual(fe.requests, [])

    async def test_unpadded_query_ids_reach_the_fe(self):
        # Doris prints each half with Long.toHexString, so a leading zero nibble is dropped.
        for raw, qid in (("4f3c29918764dfc-b03a971ce0467326", "4f3c29918764dfc-b03a971ce0467326"),
                         ("b03a971ce0467326-4f3c29918764dfc", "b03a971ce0467326-4f3c29918764dfc"),
                         ("0-1", "0-1"),
                         ("A-B", "a-b")):
            with self.subTest(query_id=raw):
                fe = FakeFe(api_text=lambda q: httpx.Response(200, text=PROFILE))
                body = _body(await get_query_profile(TARGET, raw, transport=fe.transport()))
                self.assertTrue(body.get("success"), body)
                self.assertEqual((body["data"]["query_id"], body["data"]["source"]), (qid, "api_text"))
                self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{qid}", "/api/profile/text"])
                self.assertEqual(fe.requests[1].url.params["query_id"], qid)

    async def test_invalid_mode_and_max_chars(self):
        fe = FakeFe()
        for kwargs in ({"mode": "brief"}, {"max_chars": 999}, {"max_chars": 200001}):
            body = _body(await get_query_profile(TARGET, QID, transport=fe.transport(), **kwargs))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS", kwargs)
        self.assertEqual(fe.requests, [])

    async def test_v2_hit_returns_summary(self):
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        body = _body(await get_query_profile(TARGET, f"  {QID.upper()} ", transport=fe.transport()))
        data = body["data"]
        self.assertTrue(data["profile_found"])
        self.assertEqual((data["query_id"], data["source"], data["mode"]), (QID, "v2", "summary"))
        self.assertEqual(data["total_chars"], len(PROFILE))
        self.assertFalse(data["truncated"])
        self.assertEqual(data["returned_chars"], len(data["profile_text"]))
        self.assertNotIn("InstanceId", data["profile_text"])
        self.assertIn("ExecTime", data["profile_text"])
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}"])

    async def test_profile_text_is_masked_like_the_sql_preview(self):
        # The profile repeats the whole SQL, which can span lines; list_recent_queries masks its preview.
        text = PROFILE.replace("  - Task Type: QUERY",
                               "  - Sql Statement: SELECT 1\nFROM t WHERE password = 'hunter2-pw'\n  - Task Type: QUERY")
        cases = (("summary", "v2", FakeFe(v2=lambda qid: _ok({"profile": text}))),
                 ("full", "api_text", FakeFe(api_text=lambda qid: httpx.Response(200, text=text))))
        for mode, source, fe in cases:
            with self.subTest(mode=mode):
                data = _body(await get_query_profile(TARGET, QID, mode=mode, transport=fe.transport()))["data"]
                self.assertEqual(data["source"], source)
                self.assertIn("FROM t WHERE password = '****'", data["profile_text"])
                self.assertNotIn("hunter2-pw", data["profile_text"])

    async def test_full_mode_returns_everything(self):
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        data = _body(await get_query_profile(TARGET, QID, mode="full", transport=fe.transport()))["data"]
        self.assertEqual(data["profile_text"], PROFILE)

    async def test_falls_back_to_api_text_for_other_users_profiles(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, text=PROFILE, headers={"content-type": "text/plain"}))
        data = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))["data"]
        self.assertTrue(data["profile_found"])
        self.assertEqual(data["source"], "api_text")
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}", "/api/profile/text"])
        self.assertEqual(fe.requests[1].url.params["query_id"], QID)

    async def test_scope_self_never_uses_api_text(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, text=PROFILE))
        body = _body(await get_query_profile(TARGET, QID, scope="self", transport=fe.transport()))
        self.assertFalse(body["data"]["profile_found"])
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}"])

    async def test_not_found_is_evidence_not_error(self):
        fe = FakeFe()
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], {"query_id": QID, "profile_found": False})
        self.assertIn("enable_profile", body["meta"]["hint"])
        self.assertEqual(body["meta"]["evidence"]["v2"]["code"], 0)
        self.assertEqual(body["meta"]["evidence"]["api_text"], {"code": None, "msg": f"query id {QID} not found"})

    async def test_api_text_json_error_is_not_found(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, json={"msg": "Invalid profile id", "code": 500}))
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertFalse(body["data"]["profile_found"])
        self.assertEqual(body["meta"]["evidence"]["api_text"], {"code": 500, "msg": "Invalid profile id"})

    async def test_api_text_must_start_with_a_section_to_count_as_a_profile(self):
        for text in ("", "   ", "profile is not ready yet", "<html>error</html>"):
            fe = FakeFe(api_text=lambda qid, text=text: httpx.Response(200, text=text))
            body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
            self.assertFalse(body["data"]["profile_found"], repr(text))

    async def test_truncation(self):
        long_profile = "Summary:\n" + "\n".join(f"  - Counter{i}: {i}" for i in range(1, 501))
        fe = FakeFe(v2=lambda qid: _ok({"profile": long_profile}))
        data = _body(await get_query_profile(TARGET, QID, max_chars=1000, transport=fe.transport()))["data"]
        self.assertTrue(data["truncated"])
        self.assertEqual(data["returned_chars"], 1000)
        self.assertTrue(data["profile_text"].startswith(long_profile[:1000]))
        self.assertIn("truncated", data["profile_text"][1000:])

    async def test_v2_unauthorized(self):
        fe = FakeFe(v2=lambda qid: httpx.Response(200, json={"msg": "Unauthorized", "code": 401, "data": "x"}))
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")
        self.assertEqual(len(fe.requests), 1)


class TestSummarizeProfile(unittest.TestCase):
    def test_drops_detail_profile_and_na_lines(self):
        summary = summarize_profile(PROFILE)
        lines = summary.splitlines()
        self.assertIn(f"DetailProfile({QID}):", lines)
        self.assertIn("  [4 lines omitted; use mode='full' for per-instance detail]", lines)
        self.assertNotIn("InstanceId", summary)
        self.assertNotIn(": N/A", summary)
        for kept in ("Summary:", "Execution Summary:", "MergedProfile:", "Appendix:", "PhysicalPlan:"):
            self.assertIn(kept, lines)

    def test_drops_all_zero_counters_only(self):
        lines = summarize_profile(PROFILE).splitlines()
        self.assertNotIn("        - MemoryUsage: sum 0.00 , avg 0.00 , max 0.00 , min 0.00 ", lines)
        self.assertNotIn("        - WaitForDependencyTime: avg 0ns, max 0ns, min 0ns", lines)
        self.assertIn("        - InputRows: sum 0, avg 0, max 7, min 0", lines)
        self.assertIn("        - group by: ", lines)
        self.assertIn("        - ExecTime: 1.2ms", lines)

    def test_collapses_plan_column_statistics(self):
        lines = summarize_profile(PROFILE).splitlines()
        self.assertEqual(lines[-4:], [
            "PhysicalResultSink[182] ( outputExprs=[n#31] )",
            "     PhysicalOlapScan[158]@0 ( table=fact_order, stats=100,240 )",
            "       [3 column-statistics lines omitted; use mode='full' for column statistics]",
            "     PhysicalFilter[162]@1 ( predicates=(__DORIS_DELETE_SIGN__#27 = 0) )",
        ])

    def test_detail_profile_at_end(self):
        text = "Summary:\n  - A: 1\nDetailProfile(x):\n  - B: 2\n  - C: 3"
        self.assertEqual(
            summarize_profile(text),
            "Summary:\n  - A: 1\nDetailProfile(x):\n  [2 lines omitted; use mode='full' for per-instance detail]",
        )

    def test_text_without_sections_is_kept(self):
        self.assertEqual(summarize_profile("plain line\n  - X: 1"), "plain line\n  - X: 1")


class TestFeHttpTarget(unittest.TestCase):
    def test_repr_hides_password(self):
        self.assertNotIn("s3cret-pw", repr(TARGET))


class TestRegisterProfileTools(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_registered_read_only_and_audited(self):
        mcp = FastMCP("t")
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        register_profile_tools(mcp, TARGET, scope="all", transport=fe.transport())
        for name in ("list_recent_queries", "get_query_profile"):
            tool = await mcp.get_tool(name)
            self.assertTrue(tool.annotations.readOnlyHint, name)
            self.assertFalse(tool.annotations.destructiveHint, name)
        with patch("tools.profile.log_tool_call") as audit:
            async with Client(mcp) as client:
                result = await client.call_tool("get_query_profile", {"query_id": QID})
        self.assertTrue(json.loads(result.content[0].text)["data"]["profile_found"])
        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], "get_query_profile")
        self.assertTrue(audit.call_args.kwargs["success"])

    async def test_mode_is_an_enum_in_the_schema(self):
        mcp = FastMCP("t")
        register_profile_tools(mcp, TARGET)
        tool = await mcp.get_tool("get_query_profile")
        self.assertEqual(sorted(tool.parameters["properties"]["mode"]["enum"]), ["full", "summary"])
        self.assertEqual(tool.parameters["required"], ["query_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
