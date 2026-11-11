"""Monta a lista de lojas: diretório Brazil Made It (Supabase público, somente leitura) + extras.

Saída: cache/brands.json
"""
import json
import os
import re
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

SUPABASE_URL = "https://dnmcwpxzqpuyeanblcba.supabase.co"
# chave "anon" pública embutida no bundle JS do site (/assets/index-*.js)
SUPABASE_ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRubWN3cHh6cXB1eWVhbmJsY2JhIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3Njg2NDYwMjYsImV4cCI6MjA4NDIyMjAyNn0.6fQkv2lQB8xMcwbdtcNT3MvQxbhgh49qWmsNSHvesDM"
)

IGNORAR = {
    "c&a", "renner", "riachuelo", "hering", "zattini", "marisa", "torra torra", "havaianas", "animale",
    "farm rio", "osklen", "reserva", "colcci", "viga", "wayward",
}

EXTRAS = [
    "nephew.com.br", "amnidevt.com", "mondepars.com", "singa.com.br", "doughboy.com.br", "kardiganstudios.net",
    "recurva.com.br", "studiosecta.com.br", "darklingstudios.com.br", "thedustcompany.com.br",
    "quadrocreations.com", "hardjeanssanto.com", "egho.com.br", "cursed.com.br", "spirandellilaboratories.com",
    "welcomesunnygarments.com.br",
    # achadas em busca na web (fora do diretório)
    "shui.com.br", "strut.com.br", "desertdenimbrasil.com.br", "jeandarrot.com.br",
    # bola de neve (collabs citadas em títulos de produtos)
    "allglory.com.br", "anticool.com.br", "cyshimi.com",
    # listas editoriais (Steal The Look, Elle, Hypebeast…) + teste de domínios por nome
    "ukio.art.br", "bosycoys.com", "damagewip.com.br", "dengo.club", "eloemcomum.com", "ganguedocaramelo.com.br",
    "howiseethings.com.br", "quembh.com.br", "cacete.co", "normando.co", "dendezeiro.com.br",
    "sardegnasartoria.com.br", "kietzo.com", "inttui.com.br",
]


def norm_domain(url):
    if not url:
        return None
    u = url.strip().lower()
    if u in ("off-line", "offline", "-"):
        return None
    u = re.sub(r"^h+t+p+s*:?/+", "", u)  # corrige "httpps://"
    host = urlparse("http://" + u).hostname or ""
    host = host.removeprefix("www.")
    return host if "." in host else None


def fetch_directory():
    raw_path = os.path.join(CACHE, "brands_raw.json")
    if os.path.exists(raw_path):
        return json.load(open(raw_path))
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/brands?select=*&order=name",
        headers={"apikey": SUPABASE_ANON, "Authorization": f"Bearer {SUPABASE_ANON}", "Range": "0-999"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    json.dump(data, open(raw_path, "w"), ensure_ascii=False, indent=1)
    return data


def build():
    os.makedirs(CACHE, exist_ok=True)
    raw = fetch_directory()
    brands, seen_handles = [], set()
    for b in raw:
        h = (b.get("handle") or "").strip().lower()
        if h in seen_handles:
            continue  # duplicata (ex.: Viot)
        seen_handles.add(h)
        dom = norm_domain(b.get("shop_url"))
        status = None
        if b["name"].strip().lower() in IGNORAR:
            status = "ignorada (grande varejo / não vende calça)"
        elif not dom:
            status = "só Instagram"
        brands.append({
            "name": b["name"].strip(), "instagram": b.get("url") or "", "handle": b.get("handle"),
            "region": b.get("region"), "shop_url": b.get("shop_url"), "domain": dom,
            "source": "brazilmadeit", "pre_status": status,
        })
    doms = {b["domain"] for b in brands if b["domain"]}
    for d in EXTRAS:
        if d in doms:
            continue
        doms.add(d)
        brands.append({"name": d.split(".")[0], "instagram": "", "handle": "", "region": "", "shop_url": "https://" + d,
                       "domain": d, "source": "extra", "pre_status": None})
    # lojas repetidas (mesmo domínio para duas marcas) — varre só uma vez
    seen = set()
    for b in brands:
        if b["domain"] and not b["pre_status"]:
            if b["domain"] in seen:
                b["pre_status"] = "duplicada"
            seen.add(b["domain"])
    json.dump(brands, open(os.path.join(CACHE, "brands.json"), "w"), ensure_ascii=False, indent=1)
    return raw, brands


if __name__ == "__main__":
    raw, brands = build()
    from collections import Counter
    print("registros no diretório:", len(raw))
    print("marcas únicas do diretório:", sum(1 for b in brands if b["source"] == "brazilmadeit"))
    print("extras adicionadas:", sum(1 for b in brands if b["source"] == "extra"))
    print(Counter(b["pre_status"] or "a varrer" for b in brands))
