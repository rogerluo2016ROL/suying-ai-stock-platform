import asyncio

from app.jobs.pipeline_runner import finish_persisted_pipeline, submit_pipeline, submit_persisted_pipeline

def test_pipeline_submission_is_idempotent():
    first = submit_pipeline({}, "same-key")
    second = submit_pipeline({}, "same-key")
    assert first.run_id == second.run_id


class _Mappings:
    def __init__(self, row): self.row = row
    def first(self): return self.row


class _Result:
    def __init__(self, row=None): self.row = row
    def mappings(self): return _Mappings(self.row)


class _Db:
    def __init__(self): self.calls = []; self.row = None; self.commits = 0
    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result(self.row)
    async def commit(self): self.commits += 1


def test_persisted_pipeline_inserts_and_finishes_run():
    db = _Db()
    async def exercise():
        run = await submit_persisted_pipeline(db, {"mode": "short"}, "persisted-key")
        await finish_persisted_pipeline(db, run.run_id, result={"result_status": "success_no_matches"})
        return run
    run = asyncio.run(exercise())

    assert run.status == "running"
    assert db.commits == 2
    assert "INSERT INTO task_runs" in db.calls[1][0]
    assert db.calls[2][1]["status"] == "succeeded"


def test_persisted_pipeline_reuses_existing_idempotency_key():
    db = _Db(); db.row = {"run_id": "existing", "idempotency_key": "same", "status": "succeeded"}
    run = asyncio.run(submit_persisted_pipeline(db, {}, "same"))

    assert run.run_id == "existing"
    assert run.status == "succeeded"
    assert db.commits == 0
