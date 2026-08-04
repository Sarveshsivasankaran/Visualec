import pytest

from app.services.energy_service import energy_kwh


def test_energy_calculation():
    assert energy_kwh(1000, 3600) == pytest.approx(1.0)
    assert energy_kwh(75, 7200) == pytest.approx(0.15)
