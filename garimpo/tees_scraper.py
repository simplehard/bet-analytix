"""Coleta camisetas das lojas cujo cache só tem calças (Nuvemshop / genérico) e de varejistas VTEX.

Saída: cache/tees/<domínio>.json  (mesmo formato de cache/stores)
Uso:   python tees_scraper.py [--workers 8] [--retail-only]
"""
import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

import scraper as S

HERE = os.path.dirname(os.path.abspath(__file__))
TEES = os.path.join(HERE, "cache", "tees")
SLUG = re.compile(r"camiseta|camisa-basica|\btee\b|-tee|tee-|t-?shirt|basica|basic", re.I)
PRIO = re.compile(r"basica|basic|lisa|plain|essential|blank|heavy|pima|preto|preta|black|chumbo|grafite|cinza|washed|"
                  r"lavad|stone|charcoal", re.I)
MAX_PAGES = 70

# varejo / marcas de básicos (VTEX tem API pública de catálogo, somente leitura)
RETAIL = ["hering.com.br", "cea.com.br", "riachuelo.com.br", "usereserva.com", "youcom.com.br", "lojasrenner.com.br",
          "insiderstore.com.br", "basico.com", "aramis.com.br", "foxtonbrasil.com.br", "johnjohndenim.com.br",
          "ellus.com", "colcci.com.br", "oficinareserva.com.br", "richards.com.br", "malwee.com.br",
          "marisa.com.br", "pullandbear.com", "zara.com", "levi.com.br", "osklen.com.br", "calvinklein.com.br",
          "tommy.com.br", "lacoste.com.br", "brooksfield.com.br", "vrcollezione.com.br", "acostamento.com.br",
          "forum.com.br", "tng.com.br"]
VTEX_TERMS = ["camiseta basica masculina", "camiseta masculina lisa", "camiseta preta masculina",
              "camiseta cinza masculina", "camiseta estonada", "camiseta lavada", "camiseta basica", "t-shirt basica",
              "camiseta chumbo", "camiseta grafite", "camiseta preto lavado", "camiseta stone", "camiseta pima",
              "camiseta essential", "camiseta regular masculina", "camiseta masculina preta"]


def tees_from_sitemap(h, domain):
    urls = S.sitemap_urls(h, [h.base + "/sitemap.xml"])
    prod = [u for u in urls if re.search(r"/(produtos?|products?|p)/[^/?#]+/?$|/p$", u)
            and not re.search(r"^https?://[^/]+/[a-z]{2}/", u)]
    cand = [u for u in prod if SLUG.search(u.rstrip("/").rsplit("/", 1)[-1])]
    cand.sort(key=lambda u: 0 if PRIO.search(u) else 1)
    return S.scrape_product_pages(h, domain, cand[:MAX_PAGES], "tees"), len(prod)


def vtex_tees(h):
    seen = {}
    for term in VTEX_TERMS:
        for frm in range(0, 150, 50):
            r = h.get(f"{h.base}/api/catalog_system/pub/products/search?ft={requests.utils.quote(term)}"
                      f"&_from={frm}&_to={frm + 49}")
            if not r:
                break
            try:
                data = r.json()
            except ValueError:
                break
            if not isinstance(data, list) or not data:
                break
            for p in data:
                vs = []
                for it in p.get("items") or []:
                    co = ((it.get("sellers") or [{}])[0].get("commertialOffer") or {})
                    vs.append({"title": it.get("name"), "options": [it.get("name")], "price": co.get("Price"),
                               "compare_at": co.get("ListPrice") if co.get("ListPrice") != co.get("Price") else None,
                               "available": (co.get("AvailableQuantity") or 0) > 0})
                specs = " ".join(f"{k}: {', '.join(map(str, p.get(k) or []))}" for k in (p.get("allSpecifications") or []))
                imgs = ((p.get("items") or [{}])[0].get("images") or [{}])
                link = p.get("link") or ""
                seen[link] = {"url": link, "title": p.get("productName", ""),
                              "description_html": (p.get("description") or "") + "<p>" + specs + "</p>",
                              "description_text": re.sub(r"<[^>]+>", " ", p.get("description") or "") + " " + specs,
                              "tags": p.get("categories") or [], "product_type": "", "option_names": [],
                              "variants": vs, "price": min([v["price"] for v in vs if v["price"]] or [0]) or None,
                              "compare_at": max([v["compare_at"] or 0 for v in vs] or [0]) or None,
                              "image": imgs[0].get("imageUrl"), "extra_images": []}
            if len(data) < 50:
                break
    return list(seen.values()) if seen else None


def scrape(domain, retail=False):
    out = os.path.join(TEES, domain + ".json")
    if os.path.exists(out):
        return json.load(open(out))
    res = {"domain": domain, "status": None, "platform": None, "products": [], "error": None, "retail": retail}
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
        h.load_robots()
        try:
            rob = h.s.get(h.base + "/robots.txt", timeout=S.TIMEOUT).text
            h._wild = S._wild_rules(rob) if "<html" not in rob[:500].lower() else []
        except requests.RequestException:
            h._wild = []
        prods = None
        if retail:
            prods = S.try_shopify(h, home.text)
            if prods is not None:
                res["platform"] = "shopify"
            else:
                prods = vtex_tees(h)
                if prods is not None:
                    res["platform"] = "vtex"
        if prods is None:
            prods, _ = tees_from_sitemap(h, domain)
            res["platform"] = "sitemap"
        res["products"] = prods
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
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--retail-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(TEES, exist_ok=True)
    todo = [(d, True) for d in RETAIL]
    if not a.retail_only:
        import glob
        for f in glob.glob(os.path.join(HERE, "cache", "stores", "*.json")):
            s = json.load(open(f))
            if s["status"] == "ok" and s.get("platform") in ("nuvemshop", "genérico") and not s.get("triagem"):
                todo.append((s["domain"], False))
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(scrape, d, r): d for d, r in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            print(f"[{i}/{len(todo)}] {r['domain']:<30} {r['status']:<10} {str(r['platform']):<8} "
                  f"camisetas={len(r['products'])} {r.get('error') or ''}", flush=True)


if __name__ == "__main__":
    main()
