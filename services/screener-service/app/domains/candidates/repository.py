"""Candidate persistence boundary.

The stores remain the single database implementation; this module gives
domain consumers one stable import surface while route migration proceeds.
"""

from app import candidate_pool_store, watchlist_store

__all__ = ["candidate_pool_store", "watchlist_store"]
