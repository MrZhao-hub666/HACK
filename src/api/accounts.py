"""Local account storage and operator-only administrator provisioning."""

import argparse
import getpass
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys

from fastapi import HTTPException

from .db import database, initialize

PUBLIC_FIELDS = "id, username, display_name, role, active, must_change"
USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{2,47}\Z")
ROUNDS = 600_000
PASSWORD_HASH = re.compile(
    r"pbkdf2_sha256\$[1-9][0-9]{0,6}\$[0-9a-f]{32}\$[0-9a-f]{64}"
)


def encode_password(password):
    if not 12 <= len(password) <= 256 or not password.strip():
        raise HTTPException(422, "密码长度须为 12 至 256 个字符")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), ROUNDS
    )
    return f"pbkdf2_sha256${ROUNDS}${salt}${digest.hex()}"


def verify_password(password, encoded):
    _, rounds, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
    )
    return hmac.compare_digest(actual, bytes.fromhex(expected))


def public_user(row):
    return {
        k: bool(row[k]) if k in ("active", "must_change") else row[k]
        for k in PUBLIC_FIELDS.split(", ")
    }


def create_account(db, username, display_name, role, encoded, must_change=True):
    name = display_name.strip()
    username = username.strip().lower()
    if not USERNAME.fullmatch(username):
        raise HTTPException(422, "账号须为 3 至 48 位小写字母、数字、点、横线或下划线")
    if not 1 <= len(name) <= 40 or name in {"系统", "待认领"}:
        raise HTTPException(422, "请输入有效的成员姓名")
    try:
        row = db.execute(
            f"""INSERT INTO users(username,display_name,role,password_hash,must_change)
                VALUES(?,?,?,?,?) RETURNING {PUBLIC_FIELDS}""",
            (username, name, role, encoded, int(must_change)),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "账号或成员姓名已被使用") from exc
    return public_user(row)


def team(db):
    return [
        row[0]
        for row in db.execute(
            "SELECT display_name FROM users WHERE active=1 ORDER BY id"
        )
    ]


def bootstrap_admin():
    encoded = os.getenv("ADMIN_BOOTSTRAP_PASSWORD_HASH", "").strip()
    if not encoded:
        return
    with database(True) as db:
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        if not PASSWORD_HASH.fullmatch(encoded):
            raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD_HASH 格式无效")
        create_account(db, "admin", "工作台管理员", "admin", encoded, must_change=False)


def main():
    parser = argparse.ArgumentParser(description="工作台管理员初始化与密码恢复")
    parser.add_argument("action", choices=["init-admin", "recover-admin", "hash-password"])
    parser.add_argument("--username", default="admin")
    parser.add_argument("--name", default="工作台管理员")
    parser.add_argument("--permanent", action="store_true", help="使用输入的密码直接登录")
    args = parser.parse_args()
    password = (
        getpass.getpass("初始密码（至少 12 个字符）: ")
        if sys.stdin.isatty()
        else sys.stdin.readline().rstrip("\r\n")
    )
    try:
        encoded = encode_password(password)
        if args.action == "hash-password":
            print(encoded)
            return
        initialize()
        must_change = not args.permanent
        with database(True) as db:
            if args.action == "init-admin":
                if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise HTTPException(409, "工作台已初始化")
                create_account(db, args.username, args.name, "admin", encoded, must_change)
            else:
                row = db.execute(
                    """UPDATE users SET password_hash=?,active=1,must_change=?
                    WHERE username=? AND role='admin' RETURNING id""",
                    (encoded, int(must_change), args.username.strip().lower()),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "管理员账号不存在")
                db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
                db.execute(
                    "DELETE FROM login_limits WHERE bucket IN (?,?)",
                    (
                        "user:" + args.username.strip().lower(),
                        "change:" + str(row["id"]),
                    ),
                )
    except HTTPException as exc:
        parser.exit(1, exc.detail + "\n")
    if must_change:
        print("管理员账号已就绪，登录后请修改初始密码。")
    else:
        print("管理员账号已就绪，可用设定的密码直接登录。")


if __name__ == "__main__":
    main()
