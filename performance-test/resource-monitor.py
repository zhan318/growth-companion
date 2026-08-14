"""资源监控：psutil 采样 CPU/内存/连接/句柄 → CSV

用法：
    python resource-monitor.py --out reports/raw/resource.csv --pid <后端pid> --interval 1 --duration 3600

指标：timestamp, cpu_percent, rss_mb, vms_mb, threads, open_files, conns_total, conns_time_wait
"""

import argparse
import csv
import os
import time

import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="CSV 输出路径")
    parser.add_argument("--pid", type=int, required=True, help="目标进程 PID（后端 uvicorn）")
    parser.add_argument("--interval", type=float, default=1.0, help="采样间隔（秒）")
    parser.add_argument("--duration", type=float, default=3600, help="监控时长（秒）")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    proc = psutil.Process(args.pid)
    print(f"[resource-monitor] 监控 PID={args.pid} ({proc.name()})，间隔 {args.interval}s，时长 {args.duration}s")
    print(f"[resource-monitor] 输出 → {args.out}")

    start = time.time()
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "cpu_percent", "rss_mb", "vms_mb",
            "threads", "open_files", "conns_total", "conns_established", "conns_time_wait",
        ])
        while time.time() - start < args.duration:
            try:
                proc.cpu_percent(None)  # 第一次调用返回 0，下一轮才有值
                cpu = proc.cpu_percent(None)
                mem = proc.memory_info()
                conns = proc.net_connections(kind="all")
                n_est = sum(1 for c in conns if c.status == "ESTABLISHED")
                n_tw = sum(1 for c in conns if c.status == "TIME_WAIT")
                row = [
                    time.strftime("%H:%M:%S"),
                    round(cpu, 1),
                    round(mem.rss / 1024 / 1024, 1),
                    round(mem.vms / 1024 / 1024, 1),
                    proc.num_threads(),
                    len(proc.open_files()),
                    len(conns),
                    n_est,
                    n_tw,
                ]
                writer.writerow(row)
                f.flush()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"[resource-monitor] 进程不可用: {e}")
                break
            time.sleep(args.interval)

    print("[resource-monitor] 完成")


if __name__ == "__main__":
    main()
