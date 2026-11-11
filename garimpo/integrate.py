"""Incorpora as lojas da triagem em massa (cache/mass) que têm calça bootcut/flare.

- Só entram lojas brasileiras: domínio .br ou produtos com texto em português.
- Grava cache/stores/<dom>.json (só com as calças triadas) e cache/brands_mass.json,
  que analyze.py / lista_md.py somam ao brands.json.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
MASC = re.compile(r"masculin|unissex|unisex|\bmen'?s?\b|\bhomem\b|\bmale\b|ag[eê]nero|genderless|sem g[eê]nero", re.I)
PT = re.compile(r"\bcal[cç]a|\btamanho|\balgod[aã]o|\bcintura|\bmodelagem|\btecido|\bcomposi[cç][aã]o", re.I)


def pretty(dom):
    base = dom.split(".")[0]
    if base in ("www", "loja", "shop"):
        base = dom.split(".")[1]
    return base.replace("-", " ").title()


def main():
    disc = json.load(open(os.path.join(CACHE, "discovered.json")))
    out, n_ok, n_hit = [], 0, 0
    for f in sorted(glob.glob(os.path.join(CACHE, "mass", "*.json"))):
        r = json.load(open(f))
        if r["status"] == "ok":
            n_ok += 1
        if not r["products"]:
            continue
        n_hit += 1
        final = re.sub(r"^https?://(www\.)?", "", r.get("final_url") or "").split("/")[0] or r["domain"]
        txt = " ".join((p.get("title") or "") + " " + (p.get("description_text") or "")[:500] for p in r["products"])
        if not (final.endswith(".br") or r["domain"].endswith(".br") or PT.search(txt)):
            continue
        dom = r["domain"]
        # lojas genéricas: só calças com sinal explícito de masculino/unissex
        prods = [p for p in r["products"] if MASC.search(" ".join(
            [p.get("title") or "", p.get("url") or "", p.get("product_type") or "", " ".join(map(str, p.get("tags") or [])),
             (p.get("description_text") or "")[:2000]]))]
        if not prods:
            continue
        r["products"] = prods
        store = {"domain": dom, "name": pretty(final), "status": "ok", "platform": r["platform"],
                 "products": r["products"], "n_listed": r.get("n_total"), "error": None,
                 "final_url": r.get("final_url"), "triagem": True}
        json.dump(store, open(os.path.join(CACHE, "stores", dom + ".json"), "w"), ensure_ascii=False)
        out.append({"name": pretty(final), "instagram": "", "handle": "", "region": "", "shop_url": "https://" + final,
                    "domain": dom, "source": disc.get(dom, "descoberta").split(":")[0], "pre_status": None})
    json.dump(out, open(os.path.join(CACHE, "brands_mass.json"), "w"), ensure_ascii=False, indent=1)
    print(f"lojas lidas: {n_ok} | com bootcut/flare: {n_hit} | brasileiras incorporadas: {len(out)}")


if __name__ == "__main__":
    main()
