#!/usr/bin/env python
"""
挂载性能体检：验证 SQLite 在容器挂载目录上能不能正常跑。

为什么需要这个脚本：
    Windows / macOS 上用 Docker 时，宿主机目录不是真的"直接"挂进容器的。
    Windows 走的是 NTFS -> WSL2 的 9p 通道，macOS 走的是 virtiofs / gRPC-FUSE。
    这两条通道对 POSIX 文件锁的支持都不完整，而 SQLite 的 WAL 模式
    恰恰依赖文件锁。症状通常是：
        - 写入偶发 "database is locked"
        - 并发读写直接崩
        - 速度比本地磁盘慢一到两个数量级
    在 Linux 服务器上挂原生 ext4 目录没有这个问题。

用法（在容器里跑）：
    docker compose exec kids python tools/probe_mount.py
    docker compose exec kids python tools/probe_mount.py --quick
"""

import argparse
import os
import sqlite3
import sys
import tempfile
import time

# 低于这个值说明挂载通道有严重性能问题，数据库应该挪到 Docker 命名卷上
SLOW_THRESHOLD_MB_S = 20.0


def hr(title=""):
    print()
    if title:
        print("=" * 62)
        print(" " + title)
        print("=" * 62)
    else:
        print("-" * 62)


def fmt(v, unit="", width=9):
    return f"{v:>{width}.2f}{unit}"


def where(path):
    """说清楚一个路径究竟落在哪一层文件系统上。"""
    try:
        st = os.stat(path)
        return f"inode={st.st_ino} dev={st.st_dev}"
    except OSError as e:
        return f"无法 stat: {e}"


def probe_fs(path):
    """判断挂载类型。Windows/Mac 的 bind mount 在 /proc/mounts 里会有特征。"""
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            mounts = f.read().splitlines()
    except OSError:
        return "unknown"

    # 找最长匹配的那条
    best, best_src = None, ""
    for line in mounts:
        parts = line.split()
        if len(parts) < 3:
            continue
        src, dst, fstype = parts[0], parts[1], parts[2]
        if path.startswith(dst) and (best is None or len(dst) > len(best)):
            best, best_src = dst, f"{src} ({fstype})"

    if best:
        return f"{best} <- {best_src}"
    return "未找到匹配的挂载点"


def bench_write(path, size_mb, block_kb=64):
    """顺序写：模拟 SQLite 写库。"""
    block = b"x" * (block_kb * 1024)
    n = int(size_mb * 1024 / block_kb)
    t0 = time.perf_counter()
    with open(path, "wb") as f:
        for _ in range(n):
            f.write(block)
        f.flush()
        os.fsync(f.fileno())
    dt = time.perf_counter() - t0
    return size_mb / dt, dt


def bench_read(path):
    t0 = time.perf_counter()
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
    dt = time.perf_counter() - t0
    mb = total / 1024 / 1024
    return mb / dt, dt


def bench_fsync(path, rounds=200):
    """fsync 单项：这是 WAL 提交路径上最贵的一步。"""
    t0 = time.perf_counter()
    with open(path, "wb") as f:
        for _ in range(rounds):
            f.write(b"y" * 4096)
            f.flush()
            os.fsync(f.fileno())
    dt = time.perf_counter() - t0
    return rounds / dt, dt


