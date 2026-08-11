from packages.bot.queries import PipelineOverview
from packages.bot.tools import TOOL_SCHEMAS, dispatch_tool, result_to_json
from tests.test_bot_stats import make_incident


class FakeQueries:
    def __init__(self, incidents=None):
        self.incidents = incidents if incidents is not None else [make_incident()]

    def latest(self, n=5):
        return self.incidents[:n]

    def search_victim(self, name):
        return [i for i in self.incidents if name.lower() in i.victim_name.lower()]

    def group_profile(self, name):
        victims = [i for i in self.incidents if name.lower() in (i.group_name or "")]
        return (victims[0].group_name if victims else name, victims)

    def all_incidents(self):
        return self.incidents

    def pipeline_overview(self):
        return PipelineOverview(
            companies_hit=2,
            by_status={"not_contacted": 1, "contacted": 1},
            rows=[],
        )


def test_tool_schemas_have_unique_names_and_valid_shape():
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))
    for t in TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert "description" in t["function"]
        assert t["function"]["parameters"]["type"] == "object"


def test_dispatch_latest_includes_source_urls():
    result = dispatch_tool("get_latest_incidents", {"n": 5}, FakeQueries())
    assert result["count"] == 1
    assert result["incidents"][0]["source_url"] == "https://example.com/v/1"


def test_dispatch_search_victim_no_match_returns_zero_not_error():
    result = dispatch_tool("search_victim", {"name": "Nonexistent Corp"}, FakeQueries())
    assert result == {"count": 0, "incidents": []}


def test_dispatch_group_profile():
    result = dispatch_tool("get_group_profile", {"name": "lockbit"}, FakeQueries())
    assert result["group"] == "lockbit"
    assert result["count"] == 1


def test_dispatch_stats_aggregates():
    result = dispatch_tool("get_stats", {"period": "90d"}, FakeQueries())
    assert result["total"] == 1
    assert result["by_group"] == [("lockbit", 1)]
    assert len(result["by_day"]) == 90


def test_dispatch_brief_returns_bullets():
    result = dispatch_tool("get_brief", {"topic": "", "period": "90d"}, FakeQueries())
    assert 1 <= len(result["bullets"]) <= 5


def test_dispatch_pipeline_funnel():
    result = dispatch_tool("get_pipeline", {}, FakeQueries())
    assert result["companies_hit"] == 2
    assert "2 watchlist companies hit" in result["funnel"]


def test_dispatch_unknown_tool_returns_error():
    result = dispatch_tool("drop_table", {}, FakeQueries())
    assert "error" in result


def test_dispatch_tool_exception_is_captured_not_raised():
    class BrokenQueries(FakeQueries):
        def latest(self, n=5):
            raise RuntimeError("db down")

    result = dispatch_tool("get_latest_incidents", {}, BrokenQueries())
    assert "db down" in result["error"]


def test_result_to_json_serializes():
    assert '"count": 0' in result_to_json({"count": 0})
