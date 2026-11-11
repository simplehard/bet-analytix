"""Triagem em massa das lojas descobertas (discover.py).

Para cada domínio guarda só as calças com bootcut/flare/bootleg — o resto é descartado para caber no disco.
  Shopify   -> /products.json (até 8 páginas)
  Nuvemshop -> sitemap; abre só produtos cujo slug tem boot-cut/flare/bootleg
  Outros    -> sitemap + JSON-LD, mesmo critério de slug

Saída: cache/mass/<domínio>.json  (status, plataforma, final_url, produtos filtrados)
Uso:   python mass_scan.py [--workers 16] [--limit N]
"""
import argparse
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

import scraper as S

HERE = os.path.dirname(os.path.abspath(__file__))
MASS = os.path.join(HERE, "cache", "mass")
KW = re.compile(r"boot[\s_-]?cul?t|flare|bootleg", re.I)
PANTS = re.compile(r"cal[cç]a|pants?|jeans?|denim|trouser|bootcut|flare", re.I)
NOTP = re.compile(r"dress|vestido|sweater|skirt|saia|blus|shirt|camis|top\b|cropped|body\b|macac|short|bermuda|"
                  r"jaqueta|jacket|bolsa|bag\b|sapato|shoe|bota\b|boot\b(?![\s-]?cut)|legging", re.I)


def keep(p):
    t = " ".join([p.get("title") or "", p.get("product_type") or "", " ".join(map(str, p.get("tags") or [])),
                  (p.get("description_text") or "")[:1500]])
    head = (p.get("title") or "") + " " + (p.get("product_type") or "")
    if NOTP.search(p.get("title") or ""):
        return False
    return bool(KW.search(t) and PANTS.search(head))


def scan(domain):
    out = os.path.join(MASS, domain + ".json")
    if os.path.exists(out):
        return json.load(open(out))
    res = {"domain": domain, "status": None, "platform": None, "final_url": None, "n_total": 0, "products": []}
    h = S.Http(f"https://{domain}")
    try:
        h._sleep()
        try:
            home = h.s.get(h.base + "/", timeout=S.TIMEOUT)
        except requests.RequestException as e:
            raise S.Offline(type(e).__name__)
        if home.status_code in (403, 429) or "challenge" in home.url:
            raise S.Blocked(f"HTTP {home.status_code}")
        if home.status_code >= 400:
            raise S.Offline(f"HTTP {home.status_code}")
        fu = urlparse(home.url)
        h.base = f"{fu.scheme}://{fu.netloc}"
        res["final_url"] = home.url
        if "/password" in fu.path:
            raise S.Offline("senha")
        h.load_robots()
        try:
            rob = h.s.get(h.base + "/robots.txt", timeout=S.TIMEOUT).text
            h._wild = S._wild_rules(rob) if "<html" not in rob[:500].lower() else []
        except requests.RequestException:
            h._wild = []
        prods = None
        r = h.get(h.base + "/products.json?limit=250&page=1")
        if r is not None and "json" in r.headers.get("content-type", ""):
            S_MAX = 8
            # reaproveita o leitor Shopify, limitando páginas
            prods = S.try_shopify(h, home.text)
            if prods is not None:
                res["platform"] = "shopify"
                prods = prods[:250 * S_MAX]
        if prods is None:
            res["platform"] = "nuvemshop" if S.is_nuvemshop(home.text) else "outro"
            urls = S.sitemap_urls(h, [h.base + "/sitemap.xml"])
            prod_urls = [u for u in urls if re.search(r"/(produtos?|products?|p)/[^/?#]+/?$|/p$", u)
                         and not re.search(r"^https?://[^/]+/[a-z]{2}/", u)]
            res["n_total"] = len(prod_urls)
            hits = [u for u in prod_urls if KW.search(u.rstrip("/").rsplit("/", 1)[-1])][:30]
            prods = S.scrape_product_pages(h, domain, hits, res["platform"])
        else:
            res["n_total"] = len(prods)
        res["products"] = [p for p in prods if keep(p)]
        res["status"] = "ok"
    except S.Blocked as e:
        res["status"], res["error"] = "bloqueada", str(e)
    except S.Offline as e:
        res["status"], res["error"] = "fora do ar", str(e)
    except Exception as e:
        res["status"], res["error"] = "erro", f"{type(e).__name__}: {str(e)[:120]}"
    json.dump(res, open(out, "w"), ensure_ascii=False)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    os.makedirs(MASS, exist_ok=True)
    disc = json.load(open(os.path.join(HERE, "cache", "discovered.json")))
    known = {b["domain"] for b in json.load(open(os.path.join(HERE, "cache", "brands.json"))) if b["domain"]}
    todo = sorted(d for d in disc if d not in known)
    if a.limit:
        todo = todo[:a.limit]
    lock, n, hits = threading.Lock(), 0, 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(scan, d): d for d in todo}
        for f in as_completed(futs):
            r = f.result()
            with lock:
                n += 1
                if r["products"]:
                    hits += 1
                    print(f"[{n}/{len(todo)}] HIT {r['domain']} ({r['platform']}): "
                          + " | ".join(p["title"][:40] for p in r["products"][:4]), flush=True)
                elif n % 100 == 0:
                    print(f"[{n}/{len(todo)}] lojas com bootcut/flare até agora: {hits}", flush=True)


if __name__ == "__main__":
    main()
