"""Two independently coalesced component preparation lanes; no widget access."""

import threading


class ComponentLoads:
    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.closed = False
        self.lanes = {kind: {"generation": 0, "active": False, "pending": None} for kind in ("fixture", "workholding")}

    def invalidate(self, kind):
        lane = self.lanes[kind]
        lane["generation"] += 1
        lane["pending"] = None

    def close(self):
        self.closed = True
        for kind in self.lanes:
            self.invalidate(kind)

    def submit(self, kind, work, finish):
        lane = self.lanes[kind]
        if self.closed:
            return False
        lane["generation"] += 1
        request = (lane["generation"], work, finish)
        if lane["active"]:
            lane["pending"] = request
        else:
            self._start(kind, request)
        return True

    def _start(self, kind, request):
        generation, work, finish = request
        lane = self.lanes[kind]
        lane["active"] = True

        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)

            def publish():
                lane["active"] = False
                pending, lane["pending"] = lane["pending"], None
                if self.closed:
                    return
                if pending is not None:
                    self._start(kind, pending)
                    return
                if generation == lane["generation"]:
                    finish(result, error)

            self.dispatch(publish)

        threading.Thread(target=worker, name="component-prepare-" + kind, daemon=True).start()
