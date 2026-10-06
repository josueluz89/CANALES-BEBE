#!/usr/bin/env python3
"""Genera tummtv.m3u con los canales abiertos de TUMM TV+ (web.tumm.tv).

Flujo: demo-login anonimo -> lista de canales -> streams por canal -> M3U.
Las URLs de stream llevan tokens de corta duracion; este script esta pensado
para correrse por cron/CI y regenerar el archivo.

Logos: s3.tumm.tv los sirve como application/octet-stream y muchos
reproductores los rechazan. Se guardan en logos/<tvg-id>.png dentro del
repo y el M3U apunta a jsDelivr (Content-Type image/png correcto).
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

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LOGOS_DIR = os.path.join(REPO_DIR, "logos")
JSDELIVR_LOGOS = "https://cdn.jsdelivr.net/gh/josueluz89/CANALES-BEBE@main/logos"


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


def logo_local(channel_id, s3_url):
    """Devuelve la URL jsDelivr del logo. Descarga y guarda el PNG si falta."""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    dest = os.path.join(LOGOS_DIR, f"{channel_id}.png")
    if os.path.exists(dest) and os.path.getsize(dest) > 100:
        return f"{JSDELIVR_LOGOS}/{channel_id}.png"
    if not s3_url:
        return ""
    tmp = dest + ".tmp"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "25", "-o", tmp, s3_url],
            capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 100:
            with open(tmp, "rb") as f:
                head = f.read(4)
            if head[:4] == b"\x89PNG":
                os.rename(tmp, dest)
                return f"{JSDELIVR_LOGOS}/{channel_id}.png"
            if head[:2] == b"\xff\xd8":
                # JPEG -> convertir a PNG para unificar extension
                try:
                    from PIL import Image
                    Image.open(tmp).save(dest)
                    os.remove(tmp)
                    return f"{JSDELIVR_LOGOS}/{channel_id}.png"
                except ImportError:
                    pass
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:  # noqa: BLE001
        pass
    # Fallback: URL original (puede no cargar en algunos reproductores)
    return s3_url


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
        s3_logo = c.get("landscapeImage") or c.get("image") or ""
        logo = logo_local(c["id"], s3_logo)
        lines.append(
            f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-logo="{logo}" '
            f'group-title="Costa Rica",{title}'
        )
        lines.append(url)
        ok += 1
    print(f"{ok} canales con stream")

    # Fusionar listas estáticas adicionales: van por el mismo raw que la app
    # ya trae configurado (tummtv.m3u), así llegan solas sin agregar plugins.
    for extra in ("listas/vampitv-verificado.m3u", "listas/24-7-maraton.m3u"):
        p = os.path.join(REPO_DIR, extra)
        if not os.path.exists(p):
            print(f"  ! no existe {extra}, se omite")
            continue
        n = 0
        with open(p, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#EXTM3U"):
                    continue
                lines.append(s)
                if s.startswith("#EXTINF"):
                    n += 1
        print(f"  + {extra}: {n} canales")

    out = os.path.join(REPO_DIR, "tummtv.m3u")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Lista generada: {stamp}\n")
        f.write("\n".join(lines) + "\n")
    print("escrito:", out)


if __name__ == "__main__":
    main()
