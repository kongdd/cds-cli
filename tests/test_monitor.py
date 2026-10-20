import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests

import cdsapi


@pytest.fixture
def monitor(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "examples" / "monitor-progress.py"
    namespace = runpy.run_path(str(script))
    state_file = tmp_path / "tasks.json"
    api = SimpleNamespace(get_remote=Mock(return_value=SimpleNamespace(status="running")))
    queue = SimpleNamespace(state_file=state_file, client=SimpleNamespace(client=api))
    monkeypatch.setattr(cdsapi, "BatchClient", Mock(return_value=queue))
    sleep = Mock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(namespace["time"], "sleep", sleep)
    return namespace["monitor"], state_file, api, sleep


def test_monitor_is_read_only(monitor, capsys):
    watch, state_file, api, sleep = monitor
    tasks = [
        {"request_id": str(index), "target": f"file{index}.grib", "state": state}
        for index, state in enumerate(["submitted", "downloaded", "download_failed", "failed"])
    ]
    state_file.write_text(json.dumps(tasks))
    with pytest.raises(KeyboardInterrupt):
        watch(state_file)
    api.get_remote.assert_called_once_with("0")
    sleep.assert_called_once_with(120)
    assert json.loads(state_file.read_text()) == tasks
    output = capsys.readouterr().out
    for state in ("running", "downloaded", "download_failed", "failed"):
        assert state in output
    for task in tasks:
        assert task["target"] in output


def test_monitor_reloads_queue(monitor, capsys):
    watch, state_file, api, sleep = monitor
    task = {"request_id": "1", "target": "one.grib", "state": "submitted"}
    state_file.write_text(json.dumps([task]))

    def update_queue(seconds):
        task["state"] = "downloaded"
        state_file.write_text(json.dumps([task]))
        sleep.side_effect = KeyboardInterrupt

    sleep.side_effect = update_queue
    with pytest.raises(KeyboardInterrupt):
        watch(state_file)
    api.get_remote.assert_called_once_with("1")
    assert sleep.call_args_list == [call(120), call(120)]
    assert "downloaded" in capsys.readouterr().out


def test_monitor_continues_after_query_error(monitor, capsys):
    watch, state_file, api, _ = monitor
    tasks = [
        {"request_id": str(index), "target": f"file{index}.grib", "state": "submitted"}
        for index in range(2)
    ]
    state_file.write_text(json.dumps(tasks))
    api.get_remote.side_effect = [
        requests.ConnectionError("offline"),
        SimpleNamespace(status="successful"),
    ]
    with pytest.raises(KeyboardInterrupt):
        watch(state_file)
    assert api.get_remote.call_count == 2
    output = capsys.readouterr().out
    assert "查询失败: offline" in output
    assert "successful" in output
