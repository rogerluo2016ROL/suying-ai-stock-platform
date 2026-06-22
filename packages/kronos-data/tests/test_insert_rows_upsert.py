"""ADR-015.0 SIT: `_insert_rows` UPSERT 扩展验证.

测试用例:
1. nothing (默认) 行为零变化 — ON CONFLICT DO NOTHING
2. update 成功路径 — ON CONFLICT (c) DO UPDATE SET cols=EXCLUDED.cols 真实写库
3. update 缺 conflict_cols 必须 raise ValueError
4. update 缺 update_cols 必须 raise ValueError
5. update_cols ∩ conflict_cols ≠ ∅ 必须 raise ValueError
6. update_cols 含审计列 (created_at/updated_at) 必须 raise ValueError
7. update_cols ⊄ columns 必须 raise ValueError
8. conflict_action 非法值必须 raise ValueError

PG 不可用时整文件 skip (pytest.importorskip + 连接探测).
"""

import os
import sys
import pytest

# 注入 kronos-data 模块路径 (与 etl.py 同 repo)
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # packages/kronos-data
sys.path.insert(0, _PKG_ROOT)

psycopg2 = pytest.importorskip("psycopg2")

_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(_PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(),
                                reason="PG 不可用 (KRONOS_PG_URL 连不上)")


@pytest.fixture
def pg_conn():
    """临时表 fixture: 创建 t_adr015_upsert (id PK, name, value, created_at) + setup/teardown."""
    conn = psycopg2.connect(_PG_URL)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS t_adr015_upsert")
    cur.execute("""
        CREATE TABLE t_adr015_upsert (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        )
    """)
    conn.commit()
    yield conn
    cur.execute("DROP TABLE IF EXISTS t_adr015_upsert")
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture
def db_wrapper(pg_conn):
    """构造与 _insert_rows 兼容的 _Db 包装 (沿用 etl.py 内部约定 _pg/_conn 属性)."""
    from kronos_data.etl import _Db
    db = _Db.__new__(_Db)
    db._pg = True
    db._conn = pg_conn
    db._cur = pg_conn.cursor()
    # _Db 的 commit/rollback 走 _conn
    db.commit = pg_conn.commit
    db.rollback = pg_conn.rollback
    return db


def test_nothing_default_behavior_zero_regression(db_wrapper, pg_conn):
    """用例 1: conflict_action="nothing" (默认) 与旧版行为字面一致 — DO NOTHING."""
    from kronos_data.etl import _insert_rows

    cur = pg_conn.cursor()
    # 第一次插入
    written = _insert_rows(db_wrapper, "t_adr015_upsert",
                           ["id", "name", "value"],
                           [(1, "alice", 10)])
    assert written == 1
    # 第二次冲突 (id=1 同 PK), DO NOTHING → 写 0 行, value 不变
    written = _insert_rows(db_wrapper, "t_adr015_upsert",
                           ["id", "name", "value"],
                           [(1, "alice_v2", 999)])
    assert written == 0
    cur.execute("SELECT name, value FROM t_adr015_upsert WHERE id = 1")
    row = cur.fetchone()
    assert row == ("alice", 10), "DO NOTHING 后 name/value 应保持首次插入值"


def test_update_action_real_upsert(db_wrapper, pg_conn):
    """用例 2: conflict_action="update" 真实 UPSERT — DO UPDATE SET 列被刷新."""
    from kronos_data.etl import _insert_rows

    cur = pg_conn.cursor()
    # 首次插入
    written = _insert_rows(db_wrapper, "t_adr015_upsert",
                           ["id", "name", "value"],
                           [(2, "bob", 20)])
    assert written == 1
    # 冲突时 UPDATE name 和 value
    written = _insert_rows(db_wrapper, "t_adr015_upsert",
                           ["id", "name", "value"],
                           [(2, "bob_v2", 200)],
                           conflict_action="update",
                           conflict_cols=["id"],
                           update_cols=["name", "value"])
    # rowcount: UPSERT 时 PG 报 1 (更新算 1 行影响)
    assert written == 1
    cur.execute("SELECT name, value FROM t_adr015_upsert WHERE id = 2")
    row = cur.fetchone()
    assert row == ("bob_v2", 200), f"UPSERT 后 name/value 应被刷新, 实际 {row}"


def test_update_action_partial_update_cols(db_wrapper, pg_conn):
    """用例 2.bis: update_cols 只指定部分列, 未指定列不变."""
    from kronos_data.etl import _insert_rows

    cur = pg_conn.cursor()
    _insert_rows(db_wrapper, "t_adr015_upsert",
                 ["id", "name", "value"],
                 [(3, "carol", 30)])
    # 只更新 name, value 应保持 30
    _insert_rows(db_wrapper, "t_adr015_upsert",
                 ["id", "name", "value"],
                 [(3, "carol_v2", 999)],
                 conflict_action="update",
                 conflict_cols=["id"],
                 update_cols=["name"])
    cur.execute("SELECT name, value FROM t_adr015_upsert WHERE id = 3")
    row = cur.fetchone()
    assert row == ("carol_v2", 30), f"只 UPDATE name, value 应保持 30, 实际 {row}"


