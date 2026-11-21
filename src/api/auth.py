import hashlib
import os
import secrets
import time
from contextlib import contextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .accounts import (
    PUBLIC_FIELDS,
    create_account,
    encode_password,
    public_user,
    verify_password,
)
from .db import database, one

COOKIE = "kooying_session"
# Unknown and inactive accounts incur the same password-verification work.
DUMMY_HASH = "pbkdf2_sha256$600000$" + "00" * 16 + "$" + "00" * 32


def browser_write(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get("X-Workspace-Request") != "1"
        or request.headers.get("Sec-Fetch-Site") == "cross-site"
    ):
        raise HTTPException(403, "请通过工作台提交操作")


router = APIRouter(prefix="/api/auth", dependencies=[Depends(browser_write)])


class Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Form):
    username: str = Field(min_length=1, max_length=48)
    password: SecretStr = Field(min_length=1, max_length=256)
    remember: bool = False


class Password(Form):
    password: SecretStr = Field(min_length=12, max_length=256)


class ChangePassword(Password):
    current_password: SecretStr = Field(min_length=1, max_length=256)


class Member(Password):
    username: str = Field(min_length=3, max_length=48)
    display_name: str = Field(min_length=1, max_length=40)
    role: Literal["admin", "sales"] = "sales"


class Status(Form):
    active: bool


def token_key(request):
    return hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()


def read_session(db, request: Request):
    row = db.execute(
        """SELECT u.*, s.expires_at, s.remember FROM sessions s JOIN users u
        ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>%s AND u.active=1""",
        (token_key(request), int(time.time())),
    ).fetchone()
    if row is None:
        raise HTTPException(401, "请登录工作台")
    return row


def session_user(request: Request):
    with database() as db:
        return read_session(db, request)


def workspace_user(user=Depends(session_user)):
    if user["must_change"]:
        raise HTTPException(403, "请先修改初始密码")
    return user


def administrator(user=Depends(workspace_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "此操作需要管理员权限")
    return user


def session_info(user, expires):
    return {"user": public_user(user), "expires_at": expires}


def issue(db, response, user, remember):
    now = int(time.time())
    ttl = (14 * 24 if remember else 8) * 3600
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at<=%s", (now,))
    db.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at,remember) VALUES(%s,%s,%s,%s)",
        (
            hashlib.sha256(token.encode()).hexdigest(),
            user["id"],
            now + ttl,
            int(remember),
        ),
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=os.getenv("SESSION_COOKIE_SECURE") == "1",
        samesite="strict",
        path="/",
        max_age=ttl if remember else None,
    )
    return session_info(user, now + ttl)


def reserve_attempt(keys):
    now = int(time.time())
    with database(True) as db:
        db.execute("DELETE FROM login_limits WHERE until<=%s", (now,))
        for key, limit in keys:
            row = db.execute(
                "SELECT hits FROM login_limits WHERE bucket=%s", (key,)
            ).fetchone()
            if row and row["hits"] >= limit:
                raise HTTPException(429, "尝试次数过多，请稍后再试")
        for key, _ in keys:
            db.execute(
                """INSERT INTO login_limits VALUES(%s,1,%s) ON CONFLICT(bucket)
                        DO UPDATE SET hits=login_limits.hits+1""",
                (key, now + 600),
            )


@router.post("/login")
def login(form: Login, request: Request, response: Response):
    name = form.username.strip().lower()
    account_key = "user:" + name
    peer_key = "peer:" + (request.client.host if request.client else "local")
    reserve_attempt([(account_key, 10), (peer_key, 100)])
    with database() as db:
        row = db.execute("SELECT * FROM users WHERE username=%s", (name,)).fetchone()
    encoded = row["password_hash"] if row and row["active"] else DUMMY_HASH
    if (
        not verify_password(form.password.get_secret_value(), encoded)
        or not row
        or not row["active"]
    ):
        raise HTTPException(401, "账号或密码不正确")
    with database(True) as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=%s AND active=1 AND password_hash=%s",
            (row["id"], encoded),
        ).fetchone()
        if not user:
            raise HTTPException(401, "账号或密码不正确")
        db.execute("DELETE FROM login_limits WHERE bucket=%s", (account_key,))
        db.execute(
            "UPDATE login_limits SET hits=greatest(0,hits-1) WHERE bucket=%s", (peer_key,)
        )
        db.execute("DELETE FROM sessions WHERE token_hash=%s", (token_key(request),))
        return issue(db, response, user, form.remember)


