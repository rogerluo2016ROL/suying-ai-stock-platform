"""Candidate-pool domain rules independent of HTTP routing."""


def resolve_candidate_pool_scope(*, data_scope: str, visibility: str, account_id: str | None, owner_user_id: str | None) -> tuple[str, str]:
    scope = data_scope or ("account" if (account_id or owner_user_id) else "public")
    resolved_visibility = "public" if scope == "public" else (
        visibility if visibility in ("private", "tenant_shared", "public") else "private"
    )
    return scope, resolved_visibility


def build_candidate_pool_id(*, source_mode: str, trade_date: str, time_slot: str, account_id: str | None, owner_user_id: str | None) -> str:
    scope_key = account_id or owner_user_id or "public"
    return f"POOL-{source_mode}-{trade_date}-{time_slot.replace(':', '')}-{scope_key}"
