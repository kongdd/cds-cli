#!/usr/bin/env python
"""查询已完成的 CDS 任务，保存下载清单，再用 aria2c 下载。"""

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import cdsapi


STATES = ("accepted", "running", "successful", "failed", "rejected", "dismissed", "deleted")


def task_filename(dataset, request, url, prefix=None, subfix=None):
    years = request.get("year") or []
    if isinstance(years, (str, int)):
        years = [years]
    year = "-".join(sorted({str(year) for year in years})) or "unknown-year"
    prefix = dataset + "_" if prefix is None else prefix
    extension = "".join(Path(urlsplit(url).path).suffixes) or ".bin"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{prefix}{year}{subfix or ''}")
    return stem + extension


def fetch(limit, outdir, prefix=None, subfix=None):
    api = cdsapi.Client(delete=False, quiet=True).client
    ids = api.get_jobs(limit=limit, sortby="-created", status="successful").request_ids[:limit]
    items = []
    for request_id in ids:
        remote = api.get_remote(request_id)
        dataset = remote.collection_id
        request = remote.request
        result = remote.get_results()
        items.append(
            {
                "request_id": request_id,
                "dataset": dataset,
                "request": request,
                "url": result.location,
                "size": result.content_length,
                "filename": task_filename(dataset, request, result.location, prefix, subfix),
            }
        )
    if not items:
        raise ValueError("没有可下载的已完成任务")
    if len({item["filename"] for item in items}) != len(items):
        raise ValueError("文件名重复，请缩小 --limit 或调整命名，避免覆盖")

    outdir = Path(outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    files = {
        "manifest.json": json.dumps(items, indent=2, ensure_ascii=False) + "\n",
        # 最后更新 urls.txt，通知 monitor；链接下一行保存输出文件名。
        "urls.txt": "".join(f"{item['url']}\n  out={item['filename']}\n" for item in items),
    }
    for name, content in files.items():
        path = outdir / name
        # 原子替换，避免 monitor 读取半份清单；下载链接仅允许当前用户读写。
        temporary = path.with_name(path.name + ".tmp")
        temporary.touch(mode=0o600, exist_ok=True)
        temporary.chmod(0o600)
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    size = sum(item["size"] for item in items)
    print(f"已保存 {len(items)} 个任务，合计 {size / 1e9:.2f} GB：{outdir / 'urls.txt'}")
    for item in items:
        print(item["filename"])


def completed(outdir, item):
    """文件是否已完整下载：存在、大小一致、无 aria2 控制文件。"""
    path = Path(outdir) / item["filename"]
    return (
        path.is_file()
        and path.stat().st_size == item["size"]
        and not Path(str(path) + ".aria2").exists()
    )


def download(outdir, jobs=4, connections=4):
    outdir = Path(outdir).expanduser().resolve()
    items = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    if not items:
        raise ValueError("下载清单为空，请先执行 fetch")
    # 已完成的文件不再下载：存在、大小一致、无 aria2 控制文件。
    pending = [item for item in items if not completed(outdir, item)]
    if not pending:
        print(f"全部 {len(items)} 个文件已完成")
        return
    executable = shutil.which("aria2c")
    if executable is None:
        raise FileNotFoundError("未找到 aria2c，请先安装 aria2")
    urls = "".join(f"{item['url']}\n  out={item['filename']}\n" for item in pending)
    subprocess.run(
        [
            executable,
            "-i", "-",
            "-d", str(outdir),
            "-c", "-j", str(jobs), "-x", str(connections), "-s", str(connections),
            "--auto-file-renaming=false",
            "--file-allocation=none",
            "--max-tries=3",
            "--retry-wait=5",
            "--connect-timeout=30",
            "--timeout=60",
        ],
        input=urls,
        text=True,
        check=True,
    )
    for item in pending:
        if not completed(outdir, item):
            raise ValueError(f"文件不完整：{item['filename']}；重新执行 download 可续传")
    print(f"下载完成，{len(pending)} 个文件大小校验通过")


def monitor(outdir, jobs=3, connections=4, interval=120):
    path = Path(outdir).expanduser() / "urls.txt"
    previous = None
    print(f"监听 {path}，每 {interval} 秒检查一次；Ctrl+C 停止", flush=True)
    while True:
        try:
            current = path.read_bytes() if path.is_file() else b""
            if current != previous:
                previous = current
                if current.strip():
                    print("清单已更新，开始下载", flush=True)
                    # 串行下载；期间收到的更新在本轮结束后处理。
                    download(outdir, jobs, connections)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f"下载失败，继续监听：{error}", flush=True)
        time.sleep(interval)