def test_update_missing_conflict_cols_raises(db_wrapper):
    """用例 3: conflict_action="update" 但 conflict_cols=None 必须 raise."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="conflict_cols"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(4, "x", 1)],
                     conflict_action="update",
                     conflict_cols=None,
                     update_cols=["name"])


def test_update_missing_update_cols_raises(db_wrapper):
    """用例 4: conflict_action="update" 但 update_cols=None 必须 raise."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="update_cols"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(5, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=None)


def test_update_cols_overlap_conflict_cols_raises(db_wrapper):
    """用例 5: update_cols ∩ conflict_cols ≠ ∅ 必须 raise (PK 列 SET 反模式)."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="overlap"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(6, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["id", "name"])


def test_update_cols_contains_audit_col_raises(db_wrapper):
    """用例 6: update_cols 含 created_at / updated_at 必须 raise (审计列黑名单)."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="audit cols"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "created_at"],
                     [(7, "x", "2026-01-01")],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["name", "created_at"])


def test_update_cols_not_subset_of_columns_raises(db_wrapper):
    """用例 7: update_cols ⊄ columns 必须 raise."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="subset"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(8, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["nonexistent_col"])


def test_invalid_conflict_action_raises(db_wrapper):
    """用例 8: conflict_action 非法值必须 raise."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="conflict_action"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(9, "x", 1)],
                     conflict_action="replace")  # 非 nothing/update


# ── ADR-015.0 minor amend (2026-06-22): now_cols 测试 ──

def test_now_cols_refreshes_updated_at(db_wrapper, pg_conn):
    """用例 10: now_cols=["updated_at"] → INSERT + DO UPDATE SET 都用 NOW() 真实刷新."""
    from kronos_data.etl import _insert_rows
    import time as _time

    cur = pg_conn.cursor()
    # 首次 UPSERT (无冲突, 走 INSERT): now_cols 追加 updated_at=NOW() 到 INSERT VALUES
    _insert_rows(db_wrapper, "t_adr015_upsert",
                 ["id", "name", "value"],
                 [(10, "dave", 100)],
                 conflict_action="update",
                 conflict_cols=["id"],
                 update_cols=["name"],
                 now_cols=["updated_at"])
    cur.execute("SELECT updated_at FROM t_adr015_upsert WHERE id = 10")
    ts1 = cur.fetchone()[0]
    assert ts1 is not None, "首次 INSERT 时 now_cols=[updated_at] 应写入 NOW()"
    # 等 1.1s 确保 NOW() 有可见差异
    _time.sleep(1.1)
    # 第二次 UPSERT (冲突): DO UPDATE SET updated_at=NOW() 刷新
    _insert_rows(db_wrapper, "t_adr015_upsert",
                 ["id", "name", "value"],
                 [(10, "dave", 100)],
                 conflict_action="update",
                 conflict_cols=["id"],
                 update_cols=["name"],
                 now_cols=["updated_at"])
    cur.execute("SELECT updated_at FROM t_adr015_upsert WHERE id = 10")
    ts2 = cur.fetchone()[0]
    assert ts2 > ts1, f"now_cols=[updated_at] 应刷新时间, ts1={ts1} ts2={ts2}"


def test_now_cols_overlap_update_cols_raises(db_wrapper):
    """用例 11: now_cols ∩ update_cols ≠ ∅ 必须 raise.

    注: update_cols ⊆ columns (约束 4), 所以 now_cols ∩ update_cols ≠ ∅ 时
    now_cols ∩ columns ≠ ∅ 先触发. 这里验证拒绝重叠列 (无论哪个约束先命中).
    """
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="now_cols must NOT overlap"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(11, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["name", "value"],
                     now_cols=["value"])  # value 既在 update_cols 又在 columns


def test_now_cols_not_subset_of_columns_raises(db_wrapper):
    """用例 12: now_cols ∩ columns ≠ ∅ 必须 raise (now_cols 是独立追加列, 不能与业务列重复)."""
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="now_cols must NOT overlap columns"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(12, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["name"],
                     now_cols=["value"])  # value 已在 columns 里, 冲突


def test_now_cols_overlap_conflict_cols_raises(db_wrapper):
    """用例 13: now_cols ∩ conflict_cols ≠ ∅ 必须 raise (PK 列 NOW() 反模式).

    注: conflict_cols 通常 ⊆ columns (PK 在业务列里), 所以先触发 columns overlap.
    这里验证拒绝 PK 列走 NOW().
    """
    from kronos_data.etl import _insert_rows

    with pytest.raises(ValueError, match="now_cols must NOT overlap"):
        _insert_rows(db_wrapper, "t_adr015_upsert",
                     ["id", "name", "value"],
                     [(13, "x", 1)],
                     conflict_action="update",
                     conflict_cols=["id"],
                     update_cols=["name"],
                     now_cols=["id"])


def test_now_cols_ignored_when_nothing_action(db_wrapper, pg_conn):
    """用例 14: conflict_action="nothing" 时 now_cols 被忽略 (不报错, 也不生效)."""
    from kronos_data.etl import _insert_rows

    cur = pg_conn.cursor()
    # nothing + now_cols 传了, 但不生效 → DO NOTHING, 不 raise
    written = _insert_rows(db_wrapper, "t_adr015_upsert",
                           ["id", "name", "value"],
                           [(14, "eve", 1)],
                           conflict_action="nothing",
                           now_cols=["updated_at"])  # ignored
    assert written == 1
    cur.execute("SELECT name FROM t_adr015_upsert WHERE id = 14")
    assert cur.fetchone()[0] == "eve"
