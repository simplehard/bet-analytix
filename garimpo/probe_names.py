"""Dado um nome de marca, tenta domínios comuns e confirma se é loja online.

Uso: python probe_names.py nome1 nome2 ...   (ou dominio.com.br explícito)
Imprime: nome -> domínio (plataforma) | título
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from scraper import UA

PLAT = [("nuvemshop", r"nuvemshop|mitiendanube|lojavirtualnuvem|LS\.store|data-store=\""), ("shopify", r"cdn\.shopify|Shopify\.shop"),
        ("vtex", r"vtex"), ("tray", r"tray(commerce)?\.com|commercesuite"), ("woocommerce", r"woocommerce"),
        ("wix", r"wixstatic|wix\.com"), ("yampi", r"yampi"), ("loja integrada", r"lojaintegrada"),
        ("wbuy", r"wbuy"), ("magazord", r"magazord")]
PARKED = re.compile(r"for sale|à venda|lander|parked|domain|godaddy|hostinger|registro\.br|em construção|coming soon",
                    re.I)


def candidates(name):
    if "." in name:
        return [name]
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    out = []
    for pat in ("{n}.com.br", "{n}.com", "use{n}.com.br", "{n}oficial.com.br", "{n}store.com.br", "{n}studio.com.br",
                "{n}studios.com.br", "{n}brand.com.br", "{n}.store", "{n}.art.br", "{n}clothing.com.br", "loja{n}.com.br",
                "{n}co.com.br", "{n}.co"):
        out.append(pat.format(n=n))
    return out


def check(dom):
    try:
        r = requests.get(f"https://{dom}/", headers={"User-Agent": UA}, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200 or len(r.text) < 3000:
        return None
    t = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
    title = re.sub(r"\s+", " ", t.group(1)).strip()[:70] if t else ""
    if PARKED.search(title) or ("/lander" in r.text[:500]):
        return None
    plat = next((p for p, rx in PLAT if re.search(rx, r.text, re.I)), "?")
    final = re.sub(r"^https?://(www\.)?", "", r.url).split("/")[0]
    return final, plat, title


def probe(name):
    for d in candidates(name):
        res = check(d)
        if res and res[1] != "?":
            return name, res
    return name, None


if __name__ == "__main__":
    with ThreadPoolExecutor(6) as ex:
        for name, res in ex.map(probe, sys.argv[1:]):
            print(f"{name:22} -> " + (f"{res[0]} ({res[1]}) | {res[2]}" if res else "—"), flush=True)
