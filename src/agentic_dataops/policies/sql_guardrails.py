from __future__ import annotations

import re


class UnsafeSQL(ValueError):
    """Raised when a query is not safe for the read-only execution tool."""


FORBIDDEN_KEYWORDS = {
    "attach", "create", "delete", "detach", "drop", "export", "insert", "load",
    "pragma", "replace", "update", "vacuum", "writefile",
}


def validate_read_only_sql(query: str) -> str:
    normalized = re.sub(r"--.*?$|/\*.*?\*/", " ", query, flags=re.MULTILINE | re.DOTALL).strip()
    if not normalized:
        raise UnsafeSQL("SQL query cannot be empty")
    if normalized.count(";") > 1 or (";" in normalized and not normalized.endswith(";")):
        raise UnsafeSQL("Only one SQL statement is allowed")
    statement = normalized.rstrip(";").strip()
    if not re.match(r"^(select|with)\b", statement, flags=re.IGNORECASE):
        raise UnsafeSQL("Only SELECT and WITH queries are allowed")
    keywords = set(re.findall(r"\b[a-z]+\b", statement.lower()))
    forbidden = sorted(keywords & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise UnsafeSQL(f"Forbidden SQL keyword(s): {', '.join(forbidden)}")
    return statement

