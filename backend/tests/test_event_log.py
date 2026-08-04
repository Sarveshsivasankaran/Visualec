from app.services.state import RuntimeState


def test_event_log_keeps_latest_fifteen_only():
    state = RuntimeState()
    for index in range(20):
        state.record_event("detection", f"Event {index}", people_count=index)

    events = state.snapshot()["events"]
    assert len(events) == 15
    assert events[0]["message"] == "Event 19"
    assert events[-1]["message"] == "Event 5"
