#!/usr/bin/env python3
"""
Kling 批量注册脚本
用法: python register_kling.py --count 10
"""
import asyncio
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from platforms.kling.core import KlingRegister


async def register_batch(count: int, output_file: str):
    results = []
    success = 0
    fail = 0

    for i in range(count):
        print(f"\n[{i+1}/{count}] Registering...")
        reg = KlingRegister()
        try:
            result = await reg.run_register()
            if result:
                results.append(result)
                success += 1
                print(f"  ✅ {result['email']} - cookie: {result['cookie'][:40] if result['cookie'] else 'None'}...")
            else:
                fail += 1
                print(f"  ❌ Failed")
        except Exception as e:
            fail += 1
            print(f"  ❌ Exception: {e}")
        finally:
            await reg.close()

        # 避免频率过高
        if i < count - 1:
            await asyncio.sleep(5)

    # 保存结果
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n=== Done ===")
    print(f"Success: {success}, Failed: {fail}")
    print(f"Saved to: {output_file}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10, help="Number of accounts to register")
    parser.add_argument("--output", default="kling_accounts.json", help="Output file")
    args = parser.parse_args()

    asyncio.run(register_batch(args.count, args.output))
