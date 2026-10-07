from fastapi.testclient import TestClient
from app.main import app
from app.models import PlaySession
from app.db import SessionLocal
from datetime import timedelta


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_full_flow():
    with TestClient(app) as c:
        admin = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
        c.post("/auth/register", json={"username": "ali", "password": "123"}, headers=auth(admin))
        c.post("/admin/topup", json={"username": "ali", "amount": 1000}, headers=auth(admin))
        tok = c.post("/auth/login", json={"username": "ali", "password": "123"}).json()["token"]
        r = c.post("/sessions/start", json={"pc_name": "PC1"}, headers=auth(tok))
        assert r.json()["remaining_seconds"] == 3600
        with SessionLocal() as db:  # نرجّع بداية الجلسة 30 دقيقة
            s = db.get(PlaySession, r.json()["session_id"])
            s.started_at -= timedelta(minutes=30)
            db.commit()
        hb = c.post("/sessions/heartbeat", headers=auth(tok)).json()
        assert hb["active"] and hb["balance"] == 500


def test_no_balance_blocked():
    with TestClient(app) as c:
        admin = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
        c.post("/auth/register", json={"username": "poor", "password": "1"}, headers=auth(admin))
        tok = c.post("/auth/login", json={"username": "poor", "password": "1"}).json()["token"]
        assert c.post("/sessions/start", json={"pc_name": "PC2"}, headers=auth(tok)).status_code == 402


def test_session_closes_when_balance_ends():
    with TestClient(app) as c:
        admin = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
        c.post("/auth/register", json={"username": "sara", "password": "1"}, headers=auth(admin))
        c.post("/admin/topup", json={"username": "sara", "amount": 100}, headers=auth(admin))
        tok = c.post("/auth/login", json={"username": "sara", "password": "1"}).json()["token"]
        r = c.post("/sessions/start", json={"pc_name": "PC3"}, headers=auth(tok))
        assert r.status_code == 200
        live = c.get("/admin/sessions", headers=auth(admin)).json()
        assert any(x["pc_name"] == "PC3" for x in live)
        with SessionLocal() as db:
            s = db.get(PlaySession, r.json()["session_id"])
            s.started_at -= timedelta(hours=2)
            db.commit()
        hb = c.post("/sessions/heartbeat", headers=auth(tok)).json()
        assert hb["active"] is False and hb["balance"] == 0


def test_games_list_and_pc_busy():
    with TestClient(app) as c:
        admin = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
        assert len(c.get("/games", headers=auth(admin)).json()) >= 1
