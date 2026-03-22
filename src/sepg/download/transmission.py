import base64
import time
from pathlib import Path
from typing import Any

import requests


class TransmissionRPC:
    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
        self.session_id: str | None = None

    def call(self, method: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"method": method}
        if arguments:
            payload["arguments"] = arguments

        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(5):
            if attempt > 0:
                time.sleep(2 ** (attempt - 1))

            try:
                headers: dict[str, str] = {}
                if self.session_id:
                    headers["X-Transmission-Session-Id"] = self.session_id

                r = self.session.post(self.url, json=payload, headers=headers, timeout=60)

                if r.status_code == 409:
                    sid = r.headers.get("X-Transmission-Session-Id")
                    if not sid:
                        raise RuntimeError("Transmission RPC 409 but no session id")
                    self.session_id = sid
                    r = self.session.post(
                        self.url,
                        json=payload,
                        headers={"X-Transmission-Session-Id": sid},
                        timeout=60,
                    )

                r.raise_for_status()
                data = r.json()
                if data.get("result") != "success":
                    raise RuntimeError(f"Transmission RPC failed: {data.get('result')}")
                return data

            except requests.RequestException as e:
                last_exc = e

        raise last_exc


def torrent_get(rpc: TransmissionRPC, tid: int) -> dict[str, Any]:
    res = rpc.call(
        "torrent-get",
        {
            "ids": [tid],
            "fields": [
                "id",
                "name",
                "downloadDir",
                "percentDone",
                "rateDownload",
                "files",
                "fileStats",
            ],
        },
    )
    torrents = res.get("arguments", {}).get("torrents", [])
    if not torrents:
        raise RuntimeError("torrent-get returned no torrents")
    return torrents[0]


def add_torrent(rpc: TransmissionRPC, torrent_bytes: bytes, out_dir: Path) -> dict[str, Any]:
    b64 = base64.b64encode(torrent_bytes).decode("ascii")
    res = rpc.call(
        "torrent-add",
        {"download-dir": str(out_dir), "paused": True, "metainfo": b64},
    )
    args = res.get("arguments", {})
    t = args.get("torrent-added") or args.get("torrent-duplicate")
    if not t:
        raise RuntimeError("torrent-add failed")
    return t


def apply_selection(rpc: TransmissionRPC, tid: int, total: int, wanted: list[int]) -> None:
    wanted_set = set(wanted)
    unwanted = [i for i in range(total) if i not in wanted_set]
    if unwanted:
        rpc.call("torrent-set", {"ids": [tid], "files-unwanted": unwanted})
    rpc.call("torrent-set", {"ids": [tid], "files-wanted": wanted})
