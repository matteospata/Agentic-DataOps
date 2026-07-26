from __future__ import annotations

import re
from pathlib import Path

from ..schemas import KnowledgeResult


class KnowledgeBase:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, limit: int = 4) -> list[KnowledgeResult]:
        terms = {term for term in re.findall(r"[a-zA-Z0-9_]+", query.lower()) if len(term) > 2}
        results: list[KnowledgeResult] = []
        for path in sorted(self.directory.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            tokens = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
            score = len(terms & tokens) / max(len(terms), 1)
            if score > 0:
                title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
                results.append(KnowledgeResult(source=str(path), title=title, text=text, score=round(score, 4)))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

