import threading
import time

from carveracontroller.machine.component_loads import ComponentLoads


def pump(queue, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        if queue:
            queue.pop(0)()
        else:
            time.sleep(0.005)
    assert predicate()


def test_coalescing_is_bounded_and_fixture_vise_lanes_are_independent():
    queue, results = [], []
    loads = ComponentLoads(queue.append)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked():
        entered.set()
        assert release.wait(3)
        calls.append("old")
        return "old"

    loads.submit("fixture", blocked, lambda r, e: results.append(r))
    assert entered.wait(1)
    for number in range(20):
        loads.submit("fixture", lambda n=number: calls.append(n) or n, lambda r, e: results.append(r))
    loads.submit("workholding", lambda: "vise", lambda r, e: results.append(r))
    pump(queue, lambda: "vise" in results)
    assert loads.lanes["fixture"]["active"] and loads.lanes["fixture"]["pending"]
    release.set()
    pump(queue, lambda: 19 in results)
    assert results == ["vise", 19] and calls == ["old", 19]


def test_invalidation_and_close_reject_late_results_and_deliver_errors_on_dispatch_thread():
    queue, results = [], []
    loads = ComponentLoads(queue.append)
    ui = threading.get_ident()
    release, entered = threading.Event(), threading.Event()

    def blocked():
        entered.set()
        assert release.wait(2)
        return "late"

    loads.submit("fixture", blocked, lambda r, e: results.append(r))
    assert entered.wait(1)
    loads.invalidate("fixture")
    release.set()
    pump(queue, lambda: not loads.lanes["fixture"]["active"])
    assert not results

    def failed():
        raise ValueError("bad CAD")

    loads.submit("fixture", failed, lambda r, e: results.append((r, e, threading.get_ident())))
    pump(queue, lambda: bool(results))
    assert results == [(None, "bad CAD", ui)]
    loads.submit("fixture", lambda: "closed", lambda r, e: results.append(r))
    loads.close()
    pump(queue, lambda: not loads.lanes["fixture"]["active"])
    assert len(results) == 1 and not loads.submit("fixture", lambda: None, lambda *_: None)


def test_stock_worker_start_failure_retains_lane_and_allows_a_later_request(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import carveracontroller.machine.component_loads as module

    queue, results = [], []
    loads = ComponentLoads(queue.append)
    original = module.threading.Thread

    def failed_start():
        raise RuntimeError("platform detail")

    monkeypatch.setattr(module.threading, "Thread", lambda **kw: SimpleNamespace(start=failed_start))
    work = Mock()
    assert loads.submit("stock", work, lambda r, e: results.append((r, e)))
    assert not loads.lanes["stock"]["active"]
    assert results == [(None, "Component worker could not start; previous geometry retained")]
    work.assert_not_called()
    monkeypatch.setattr(module.threading, "Thread", original)
    loads.submit("stock", lambda: "new shape", lambda r, e: results.append((r, e)))
    pump(queue, lambda: not loads.lanes["stock"]["active"])
    assert results[-1] == ("new shape", None)
