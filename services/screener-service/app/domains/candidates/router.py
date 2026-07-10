"""Candidate route compatibility exports.

The active routes are registered by the shared Screener contract router to
avoid changing public paths during extraction.
"""

from app.domains.screening.service import (
    add_watchlist,
    list_watchlist,
    query_candidate_pool,
    record_candidate_pool,
    remove_watchlist,
)

__all__ = [
    "add_watchlist",
    "list_watchlist",
    "query_candidate_pool",
    "record_candidate_pool",
    "remove_watchlist",
]
