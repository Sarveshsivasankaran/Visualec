from app.config import Settings
from app.services.occupancy_service import OccupancyService
from app.services.state import RuntimeState, ZoneRuntime


def service() -> tuple[OccupancyService, RuntimeState]:
    state = RuntimeState()
    state.zones[1] = ZoneRuntime(1, "Zone 1", "#22d3ee")
    settings = Settings(activation_delay_seconds=1, deactivation_delay_seconds=10)
    return OccupancyService(settings, state), state


def test_activation_and_deactivation_delays():
    occupancy, state = service()
    assert occupancy.update({1: 1}, now=100) == []
    assert not state.zones[1].occupied
    transitions = occupancy.update({1: 1}, now=101)
    assert transitions[0].current is True
    assert occupancy.update({1: 0}, now=105) == []
    assert state.zones[1].occupied
    transitions = occupancy.update({1: 0}, now=115)
    assert transitions[0].current is False


def test_brief_boundary_crossing_does_not_activate():
    occupancy, state = service()
    occupancy.update({1: 1}, now=1)
    occupancy.update({1: 0}, now=1.5)
    occupancy.update({1: 1}, now=2)
    assert not state.zones[1].occupied