def job_year(api, job_id):
    """从任务元数据取年份，取不到时返回问号。"""
    try:
        years = api.get_remote(job_id).request.get("year") or []
    except Exception:
        return "?"
    return "-".join(sorted({str(year) for year in years})) or "?"


def status(limit=20, states=None):
    """列出 CDS 任务：序号、年份、状态、创建时间。"""
    api = cdsapi.Client(delete=False, quiet=True).client
    jobs = api.get_jobs(limit=limit, sortby="-created", status=states)._json_dict["jobs"]
    for number, job in enumerate(jobs, 1):
        print(
            f"[{number:2}] {job_year(api, job['jobID']):6} {job['status']:12} "
            f"{job['created'][:19]}"
        )
    # print(f"共 {len(jobs)} 个任务")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--outdir", default="data", help="清单及下载目录（默认 data）")
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument("--jobs", type=int, default=3, help="并行下载数（默认 3）")
    options.add_argument("--connections", type=int, default=4, help="单文件连接数（1–16）")

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", parents=[common], help="查询已完成任务，保存链接和文件名")
    fetch_parser.add_argument("--limit", type=int, default=999, help="任务数（默认 999，即全部）")
    fetch_parser.add_argument("--prefix", help="文件名前缀（默认：数据集 ID 加下划线）")
    fetch_parser.add_argument(
        "--subfix", "--suffix", dest="subfix", help="年份后的变量标注，如 _Ta；保留原扩展名"
    )
    commands.add_parser("download", parents=[common, options], help="按保存的清单下载，支持断点续传")
    monitor_parser = commands.add_parser("monitor", parents=[common, options], help="常驻监听清单变化，自动下载")
    monitor_parser.add_argument(
        "--interval", type=int, default=120, help="检查间隔秒数（默认 120，即 2 分钟）"
    )
    status_parser = commands.add_parser("status", help="列出任务状态")
    status_parser.add_argument("--limit", type=int, default=20, help="显示任务数（默认 20）")
    status_parser.add_argument(
        "--status", help="按状态过滤，逗号分隔，如 accepted,running"
    )
    args = parser.parse_args()
    for name in ("limit", "jobs", "interval"):
        value = getattr(args, name, None)
        if value is not None and value < 1:
            parser.error(f"--{name} 必须为正整数")
    if hasattr(args, "connections") and not 1 <= args.connections <= 16:
        parser.error("--connections 必须为 1–16")
    states = None
    if args.command == "status" and args.status:
        states = [state.strip() for state in args.status.split(",") if state.strip()]
        unknown = set(states) - set(STATES)
        if unknown:
            parser.error("未知状态：" + ",".join(sorted(unknown)))
    try:
        if args.command == "fetch":
            fetch(args.limit, args.outdir, args.prefix, args.subfix)
        elif args.command == "download":
            download(args.outdir, args.jobs, args.connections)
        elif args.command == "status":
            status(args.limit, states)
        else:
            monitor(args.outdir, args.jobs, args.connections, args.interval)
    except subprocess.CalledProcessError as error:
        parser.exit(error.returncode or 1, "aria2c 下载失败，可重新执行 download 续传\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "已停止，可重新执行 download 续传\n")


if __name__ == "__main__":
    main()
