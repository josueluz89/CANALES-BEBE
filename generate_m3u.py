#!/usr/bin/env python3
"""Genera tummtv.m3u con los canales abiertos de TUMM TV+ (web.tumm.tv).

Flujo: demo-login anonimo -> lista de canales -> streams por canal -> M3U.
Las URLs de stream llevan tokens de corta duracion; este script esta pensado
para correrse por cron/CI y regenerar el archivo.
"""
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

BASE = "https://web.tumm.tv"
OPERATOR_ID = "1fb1b4c7-dbd9-469e-88a2-c207dc195869"
DEVICE_ID = os.environ.get("TUMM_DEVICE_ID", "m3u-bebe-001")
COMMON = {
    "operator_id": OPERATOR_ID,
    "device_id": DEVICE_ID,
    "os": "android",
    "platform": "tv",
    "language": "es",
    "density": "320",
    "client": "browser",
}
HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}


def api(method, path, params=None, data=None, token=None, retries=3):
    # Se usa curl: el servidor corta las conexiones de urllib en /player/channels
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    cmd = ["curl", "-s", "--max-time", "60", "-X", method, url,
           "-H", "Content-Type: application/json",
           "-H", "User-Agent: Mozilla/5.0"]
    if token:
        cmd += ["-H", "Authorization: Bearer " + token]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    last = None
    for _ in range(retries):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if r.returncode != 0:
                last = RuntimeError(r.stderr[:200] or f"curl salio {r.returncode}")
                continue
            return json.loads(r.stdout)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def main():
    print("demo-login anonimo...")
    login = api("POST", "/api/authorization/demo-login",
                data={**COMMON, "density": COMMON["density"]})
    if login.get("code") != 1:
        sys.exit("demo-login fallo: " + json.dumps(login)[:300])
    token = login["content"]["token"]["access_token"]

    print("pidiendo canales...")
    ch = api("GET", "/api/player/channels", params=COMMON, token=token)
    if ch.get("code") != 1:
        sys.exit("channels fallo: " + json.dumps(ch)[:300])
    channels = ch["content"]["data"]
    print(f"{len(channels)} canales")

    lines = ["#EXTM3U"]
    ok = 0
    for c in channels:
        title = c.get("title", "Sin nombre")
        try:
            st = api("GET", "/api/player/streams",
                     params={**COMMON, "media_id": c["id"]}, token=token)
            items = st.get("content") or []
            url = items[0]["src"]["url"] if items else None
        except Exception as e:  # noqa: BLE001
            print(f"  x {title}: {e}")
            url = None
        if not url:
            print(f"  - {title}: sin stream")
            continue
        logo = c.get("landscapeImage") or c.get("image") or ""
        lines.append(
            f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-logo="{logo}" '
            f'group-title="Costa Rica",{title}'
        )
        lines.append(url)
        ok += 1
    print(f"{ok} canales con stream")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tummtv.m3u")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Lista generada: {stamp}\n")
        f.write("\n".join(lines) + "\n")
    print("escrito:", out)


if __name__ == "__main__":
    main()
