def test_health_reports_real_hardware_status(client):
    health = client.get("/api/system/health")
    assert health.status_code == 200
    assert health.json()["database"] == "connected"
    assert health.json()["esp32"] in {"connected", "offline"}


def test_zone_validation(client):
    response = client.post("/api/zones", json={
        "name": "Broken", "zone_type": "polygon", "colour": "blue",
        "coordinates": [{"x": 0, "y": 0}, {"x": 1, "y": 0}],
    })
    assert response.status_code == 422


def test_invalid_mode_is_rejected(client):
    response = client.put("/api/settings", json={"mode": "unsupported"})
    assert response.status_code == 422
