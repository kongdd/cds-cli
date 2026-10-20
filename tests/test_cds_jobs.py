import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import cdsapi


@pytest.fixture
def jobs():
    path = Path(__file__).resolve().parents[1] / "ERA5" / "cds_jobs.py"
    spec = importlib.util.spec_from_file_location("cds_jobs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "year,prefix,subfix,extension,expected",
    [
        (["2025"], None, None, ".zip", "era5_2025.zip"),
        (2025, "ERA5_", "_Ta", ".nc", "ERA5_2025_Ta.nc"),
        ("2025", "ERA5_", "_Ta", ".nc.zip", "ERA5_2025_Ta.nc.zip"),
        (["2025", "2024"], "", "", ".grib", "2024-2025.grib"),
        (None, None, None, "", "era5_unknown-year.bin"),
    ],
)
def test_filename(jobs, year, prefix, subfix, extension, expected):
    url = "https://example.test/cache" + extension + "?token=test"
    assert jobs.task_filename("era5", {"year": year}, url, prefix, subfix) == expected


@pytest.fixture
def api(monkeypatch):
    client = Mock()
    client.client.get_jobs.return_value.request_ids = ["existing-job"]
    client.client.get_remote.return_value = SimpleNamespace(
        collection_id="era5",
        request={"year": ["2025"]},
        get_results=Mock(
            return_value=SimpleNamespace(location="https://example.test/cache.zip", content_length=4)
        ),
    )
    monkeypatch.setattr(cdsapi, "Client", Mock(return_value=client))
    return client


def test_fetch_only_queries_existing_jobs(jobs, api, tmp_path):
    jobs.fetch(3, tmp_path, "ERA5_", "_Ta")
    cdsapi.Client.assert_called_once_with(delete=False, quiet=True)
    api.client.get_jobs.assert_called_once_with(limit=3, sortby="-created", status="successful")
    api.client.get_remote.assert_called_once_with("existing-job")
    api.retrieve.assert_not_called()
    api.client.submit.assert_not_called()
    assert (tmp_path / "urls.txt").read_text() == (
        "https://example.test/cache.zip\n  out=ERA5_2025_Ta.zip\n"
    )
    item = json.loads((tmp_path / "manifest.json").read_text())[0]
    assert item["filename"] == "ERA5_2025_Ta.zip"
    assert item["dataset"] == "era5" and item["request"]["year"] == ["2025"]
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())


def test_fetch_empty_leaves_existing_files_unchanged(jobs, api, tmp_path):
    api.client.get_jobs.return_value.request_ids = []
    (tmp_path / "urls.txt").write_text("keep")
    with pytest.raises(ValueError, match="没有可下载"):
        jobs.fetch(3, tmp_path)
    assert (tmp_path / "urls.txt").read_text() == "keep"


def test_fetch_rejects_duplicate_names(jobs, api, tmp_path):
    api.client.get_jobs.return_value.request_ids = ["job1", "job2"]
    with pytest.raises(ValueError, match="文件名重复"):
        jobs.fetch(3, tmp_path)
    assert not (tmp_path / "urls.txt").exists()


@pytest.fixture
def downloads(jobs, tmp_path, monkeypatch):
    item = {
        "filename": "ERA5_2025_Ta.zip",
        "size": 4,
        "url": "https://example.test/cache.zip",
    }
    (tmp_path / "manifest.json").write_text(json.dumps([item]))
    (tmp_path / "urls.txt").write_text("https://example.test/cache.zip\n  out=ERA5_2025_Ta.zip\n")
    monkeypatch.setattr(jobs.shutil, "which", lambda name: "/bin/aria2c")
    command = Mock()
    monkeypatch.setattr(jobs.subprocess, "run", command)
    return tmp_path / item["filename"], command


