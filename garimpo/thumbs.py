"""Baixa a 1ª imagem de cada calça e gera miniaturas WebP pequenas em cache/thumbs/ (para embutir no HTML)."""
import hashlib
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from PIL import Image

import lista_md as L
from scraper import UA

THUMBS = os.path.join(L.A.CACHE, "thumbs")
W = 240  # largura em px


def thumb_path(url):
    return os.path.join(THUMBS, hashlib.sha1(url.encode()).hexdigest()[:16] + ".webp")


def fetch(url):
    out = thumb_path(url)
    if os.path.exists(out):
        return True
    if url.startswith("//"):
        url = "https:" + url
    try:
        time.sleep(0.3)
        r = requests.get(url, headers={"User-Agent": UA, "Referer": f"https://{urlparse(url).hostname}/"}, timeout=15)
        if r.status_code != 200:
            return False
        im = Image.open(io.BytesIO(r.content))
        im = im.convert("RGB")
        h = int(im.height * W / im.width)
        im = im.resize((W, h), Image.LANCZOS)
        im.save(out, "WEBP", quality=55, method=6)
        return True
    except Exception:
        return False


def main():
    os.makedirs(THUMBS, exist_ok=True)
    rows, _, _ = L.collect()
    urls = sorted({r["img"] for r in rows if r.get("img")})
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(fetch, urls))
    print(f"{sum(res)}/{len(urls)} miniaturas")


if __name__ == "__main__":
    main()
