import pytest


def test_app_registers_auth_routes(test_app):
    rules = {rule.rule for rule in test_app.url_map.iter_rules()}
    assert "/api/v1/auth/login" in rules
    assert "/api/v1/auth/refresh" in rules


def test_login_success(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "Password123!"}
    )

    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_password(client, test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "WrongPassword!"}
    )

    assert response.status_code == 401
    assert response.is_json
    assert response.get_json()["error"] == "Invalid credentials"


def test_refresh_token_returns_new_access_token(client, test_user):
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "Password123!"}
    )

    refresh_token = login_response.get_json()["refresh_token"]
    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert response.status_code == 200
    assert response.is_json
    assert "access_token" in response.get_json()
