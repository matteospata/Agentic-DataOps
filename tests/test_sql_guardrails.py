import pytest

from agentic_dataops.policies.sql_guardrails import UnsafeSQL, validate_read_only_sql


def test_select_query_is_allowed() -> None:
    assert validate_read_only_sql("SELECT region, SUM(revenue) FROM sales_demo GROUP BY region")


@pytest.mark.parametrize("query", ["DROP TABLE sales_demo", "DELETE FROM sales_demo", "UPDATE sales_demo SET revenue=0"])
def test_mutating_queries_are_rejected(query: str) -> None:
    with pytest.raises(UnsafeSQL):
        validate_read_only_sql(query)

