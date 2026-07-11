"""Persistent storage for evaluated data-readiness snapshots."""

import json
import os
import uuid


def _connect():
    import psycopg2

    return psycopg2.connect(
        os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
        ),
        connect_timeout=5,
    )


def save(snapshot):
    payload = snapshot.to_dict()
    snapshot_id = uuid.uuid4().hex
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO data_readiness_snapshots(
                    snapshot_id, profile, target_trade_date, cutoff_time, status, sources
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    snapshot_id,
                    payload["profile"],
                    payload["target_trade_date"],
                    payload.get("cutoff_time"),
                    payload["status"],
                    json.dumps(payload.get("sources") or [], ensure_ascii=False),
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return {**payload, "snapshot_id": snapshot_id}


def get(snapshot_id):
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshot_id, profile, target_trade_date, cutoff_time, status, sources
                FROM data_readiness_snapshots
                WHERE snapshot_id = %s
                """,
                (snapshot_id,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {
        "snapshot_id": row[0],
        "profile": row[1],
        "target_trade_date": str(row[2]),
        "cutoff_time": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
        "status": row[4],
        "sources": row[5],
    }