@router.get("/me")
def me(user=Depends(session_user)):
    return session_info(user, user["expires_at"])


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    with database(True) as db:
        db.execute("DELETE FROM sessions WHERE token_hash=%s", (token_key(request),))
    response.delete_cookie(
        COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=os.getenv("SESSION_COOKIE_SECURE") == "1",
    )


@router.post("/password")
def change_password(
    form: ChangePassword,
    request: Request,
    response: Response,
    user=Depends(session_user),
):
    old, new = (
        form.current_password.get_secret_value(),
        form.password.get_secret_value(),
    )
    bucket = "change:" + str(user["id"])
    reserve_attempt([(bucket, 10)])
    if not verify_password(old, user["password_hash"]):
        raise HTTPException(400, "当前密码不正确")
    if old == new:
        raise HTTPException(422, "新密码须与当前密码不同")
    encoded = encode_password(new)
    with database(True) as db:
        changed = db.execute(
            f"""UPDATE users SET password_hash=%s,must_change=0
            WHERE id=%s AND active=1 AND password_hash=%s AND EXISTS
            (SELECT 1 FROM sessions WHERE token_hash=%s AND expires_at>%s) RETURNING {PUBLIC_FIELDS}""",
            (
                encoded,
                user["id"],
                user["password_hash"],
                token_key(request),
                int(time.time()),
            ),
        ).fetchone()
        if not changed:
            raise HTTPException(401, "登录状态已变更，请重新登录")
        db.execute("DELETE FROM sessions WHERE user_id=%s", (user["id"],))
        db.execute(
            "DELETE FROM login_limits WHERE bucket IN (%s,%s)",
            (bucket, "user:" + user["username"]),
        )
        return issue(db, response, changed, user["remember"])


Admin = Annotated[dict, Depends(administrator)]


@contextmanager
def admin_write(request):
    # Permission and update share the write transaction if another admin revokes access.
    with database(True) as db:
        administrator(workspace_user(read_session(db, request)))
        yield db


@router.get("/members")
def members(admin: Admin):
    with database() as db:
        return [
            public_user(row)
            for row in db.execute(f"SELECT {PUBLIC_FIELDS} FROM users ORDER BY id")
        ]


@router.post("/members", status_code=201)
def add_member(form: Member, admin: Admin, request: Request):
    encoded = encode_password(form.password.get_secret_value())
    with admin_write(request) as db:
        return create_account(db, form.username, form.display_name, form.role, encoded)


@router.patch("/members/{ident}")
def set_status(ident: int, form: Status, admin: Admin, request: Request):
    with admin_write(request) as db:
        if ident == admin["id"]:
            raise HTTPException(409, "不能更改自己的账号状态")
        if (
            not form.active
            and db.execute(
                "SELECT count(*) FROM users WHERE active=1 AND role='admin' AND id<>%s",
                (ident,),
            ).fetchone()["count"]
            == 0
        ):
            raise HTTPException(409, "工作台至少需要一位启用的管理员")
        one(db, "SELECT id FROM users WHERE id=%s", (ident,))
        db.execute("UPDATE users SET active=%s WHERE id=%s", (int(form.active), ident))
        if not form.active:
            db.execute("DELETE FROM sessions WHERE user_id=%s", (ident,))
    return {"active": form.active}


@router.post("/members/{ident}/password", status_code=204)
def reset_password(ident: int, form: Password, admin: Admin, request: Request):
    if ident == admin["id"]:
        raise HTTPException(409, "请在我的账号中修改密码")
    encoded = encode_password(form.password.get_secret_value())
    with admin_write(request) as db:
        member = one(db, "SELECT username FROM users WHERE id=%s", (ident,))
        db.execute(
            "UPDATE users SET password_hash=%s,must_change=1 WHERE id=%s",
            (encoded, ident),
        )
        db.execute("DELETE FROM sessions WHERE user_id=%s", (ident,))
        db.execute(
            "DELETE FROM login_limits WHERE bucket IN (%s,%s)",
            ("user:" + member["username"], "change:" + str(ident)),
        )
