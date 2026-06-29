from app.plan_store import PlanStore


def test_plan_store_filters_private_plans_by_tenant_and_owner():
    store = PlanStore()
    mine = store.create(
        name="我的方案",
        picks=[],
        tenant_id="tenant-a",
        owner_user_id="7",
        account_id="paper-u7",
    )
    store.create(
        name="别人的方案",
        picks=[],
        tenant_id="tenant-a",
        owner_user_id="8",
        account_id="paper-u8",
    )
    store.create(
        name="其他租户",
        picks=[],
        tenant_id="tenant-b",
        owner_user_id="7",
        account_id="paper-u7",
    )

    visible = store.list_for_scope(
        tenant_id="tenant-a",
        owner_user_id="7",
        account_id="paper-u7",
    )

    assert [plan.id for plan in visible] == [mine.id]


def test_plan_store_allows_tenant_shared_plans_for_same_tenant():
    store = PlanStore()
    shared = store.create(
        name="租户共享方案",
        picks=[],
        tenant_id="tenant-a",
        owner_user_id="8",
        visibility="tenant_shared",
        data_scope="tenant",
    )

    visible = store.list_for_scope(
        tenant_id="tenant-a",
        owner_user_id="7",
        account_id="paper-u7",
    )

    assert [plan.id for plan in visible] == [shared.id]


def test_plan_store_preserves_candidate_snapshot_fields():
    store = PlanStore()
    plan = store.create(
        name="候选快照方案",
        picks=[
            {
                "candidate_id": "CAND-leader_auction-300750",
                "code": "300750",
                "source_module": "screener",
                "source_mode": "leader_auction",
                "visibility": "public",
                "data_scope": "public",
            },
        ],
        tenant_id="tenant-a",
        owner_user_id="7",
        account_id="paper-u7",
    )

    assert plan.picks[0]["candidate_id"] == "CAND-leader_auction-300750"
    assert plan.picks[0]["source_module"] == "screener"
    assert plan.picks[0]["data_scope"] == "public"
