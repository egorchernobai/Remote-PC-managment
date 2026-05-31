from flask_jwt_extended import create_access_token
from app import db
from app.models import User


def test_login_get(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.data.decode("utf-8")


def test_login_post_success(client, test_user):
    response = client.post(
        "/login",
        data={"username": "testuser", "password": "Password123!"}
    )
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]


def test_login_post_invalid_password(client, test_user):
    response = client.post(
        "/login",
        data={"username": "testuser", "password": "WrongPassword!"}
    )
    assert response.status_code == 200
    assert "Invalid username or password" in response.data.decode("utf-8")


def test_logout_redirects_to_login(client):
    response = client.get("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_page_redirects_non_admin(client, test_app, viewer_user):
    access = create_access_token(identity=viewer_user.id, additional_claims={"role": "viewer"})
    with client.session_transaction() as session:
        session["access_token"] = access
        session["username"] = viewer_user.username
        session["role"] = "viewer"

    response = client.get("/admin")
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]
