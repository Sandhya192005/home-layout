import httpx
import pytest

from app.core.config import settings


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


def test_chat_requires_auth(client):
    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 401


def test_chat_without_api_key_returns_503(client, auth_headers):
    assert settings.NVIDIA_NIM_API_KEY == ""  # default test config: feature intentionally unconfigured
    r = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "How big should a bedroom be?"}]},
        headers=auth_headers,
    )
    assert r.status_code == 503


def test_chat_rejects_empty_messages(client, auth_headers):
    r = client.post("/api/v1/chat", json={"messages": []}, headers=auth_headers)
    assert r.status_code == 422


def test_chat_success_with_mocked_nim(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "fake-key")
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse({"choices": [{"message": {"content": "A bedroom should be at least 10x11 ft."}}]})

    monkeypatch.setattr("app.services.chat_assistant.httpx.post", fake_post)

    r = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "How big should a bedroom be?"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "A bedroom should be at least 10x11 ft."
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][-1] == {"role": "user", "content": "How big should a bedroom be?"}


def test_chat_includes_project_context(client, auth_headers, project, floor_plan, monkeypatch):
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "fake-key")
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("app.services.chat_assistant.httpx.post", fake_post)

    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Why is my kitchen small?"}], "project_id": project["id"]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    system_content = captured["json"]["messages"][0]["content"]
    assert "current project" in system_content
    assert f"{floor_plan['total_built_up_area']:,.0f}" in system_content


def test_chat_rejects_other_users_project(client, auth_headers, project, monkeypatch):
    from tests.conftest import register_and_login

    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "fake-key")
    other_headers = register_and_login(client, email="other-chat@example.com")
    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "project_id": project["id"]},
        headers=other_headers,
    )
    assert r.status_code == 403


def test_chat_upstream_failure_returns_502(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "fake-key")

    def fake_post(url, json, headers, timeout):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.services.chat_assistant.httpx.post", fake_post)

    r = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers=auth_headers
    )
    assert r.status_code == 502