def test_run_uses_saved_list_without_cds_client(jobs, downloads, tmp_path, monkeypatch):
    target, command = downloads
    command.side_effect = lambda *args, **kwargs: target.write_bytes(b"data")
    client = Mock(side_effect=AssertionError("run must not connect to CDS"))
    monkeypatch.setattr(cdsapi, "Client", client)
    jobs.download(tmp_path, jobs=2, connections=5)
    args = command.call_args.args[0]
    assert args[args.index("-i") + 1] == "-"
    assert args[args.index("-d") + 1] == str(tmp_path)
    assert args[args.index("-j") + 1] == "2"
    assert args[args.index("-x") + 1] == "5"
    assert "-c" in args and "--auto-file-renaming=false" in args
    assert command.call_args.kwargs["check"] is True
    assert command.call_args.kwargs["input"].startswith("https://example.test/cache.zip")
    client.assert_not_called()


def test_download_skips_completed_files(jobs, downloads, tmp_path):
    target, command = downloads
    target.write_bytes(b"data")
    jobs.download(tmp_path)
    command.assert_not_called()


@pytest.mark.parametrize("state", ["missing", "wrong-size", "partial"])
def test_run_detects_incomplete_files(jobs, downloads, tmp_path, state):
    target, _ = downloads
    if state != "missing":
        target.write_bytes(b"data" if state == "partial" else b"bad")
    if state == "partial":
        Path(str(target) + ".aria2").touch()
    with pytest.raises(ValueError, match="文件不完整"):
        jobs.download(tmp_path)


def test_run_requires_aria2(jobs, downloads, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="aria2c"):
        jobs.download(tmp_path)


def test_monitor_downloads_on_change(jobs, tmp_path, monkeypatch):
    (tmp_path / "urls.txt").write_text("https://example.test/a.zip\n  out=a.zip\n")
    calls = []
    monkeypatch.setattr(jobs, "download", lambda *args: calls.append(args))
    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        jobs.monitor(tmp_path)
    assert len(calls) == 1


def test_monitor_ignores_unchanged_list(jobs, tmp_path, monkeypatch):
    (tmp_path / "urls.txt").write_text("https://example.test/a.zip\n  out=a.zip\n")
    calls = []

    def fake_run(*args):
        calls.append(args)
        raise KeyboardInterrupt

    monkeypatch.setattr(jobs, "download", fake_run)
    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        jobs.monitor(tmp_path)
    assert len(calls) == 1


def test_status_lists_jobs_with_year(jobs, tmp_path, monkeypatch, capsys):
    api = Mock()
    api.client.get_jobs.return_value._json_dict = {
        "jobs": [
            {"jobID": "job-1", "status": "running", "created": "2026-01-01T00:00:00"},
            {"jobID": "job-2", "status": "successful", "created": "2026-01-02T00:00:00"},
        ]
    }
    api.client.get_remote.side_effect = lambda job_id: SimpleNamespace(
        request={"year": ["2024"]}
    )
    monkeypatch.setattr(cdsapi, "Client", Mock(return_value=api))
    jobs.status(limit=5)
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].split() == ["[", "1]", "2024", "running", "2026-01-01T00:00:00"]
    assert lines[1].split() == ["[", "2]", "2024", "successful", "2026-01-02T00:00:00"]
    api.client.get_jobs.assert_called_once_with(limit=5, sortby="-created", status=None)


def test_status_filters_by_state(jobs, tmp_path, monkeypatch):
    api = Mock()
    api.client.get_jobs.return_value._json_dict = {"jobs": []}
    monkeypatch.setattr(cdsapi, "Client", Mock(return_value=api))
    jobs.status(limit=5, states=["accepted", "running"])
    api.client.get_jobs.assert_called_once_with(
        limit=5, sortby="-created", status=["accepted", "running"]
    )


def test_status_without_local_files(jobs, tmp_path, monkeypatch, capsys):
    api = Mock()
    api.client.get_jobs.return_value._json_dict = {
        "jobs": [{"jobID": "job-2", "status": "successful", "created": "2026-01-02T00:00:00"}]
    }
    api.client.get_remote.side_effect = RuntimeError("no metadata")
    monkeypatch.setattr(cdsapi, "Client", Mock(return_value=api))
    jobs.status(limit=5)
    assert "successful" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        ["fetch", "--limit", "0"],
        ["download", "--jobs", "0"],
        ["download", "--connections", "17"],
        ["monitor", "--interval", "0"],
    ],
)
def test_invalid_cli(jobs, monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["cds_jobs"] + arguments)
    with pytest.raises(SystemExit) as error:
        jobs.main()
    assert error.value.code == 2
