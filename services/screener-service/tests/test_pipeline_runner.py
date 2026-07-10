from app.jobs.pipeline_runner import submit_pipeline

def test_pipeline_submission_is_idempotent():
    first = submit_pipeline({}, "same-key")
    second = submit_pipeline({}, "same-key")
    assert first.run_id == second.run_id
