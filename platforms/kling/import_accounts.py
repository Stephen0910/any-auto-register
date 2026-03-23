#!/usr/bin/env python3
"""
Kling 账号导入工具

用法:
  # 手动添加账号（会自动登录+签到）
  python import_accounts.py add --email xxx@gmail.com --password Yourpass123!

  # 批量从 JSON 文件导入
  # 文件格式: [{"email": "...", "password": "..."}]
  python import_accounts.py import --file accounts.json

  # 查看池状态
  python import_accounts.py stats

  # 手动执行签到
  python import_accounts.py checkin
"""
import asyncio
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from platforms.kling.pool import KlingPool


async def cmd_add(email: str, password: str, cookie: str = ""):
    pool = KlingPool()
    acc = pool.add_account(email, password, cookie)
    print(f"Added: {email}")
    if not cookie:
        print("Logging in...")
        ok = await pool.login_account(acc)
        if ok:
            print(f"Login OK, cookie: {acc.cookie[:40]}...")
            print("Checking in...")
            await pool.checkin_account(acc)
        else:
            print("Login FAILED")
    pool.save()
    print(f"Stats: {pool.stats()}")


async def cmd_import(file: str):
    pool = KlingPool()
    with open(file) as f:
        accounts = json.load(f)
    print(f"Importing {len(accounts)} accounts...")
    for i, a in enumerate(accounts):
        email = a["email"]
        password = a["password"]
        cookie = a.get("cookie", "")
        print(f"[{i+1}/{len(accounts)}] {email}")
        acc = pool.add_account(email, password, cookie)
        if not acc.cookie:
            ok = await pool.login_account(acc)
            if ok:
                await pool.checkin_account(acc)
                print(f"  ✅ login+checkin OK")
            else:
                print(f"  ❌ login failed")
        else:
            print(f"  ✅ cookie provided")
        await asyncio.sleep(2)
    pool.save()
    print(f"\nDone. Stats: {pool.stats()}")


async def cmd_stats():
    pool = KlingPool()
    stats = pool.stats()
    print(f"Total accounts : {stats['total']}")
    print(f"Active (w/cookie): {stats['active']}")
    print(f"Total credits  : {stats['total_credits']}")
    print(f"\nAccounts:")
    for acc in pool.accounts:
        status = "✅" if acc.active and acc.cookie else "❌"
        import time
        checkin_ago = int((time.time() - acc.last_checkin) / 3600) if acc.last_checkin else 999
        print(f"  {status} {acc.email} | credits={acc.credits} | last_checkin={checkin_ago}h ago")


async def cmd_checkin():
    pool = KlingPool()
    stats = await pool.run_daily_checkin()
    print(f"Checkin done: {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", help="Add single account")
    p_add.add_argument("--email", required=True)
    p_add.add_argument("--password", required=True)
    p_add.add_argument("--cookie", default="")

    p_import = sub.add_parser("import", help="Import from JSON file")
    p_import.add_argument("--file", required=True)

    sub.add_parser("stats", help="Show pool stats")
    sub.add_parser("checkin", help="Run daily checkin")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    if args.cmd == "add":
        asyncio.run(cmd_add(args.email, args.password, getattr(args, "cookie", "")))
    elif args.cmd == "import":
        asyncio.run(cmd_import(args.file))
    elif args.cmd == "stats":
        asyncio.run(cmd_stats())
    elif args.cmd == "checkin":
        asyncio.run(cmd_checkin())
