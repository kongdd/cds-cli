#!/usr/bin/env python
"""提交 ERA5 任务但不下载，任务完成后可用 cds_jobs.py 取回。"""
import json
from pathlib import Path

import cdsapi

request = {
    "product_type": ["reanalysis"],
    "variable": ["2m_temperature"],
    "month": [f"{month:02d}" for month in range(1, 13)],
    "day": [f"{day:02d}" for day in range(1, 32)],
    "time": [f"{hour:02d}:00" for hour in range(24)],
    "data_format": "netcdf",
    "download_format": "unarchived",
}

# wait_until_complete=False：提交后立即返回，不等待也不下载。
client = cdsapi.Client(wait_until_complete=False, delete=False)
submitted = []

# YEARS = range(1940, 1948)
# YEARS = range(1941, 1943)
for year in YEARS:
    remote = client.retrieve(
        "reanalysis-era5-single-levels", dict(request, year=[str(year)])
    )
    submitted.append({"year": year, "request_id": remote.request_id})
    print(year, remote.request_id, flush=True)

target = Path("submitted.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(submitted, indent=2) + "\n", encoding="utf-8")
print("已提交", len(submitted), "个任务：", target)
