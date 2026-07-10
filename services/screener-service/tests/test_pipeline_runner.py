import asyncio
from app.jobs.pipeline_runner import submit_pipeline, get_pipeline_run

def test_pipeline_runner_is_idempotent():
    async def worker(payload):
        return {"ok": payload["mode"]}
    async def scenario():
        one = submit_pipeline({"mode": "short"}, "key-1", worker)
        two = submit_pipeline({"mode": "short"}, "key-1", worker)
        assert one == two
        await asyncio.sleep(0)
        assert get_pipeline_run(one)["status"] == "completed"
    asyncio.run(scenario())
