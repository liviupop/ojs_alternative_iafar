"""Manifest builders for issue/article exports."""

from __future__ import annotations

import datetime

from .config import (
    ISSN,
    JOURNAL_ABBR,
    JOURNAL_DESCRIPTION,
    JOURNAL_NAME,
    JOURNAL_URL,
    PUBLISHER,
)


def build_issue_meta(issue_input: dict, page_count_value: int) -> dict:
    return {
        "id": str(issue_input["id"]),
        "slug": issue_input["slug"],
        "year": issue_input["year"],
        "volume": issue_input["volume"],
        "number": issue_input["number"],
        "date_published": issue_input["date_published"],
        "title": issue_input["title"],
        "status": "published",
        "article_count": 0,
        "pages": page_count_value,
        "doi_prefix": "",
        "publisher": PUBLISHER,
        "issn": ISSN,
        "issue_pdf_path": f"ingest/issues/{issue_input['slug']}/source/issue.pdf",
        "cover_hint_path": f"ingest/issues/{issue_input['slug']}/cover/",
        "page_offset": 0,
    }


def build_global_manifest(issues: list[dict], articles: list[dict]) -> dict:
    return {
        "journal": {
            "name": JOURNAL_NAME,
            "abbr": JOURNAL_ABBR,
            "issn": ISSN,
            "eissn": ISSN,
            "publisher": PUBLISHER,
            "country": "România",
            "language": "ro",
            "url": JOURNAL_URL,
            "description": JOURNAL_DESCRIPTION,
        },
        "issues": issues,
        "articles": articles,
        "generated_at": datetime.datetime.now().isoformat(),
    }
