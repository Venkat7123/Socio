"""Endpoints that are still stubs (analytics)."""


def test_hotspots_stub(client):
    assert client.get("/analytics/hotspots").json()["hotspots"]
