from carveracontroller.machine.desktop_control_owner import reported_state
from tests.integration import test_backend_job_file as file_fixture
from tests.integration import test_backend_job_run as run_fixture

backend_job = file_fixture.backend_job
backend_run = run_fixture.backend_run


def test_stale_review_cache_gets_one_private_read_before_original_admission_and_journal(backend_run):
    panel, backend, _ws, state, requests, _setup = backend_run
    run = run_fixture.prepare_run(backend_run)
    client = backend.client
    with client._lock:
        client._last_snapshot_at -= 10
    assert reported_state(client.snapshot()) is None
    previous = len(requests)
    run_fixture.start_review(run)
    run_fixture.wait_phase(run, "playing_reported")
    assert [m for m, _p in requests[previous:]].count("operation") == 1
    assert [m for m, _p in requests[previous:]].count("snapshot") >= 2
    assert sum(command.startswith(b"play ") for command in state.wire) == 1
    assert len(run.run.receipts) == 1
