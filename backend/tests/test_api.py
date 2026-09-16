from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import app, settings


def test_unconfigured_analysis_endpoint(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ft_client_id", "")
    monkeypatch.setattr(settings, "ft_client_secret", "")
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "mode": "not_configured"}

        response = client.post(
            "/api/analyze",
            json={"query": "Data engineer"},
        )
        assert response.status_code == 503
        assert "France Travail n'est pas configuré" in response.json()["detail"]
