import pytest
import requests

from sepg.download.transmission import (
    TransmissionRPC,
    add_torrent,
    apply_selection,
    torrent_get,
)


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 409:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


def test_call_succeeds_on_first_try(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    posts = []

    def fake_post(url, json, headers, timeout):
        posts.append((url, json, headers, timeout))
        return _FakeResponse(json_data={"result": "success", "arguments": {"ok": True}})

    monkeypatch.setattr(rpc.session, "post", fake_post)

    result = rpc.call("torrent-get", {"ids": [1]})

    assert result == {"result": "success", "arguments": {"ok": True}}
    assert len(posts) == 1
    assert posts[0][1] == {"method": "torrent-get", "arguments": {"ids": [1]}}


def test_call_without_arguments_omits_arguments_key(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    posts = []

    def fake_post(url, json, headers, timeout):
        posts.append(json)
        return _FakeResponse(json_data={"result": "success"})

    monkeypatch.setattr(rpc.session, "post", fake_post)

    rpc.call("torrent-start")

    assert posts[0] == {"method": "torrent-start"}


def test_call_retries_after_409_with_session_id(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(dict(headers))
        if len(calls) == 1:
            return _FakeResponse(status_code=409, headers={"X-Transmission-Session-Id": "abc123"})
        return _FakeResponse(json_data={"result": "success"})

    monkeypatch.setattr(rpc.session, "post", fake_post)

    result = rpc.call("torrent-get")

    assert result == {"result": "success"}
    assert len(calls) == 2
    assert calls[0] == {}
    assert calls[1] == {"X-Transmission-Session-Id": "abc123"}
    assert rpc.session_id == "abc123"


def test_call_reuses_cached_session_id_on_subsequent_calls(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    rpc.session_id = "cached-id"
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(dict(headers))
        return _FakeResponse(json_data={"result": "success"})

    monkeypatch.setattr(rpc.session, "post", fake_post)

    rpc.call("torrent-get")

    assert calls[0] == {"X-Transmission-Session-Id": "cached-id"}


def test_call_raises_when_409_but_no_session_id_header(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(status_code=409, headers={})

    monkeypatch.setattr(rpc.session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="no session id"):
        rpc.call("torrent-get")


def test_call_raises_runtime_error_on_non_success_result(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(json_data={"result": "error: duplicate torrent"})

    monkeypatch.setattr(rpc.session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="Transmission RPC failed"):
        rpc.call("torrent-add")


def test_call_retries_on_connection_error_then_succeeds(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    attempts = []

    def fake_post(url, json, headers, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("refused")
        return _FakeResponse(json_data={"result": "success"})

    monkeypatch.setattr(rpc.session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    result = rpc.call("torrent-get")

    assert result == {"result": "success"}
    assert len(attempts) == 3


def test_call_gives_up_after_five_connection_errors(monkeypatch):
    rpc = TransmissionRPC("http://transmission:9091/transmission/rpc")
    attempts = []

    def fake_post(url, json, headers, timeout):
        attempts.append(1)
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(rpc.session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(requests.ConnectionError):
        rpc.call("torrent-get")
    assert len(attempts) == 5


def test_torrent_get_returns_first_torrent(monkeypatch):
    rpc = TransmissionRPC("http://x/rpc")
    monkeypatch.setattr(
        rpc,
        "call",
        lambda method, arguments=None: {"arguments": {"torrents": [{"id": 7, "name": "t"}]}},
    )

    result = torrent_get(rpc, 7)

    assert result == {"id": 7, "name": "t"}


def test_torrent_get_raises_when_no_torrents_returned(monkeypatch):
    rpc = TransmissionRPC("http://x/rpc")
    monkeypatch.setattr(rpc, "call", lambda method, arguments=None: {"arguments": {"torrents": []}})

    with pytest.raises(RuntimeError, match="no torrents"):
        torrent_get(rpc, 7)


def test_add_torrent_returns_torrent_added_entry(monkeypatch, tmp_path):
    rpc = TransmissionRPC("http://x/rpc")
    seen = {}

    def fake_call(method, arguments=None):
        seen["method"] = method
        seen["arguments"] = arguments
        return {"arguments": {"torrent-added": {"id": 3}}}

    monkeypatch.setattr(rpc, "call", fake_call)

    result = add_torrent(rpc, b"raw-bytes", tmp_path)

    assert result == {"id": 3}
    assert seen["method"] == "torrent-add"
    assert seen["arguments"]["download-dir"] == str(tmp_path)
    assert seen["arguments"]["paused"] is True


def test_add_torrent_falls_back_to_duplicate_entry(monkeypatch, tmp_path):
    rpc = TransmissionRPC("http://x/rpc")
    monkeypatch.setattr(rpc, "call", lambda method, arguments=None: {"arguments": {"torrent-duplicate": {"id": 9}}})

    result = add_torrent(rpc, b"raw-bytes", tmp_path)

    assert result == {"id": 9}


def test_add_torrent_raises_when_neither_key_present(monkeypatch, tmp_path):
    rpc = TransmissionRPC("http://x/rpc")
    monkeypatch.setattr(rpc, "call", lambda method, arguments=None: {"arguments": {}})

    with pytest.raises(RuntimeError, match="torrent-add failed"):
        add_torrent(rpc, b"raw-bytes", tmp_path)


def test_apply_selection_marks_unwanted_and_wanted_files(monkeypatch):
    rpc = TransmissionRPC("http://x/rpc")
    calls = []
    monkeypatch.setattr(rpc, "call", lambda method, arguments=None: calls.append((method, arguments)))

    apply_selection(rpc, tid=5, total=4, wanted=[0, 2])

    assert calls == [
        ("torrent-set", {"ids": [5], "files-unwanted": [1, 3]}),
        ("torrent-set", {"ids": [5], "files-wanted": [0, 2]}),
    ]


def test_apply_selection_skips_unwanted_call_when_all_files_wanted(monkeypatch):
    rpc = TransmissionRPC("http://x/rpc")
    calls = []
    monkeypatch.setattr(rpc, "call", lambda method, arguments=None: calls.append((method, arguments)))

    apply_selection(rpc, tid=5, total=2, wanted=[0, 1])

    assert calls == [("torrent-set", {"ids": [5], "files-wanted": [0, 1]})]
