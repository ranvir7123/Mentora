import threading
import time

from app.excel.com_thread import ComThread


def test_submit_runs_on_the_thread_and_timers_fire_in_order():
    t = ComThread("test-com")
    fired: list[str] = []
    done = threading.Event()

    def setup():
        t.call_later(0.05, lambda: fired.append("second"))
        t.call_later(0.01, lambda: fired.append("first"))
        t.call_later(0.08, done.set)

    t.start(setup, lambda: fired.append("teardown"))
    try:
        assert t.submit(t.on_thread).result(5) is True
        assert done.wait(5)
        assert fired == ["first", "second"]
    finally:
        t.stop()
    assert fired[-1] == "teardown"


def test_an_error_in_submitted_work_reaches_the_caller():
    t = ComThread("test-com-2")
    t.start(lambda: None, lambda: None)
    try:
        fut = t.submit(lambda: 1 / 0)
        try:
            fut.result(5)
            raise AssertionError("expected ZeroDivisionError")
        except ZeroDivisionError:
            pass
        assert t.submit(lambda: "still pumping").result(5) == "still pumping"
    finally:
        t.stop()


def test_the_pump_sleeps_instead_of_spinning():
    t = ComThread("test-com-3")
    t.start(lambda: None, lambda: None)
    try:
        start = time.process_time()
        time.sleep(0.5)
        assert time.process_time() - start < 0.2   # a spinning pump burns ~0.5 s of processor here
    finally:
        t.stop()
