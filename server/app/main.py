import os
import json
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_db, SessionLocal
from .models import User, PlaySession, Transaction, now
from .security import hash_pw, check_pw, make_token, current_user, admin_user

RATE_PER_HOUR = int(os.getenv("RATE_PER_HOUR", "1000"))  # بالقروش


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.is_admin)):
            db.add(User(username=os.getenv("ADMIN_USER", "admin"),
                        password_hash=hash_pw(os.getenv("ADMIN_PASS", "admin123")), is_admin=True))
            db.commit()
    yield


app = FastAPI(title="GameCafe", lifespan=lifespan)
GAMES_FILE = Path(os.getenv("GAMES_FILE", Path(__file__).resolve().parent.parent / "data" / "games.json"))


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


class Credentials(BaseModel):
    username: str
    password: str


class TopUp(BaseModel):
    username: str
    amount: int


class StartReq(BaseModel):
    pc_name: str


def bill(db: Session, s: PlaySession, user: User) -> int:
    """يخصم المستحق حتى الآن، ويقفل الجلسة لو الرصيد خلص. يرجع الثواني المتبقية."""
    elapsed = int(((s.ended_at or now()) - s.started_at).total_seconds())
    due = elapsed * s.rate_per_hour // 3600
    delta = min(due - s.charged, user.balance)
    if delta > 0:
        user.balance -= delta
        s.charged += delta
        db.add(Transaction(user_id=user.id, amount=-delta, kind="usage"))
    if user.balance <= 0 and s.ended_at is None:
        s.ended_at = now()
    db.commit()
    return 0 if s.ended_at else user.balance * 3600 // s.rate_per_hour


@app.post("/auth/register")
def register(c: Credentials, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    if db.scalar(select(User).where(User.username == c.username)):
        raise HTTPException(400, "الاسم مستخدم")
    db.add(User(username=c.username, password_hash=hash_pw(c.password)))
    db.commit()
    return {"ok": True}


@app.post("/auth/login")
def login(c: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == c.username))
    if not user or not check_pw(c.password, user.password_hash):
        raise HTTPException(401, "بيانات خاطئة")
    return {"token": make_token(user.id), "balance": user.balance, "is_admin": user.is_admin}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "balance": user.balance}


@app.post("/admin/topup")
def topup(t: TopUp, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    user = db.scalar(select(User).where(User.username == t.username))
    if not user or t.amount <= 0:
        raise HTTPException(400, "طلب غير صالح")
    user.balance += t.amount
    db.add(Transaction(user_id=user.id, amount=t.amount, kind="topup"))
    db.commit()
    return {"balance": user.balance}


def active_session(db: Session, user: User) -> PlaySession | None:
    return db.scalar(select(PlaySession).where(PlaySession.user_id == user.id, PlaySession.ended_at.is_(None)))


@app.post("/sessions/start")
def start(r: StartReq, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.balance <= 0:
        raise HTTPException(402, "الرصيد غير كافٍ")
    if active_session(db, user):
        raise HTTPException(409, "عندك جلسة شغالة")
    if db.scalar(select(PlaySession).where(PlaySession.pc_name == r.pc_name, PlaySession.ended_at.is_(None))):
        raise HTTPException(409, "الجهاز مشغول")
    s = PlaySession(user_id=user.id, pc_name=r.pc_name, rate_per_hour=RATE_PER_HOUR)
    db.add(s)
    db.commit()
    return {"session_id": s.id, "remaining_seconds": user.balance * 3600 // RATE_PER_HOUR}


@app.post("/sessions/heartbeat")
def heartbeat(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = active_session(db, user)
    if not s:
        return {"active": False, "remaining_seconds": 0, "balance": user.balance}
    remaining = bill(db, s, user)
    return {"active": s.ended_at is None, "remaining_seconds": remaining, "balance": user.balance}


@app.post("/sessions/end")
def end(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = active_session(db, user)
    if s:
        s.ended_at = now()
        bill(db, s, user)
    return {"balance": user.balance}


@app.get("/games")
def games(_: User = Depends(current_user)):
    return json.loads(GAMES_FILE.read_text(encoding="utf-8"))


@app.get("/admin/sessions")
def live_sessions(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    rows = db.execute(
        select(PlaySession, User).join(User, User.id == PlaySession.user_id).where(PlaySession.ended_at.is_(None))
    ).all()
    return [
        {"pc_name": s.pc_name, "username": u.username, "started_at": s.started_at.isoformat(),
         "balance": u.balance, "charged": s.charged}
        for s, u in rows
    ]
