from app.excel.busy import ExcelBusy
from app.excel.reads import ReadScheduler


class Rig:
    """A fake COM thread: timers wait in a list until the test runs them."""

    def __init__(self, busy_times=0, error_times=0):
        self.timers: list[tuple[float, object]] = []
        self.now = 0
        self.busy_left = busy_times
        self.error_left = error_times
        self.reads_started = 0
        self.delivered = []
        self.during_read = None   # called inside a read, to simulate events arriving then
        self.s = ReadScheduler(lambda d, fn: self.timers.append((d, fn)), self.read,
                               self.delivered.append, clock=lambda: self.now)

    def read(self):
        self.reads_started += 1
        if self.during_read:
            hook, self.during_read = self.during_read, None
            hook()
        if self.busy_left:
            self.busy_left -= 1
            raise ExcelBusy("busy")
        if self.error_left:
            self.error_left -= 1
            raise RuntimeError("odd")
        return f"snap{self.reads_started}"

    def run_next(self, advance_ns=0):
        delay, fn = self.timers.pop(0)
        self.now += advance_ns
        fn()
        return delay


def test_a_burst_of_events_is_one_read():
    r = Rig()
    for _ in range(5):
        r.s.changed()
    assert len(r.timers) == 1
    r.run_next()
    assert r.delivered == ["snap1"] and r.s.events == 5 and r.s.reads == 1
    assert r.s.idle and not r.timers


def test_busy_retries_back_off_and_never_give_up():
    r = Rig(busy_times=9)
    r.s.changed()
    delays = [r.run_next() for _ in range(10)]
    assert delays[0] == 0.0
    assert delays[1:5] == [0.02, 0.04, 0.08, 0.16]
    assert delays[5:] == [0.25] * 5
    assert r.delivered == ["snap10"] and r.s.busy_retries == 9 and r.s.idle


def test_other_failures_are_retried_and_recorded():
    r = Rig(error_times=2)
    r.s.changed()
    for _ in range(3):
        r.run_next()
    assert r.delivered == ["snap3"] and r.s.error_count == 2 and len(r.s.errors) == 2


def test_a_change_during_a_read_gets_its_own_read():
    r = Rig()
    r.s.changed()
    r.during_read = r.s.changed
    r.run_next()
    assert r.delivered == ["snap1"] and len(r.timers) == 1 and not r.s.idle
    r.run_next()
    assert r.delivered == ["snap1", "snap2"] and r.s.idle


def test_lag_runs_from_the_oldest_unread_change_through_busy_retries():
    r = Rig(busy_times=2)
    r.now = 1_000
    r.s.changed()
    r.run_next(advance_ns=5)           # busy
    r.run_next(advance_ns=20_000_000)  # busy
    r.run_next(advance_ns=40_000_000)  # read
    assert r.s.max_lag_ns == 60_000_005


def test_a_requested_read_is_not_counted_as_a_change():
    r = Rig()
    r.s.read_soon()
    r.run_next()
    assert r.s.events == 0 and r.s.reads == 1 and r.s.max_lag_ns == 0
