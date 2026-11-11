"""Descobre lojas além do Brazil Made It.

Fontes (todas públicas e permitidas pelo robots.txt):
  - StoreCensus: lojas Shopify brasileiras nas categorias de moda/luxo
  - crt.sh (Certificate Transparency): subdomínios *.lojavirtualnuvem.com.br (lojas Nuvemshop BR)

Saída: cache/discovered.json  {domínio: [fontes]}
"""
import json
import os
import random
import re
import time

import requests

from scraper import UA

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "discovered.json")
CATS = ["fashion-and-apparel", "luxury-goods", "jewelry-and-accessories"]  # acessórios: algumas marcas de roupa caem lá


def storecensus():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    found = {}
    for cat in CATS:
        page = 1
        while True:
            url = f"https://www.storecensus.com/stores/country/brazil/category/{cat}?page={page}"
            for attempt in range(3):
                try:
                    r = s.get(url, timeout=20)
                    break
                except requests.RequestException:
                    time.sleep(5)
            else:
                break
            doms = set(re.findall(r'href="/stores/([a-z0-9.-]+\.[a-z]{2,})"', r.text))
            doms -= {"country"}
            new = [d for d in doms if d not in found]
            for d in doms:
                found.setdefault(d, f"storecensus:{cat}")
            print(f"  storecensus {cat} p{page}: {len(doms)} ({len(new)} novas)", flush=True)
            if not new:
                break
            page += 1
            time.sleep(random.uniform(1.0, 2.0))
    return found


def crtsh():
    r = requests.get("https://crt.sh/?q=%25.lojavirtualnuvem.com.br&output=json", timeout=180)
    names = {n.strip().lower() for e in r.json() for n in e["name_value"].split("\n")}
    bad = re.compile(r"^(\*|acdn|cdn|www|api|admin|static|staging|test)")
    return {n: "crt.sh:nuvemshop" for n in names if n.endswith(".lojavirtualnuvem.com.br") and not bad.match(n)}


def main():
    found = {}
    print("StoreCensus…")
    found.update(storecensus())
    print("crt.sh…")
    found.update(crtsh())
    json.dump(found, open(OUT, "w"), indent=0, sort_keys=True)
    from collections import Counter
    print(len(found), Counter(v.split(":")[0] for v in found.values()))


if __name__ == "__main__":
    main()