def bench_sqlite(path, rows):
    """真实路径压测：建表 + 事务插入 + 索引 + 查询。"""
    if os.path.exists(path):
        os.remove(path)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)

    con = sqlite3.connect(path, timeout=10)
    try:
        mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]

        con.execute("""CREATE TABLE t (
            id INTEGER PRIMARY KEY, a TEXT, b INTEGER, c REAL)""")

        t0 = time.perf_counter()
        con.execute("BEGIN")
        con.executemany(
            "INSERT INTO t (a,b,c) VALUES (?,?,?)",
            [(f"row-{i}", i, i * 1.5) for i in range(rows)],
        )
        con.commit()
        t_ins = time.perf_counter() - t0

        t0 = time.perf_counter()
        con.execute("CREATE INDEX idx_b ON t(b)")
        con.commit()
        t_idx = time.perf_counter() - t0

        t0 = time.perf_counter()
        n = con.execute("SELECT COUNT(*) FROM t WHERE b > ?", (rows // 2,)).fetchone()[0]
        t_q = time.perf_counter() - t0

        # 并发锁：同一进程两个连接模拟父子端同时写
        t0 = time.perf_counter()
        con2 = sqlite3.connect(path, timeout=5)
        try:
            con2.execute("BEGIN IMMEDIATE")
            con2.execute("INSERT INTO t (a,b,c) VALUES ('lock',-1,0.0)")
            con2.commit()
            lock_ok = True
        except sqlite3.OperationalError as e:
            lock_ok = False
            print(f"      并发写失败: {e}")
        finally:
            con2.close()
        t_lock = time.perf_counter() - t0

        return {
            "journal_mode": mode,
            "insert_ms": t_ins * 1000,
            "insert_rate": rows / t_ins if t_ins else 0,
            "index_ms": t_idx * 1000,
            "query_ms": t_q * 1000,
            "query_hits": n,
            "lock_ms": t_lock * 1000,
            "lock_ok": lock_ok,
        }
    finally:
        con.close()
        for suffix in ("", "-wal", "-shm"):
            p = path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.environ.get("KIDS_DATA_DIR", "/app/data"))
    ap.add_argument("--size", type=int, default=64, help="顺序写测试 MB 数")
    ap.add_argument("--rows", type=int, default=2000, help="SQLite 插入行数")
    ap.add_argument("--quick", action="store_true", help="跑最小集，几秒出结果")
    args = ap.parse_args()

    if args.quick:
        args.size, args.rows = 16, 500

    target = args.dir
    hr("挂载性能体检")
    print(f"  被测目录 : {target}")
    print(f"  文件系统 : {probe_fs(target)}")
    print(f"  权限     : uid={os.getuid()} gid={os.getgid()}")
    print(f"  可写     : {os.access(target, os.W_OK)}")
    print(f"  磁盘余量 : ", end="")
    st = os.statvfs(target)
    print(f"{st.f_bavail * st.f_frsize / 1024**3:.1f} GB")

    # ---- 1. 顺序写 / 读 ----
    hr("1. 顺序读写吞吐")
    tmp = os.path.join(target, ".probe.bin")
    try:
        w_mbs, w_dt = bench_write(tmp, args.size)
        r_mbs, r_dt = bench_read(tmp)
        print(f"  写 {args.size}MB : {fmt(w_mbs,' MB/s')}   耗时 {fmt(w_dt,' s')}")
        print(f"  读 {args.size}MB : {fmt(r_mbs,' MB/s')}   耗时 {fmt(r_dt,' s')}")
        write_ok = w_mbs >= SLOW_THRESHOLD_MB_S
        print(f"  判定     : {'正常' if write_ok else f'偏慢（阈值 {SLOW_THRESHOLD_MB_S} MB/s）'}")
    except OSError as e:
        write_ok = False
        print(f"  顺序读写失败: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # ---- 2. fsync ----
    hr("2. fsync 频率（WAL 提交的关键指标）")
    tmp2 = os.path.join(target, ".probe.sync")
    try:
        rounds = 50 if args.quick else 200
        f_rate, f_dt = bench_fsync(tmp2, rounds)
        per_ms = (f_dt / rounds) * 1000
        print(f"  {rounds} 次 fsync : {fmt(f_rate,' 次/s')}   单次 {fmt(per_ms,' ms')}")
        sync_ok = per_ms < 20
        print(f"  判定     : {'正常' if sync_ok else '偏慢，每次提交都要等，页面会感觉卡'}")
    except OSError as e:
        sync_ok = False
        print(f"  fsync 失败: {e}")
    finally:
        if os.path.exists(tmp2):
            os.remove(tmp2)

    # ---- 3. SQLite 真实路径 ----
    hr("3. SQLite / WAL")
    db = os.path.join(target, ".probe.db")
    try:
        r = bench_sqlite(db, args.rows)
        print(f"  journal_mode : {r['journal_mode']}"
              f"{'  ✅' if r['journal_mode'] == 'wal' else '  ⚠️ 没进 WAL 模式'}")
        print(f"  插入 {args.rows} 行 : {fmt(r['insert_ms'],' ms')}"
              f"   ({fmt(r['insert_rate'],' 行/s')})")
        print(f"  建索引       : {fmt(r['index_ms'],' ms')}")
        print(f"  条件查询     : {fmt(r['query_ms'],' ms')}  命中 {r['query_hits']} 行")
        print(f"  并发写锁     : {'✅ 正常' if r['lock_ok'] else '❌ 失败'}"
              f"   {fmt(r['lock_ms'],' ms')}")
        sqlite_ok = r["journal_mode"] == "wal" and r["lock_ok"]
    except Exception as e:
        sqlite_ok = False
        print(f"  SQLite 测试失败: {e}")
    finally:
        if os.path.exists(db):
            os.remove(db)

    # ---- 结论 ----
    hr("结论")
    if sqlite_ok and write_ok and sync_ok:
        print("  ✅ 挂载一切正常，data/ 保持现在的 bind mount 即可。")
        code = 0
    elif sqlite_ok:
        print("  ⚠️  SQLite 功能正常，但吞吐偏低。")
        print("     日常用（几十个孩子的数据量）感觉不出来，")
        print("     但导入大教材 PDF 时会明显慢。可接受，也可优化。")
        code = 0
    else:
        print("  ❌ 挂载通道不支持 SQLite 并发写，必须换方案：")
        print("""
  方案：把 data/ 改成 Docker 命名卷（存在 WSL2 的原生 ext4 上）
        代码仍然挂 Windows 目录以便修改。

    volumes:
      kids-data:/app/data        # 改这一行
      - ./uploads:/app/uploads
      - ./rules.yaml:/app/rules.yaml

    volumes:
      kids-data:

  代价：data/ 不再直接躺在项目目录里，备份要用
        docker run --rm -v kids-data:/d -v %cd%:/b alpine tar czf /b/data.tgz /d
""")
        code = 1

    print()
    return code


if __name__ == "__main__":
    sys.exit(main())
