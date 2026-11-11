"""Gera lista_calcas.md com TODAS as calças varridas (não só bootcut), agrupadas por silhueta e cor.

Uso: python lista_md.py
"""
import json
import os
import re
from collections import Counter, defaultdict

import analyze as A

OUT = os.path.join(A.HERE, "lista_calcas.md")

RETA = re.compile(r"\breta\b|\breto\b|\bstraight\b|\bregular\b|\bslim\b|\bskinny\b|\bstandard\b|\bclassic\b|"
                  r"\btradicional\b|\bcarpinteir|\bcarpenter\b|\bwork ?pants?\b|\bworkwear\b|\b5 bolsos\b|\bpainter\b|"
                  r"\bfive pocket\b|\bselvedge\b|\braw\b|\bdad\b|\btapered\b|\bslouch\b")
FORA = A.EXCL + [("moletom/track", r"\bmoletom\b|\bsweat ?pants?\b|\btrack|trackpants|\btactel\b|\bnylon\b|\bfleece\b|\bsherpa\b|\bpijama\b"),
                 ("loose/relaxed", r"\bloose\b|\brelaxed\b|\bparachute\b|\bbalon\b|\bbig\b|\blarg[ao]\b|\bampl[ao]\b|\bmom\b|\bbaggies\b"),
                 ("short", r"\bshorts?\b|\bbermuda\b|\bjorts?\b|\bcapri\b")]


def silhouette(title, head, desc):
    t, d = A.unacc(title + " " + head), A.unacc(desc)
    if A.KEEP.search(t) or A.KEEP.search(d):
        if re.search(r"\bbootleg\b", t + d) and not re.search(r"boot\s?-?cul?t|flare", t + d) and \
                not re.search(r"\bcalcas?\b|\bpants?\b|\bjeans?\b|\bdenim\b", A.unacc(title)):
            return None
        return "bootcut/flare"
    if RETA.search(t) or RETA.search(d[:400]):
        return "reta/slim"
    return "não informada"


def excluded(title, head, desc):
    t = A.unacc(title + " " + head)
    for name, rx in FORA:
        if re.search(rx, t):
            if name == "wide" and re.search(r"boot\s?-?cut\s+wide|wide\s+boot\s?-?cut", t):
                continue
            if name == "feminina" and not re.search(rx, A.unacc(title)) and re.search(r"masculin|unissex|unisex", t):
                continue
            return name
    # descrição: só termos de modelagem que não deixam dúvida
    d = A.unacc(desc)
    if re.search(r"modelagem (?:\w+ ){0,2}(?:baggy|wide|oversized|barrel|balloon|cargo|jogger|pantalona)|"
                 r"caimento (?:\w+ ){0,2}(?:baggy|wide|oversized)|\bwide leg\b|\bbaggy fit\b", d):
        return "larga (descrição)"
    return None


def collect():
    brands = json.load(open(os.path.join(A.CACHE, "brands.json")))
    insta = {}
    rows, out_count, final_hosts = [], Counter(), set()
    for b in brands:
        if b["pre_status"] or not b["domain"]:
            continue
        path = os.path.join(A.STORES, b["domain"] + ".json")
        if not os.path.exists(path):
            continue
        s = json.load(open(path))
        if s["status"] != "ok":
            continue
        fh = re.sub(r"^https?://(www\.)?", "", s.get("final_url") or "").split("/")[0]
        if fh in final_hosts:
            continue
        final_hosts.add(fh)
        insta[b["name"]] = (b["instagram"], b["source"], b["domain"])
        seen = set()
        for p in s["products"]:
            url = p.get("url") or ""
            if s.get("platform") == "nuvemshop" and re.search(r"^https?://[^/]+/[a-z]{2}/", url):
                continue
            title = (p.get("title") or "").strip()
            key = (re.sub(r"\W*\(?copia\)?\s*$", "", A.unacc(title)), p.get("price"),
                   re.sub(r"[-_]?[a-z0-9]?\d*$", "", url.rstrip("/").rsplit("/", 1)[-1]))
            if key in seen or url in seen:
                continue
            seen.add(key)
            seen.add(url)
            tags = " ".join(str(t) for t in (p.get("tags") or []) if t)
            head = (p.get("product_type") or "") + " " + tags
            desc = p.get("description_text") or ""
            tt = A.unacc(title)
            if A.NOT_PANTS.search(tt) and not re.search(r"\bcalcas?\b|\bpants?\b|\bjeans?\b", tt):
                continue
            if not (re.search(r"\bcalcas?\b|\bpants?\b|\bjeans?\b|\btrousers?\b|\bdenim\b|\bbootcut\b|\bflared?\b", tt)
                    or re.search(r"\bcalcas?\b|\bpants\b|\btrousers\b", A.unacc(head))):
                continue
            if re.search(r"\b(sandalia|tenis|bota|clog|bolsa|bone|chinelo|meia|cinto|carteira|oculos)\b", tt):
                continue
            ex = excluded(title, head + " " + url.rsplit("/", 2)[-2].replace("-", " "), desc)
            if ex:
                out_count[ex] += 1
                continue
            sil = silhouette(title, head, desc)
            if not sil:
                continue
            vs = p.get("variants") or []
            avail = [A.size_of_variant(v) for v in vs if v.get("available")]
            known = any(v.get("available") is not None for v in vs)
            if known:
                good = [x for x in dict.fromkeys(avail) if x and A.SIZE_RX.match(x)]
                disp = ", ".join(good) if good else ("em estoque" if avail else "")
                in_stock = bool(avail)
            else:
                in_stock = p.get("in_stock") is not False
                disp = "estoque n/d"
            var_txt = " ".join(" ".join(map(str, v.get("options") or [])) for v in vs)
            cs = A.colors_in(title) or A.colors_in(var_txt) or \
                A.colors_in(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")) or A.colors_in(desc[:600], True)
            grp = "outra" if any(g == "outra" for _, g in cs) else ("azul/preto" if cs else "indefinida")
            fab, oz, _ = A.fabric_of(title + " " + desc)
            price, comp = p.get("price"), p.get("compare_at")
            rows.append({
                "marca": b["name"], "nome": title, "url": url, "sil": sil, "grp": grp,
                "cor": ", ".join(dict.fromkeys(c[0] for c in cs)) or "?", "tecido": " ".join(x for x in (fab, oz) if x),
                "preco": price, "de": comp if comp and price and comp > price else None,
                "disp": disp, "in_stock": in_stock,
            })
    return rows, out_count, insta


def money(v):
    return "" if v is None else ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


def esc(s):
    return str(s).replace("|", "/").replace("\n", " ").strip()


def table(rows):
    lines = ["| Marca | Peça | Cor | Tecido | Preço | Tamanhos disponíveis |", "|---|---|---|---|---|---|"]
    for r in rows:
        preco = money(r["preco"]) + (f" ~~{money(r['de'])}~~" if r["de"] else "")
        disp = esc(r["disp"]) if r["in_stock"] else "**esgotada**"
        lines.append(f"| {esc(r['marca'])} | [{esc(r['nome'])}]({r['url']}) | {esc(r['cor'])} | {esc(r['tecido'])} "
                     f"| {preco} | {disp} |")
    return "\n".join(lines)


SECTIONS = [
    ("1. Bootcut / flare — cores fora do azul e preto", "bootcut/flare", ("outra",)),
    ("2. Bootcut / flare — cor não identificada (conferir na foto)", "bootcut/flare", ("indefinida",)),
    ("3. Bootcut / flare — azul e preto", "bootcut/flare", ("azul/preto",)),
    ("4. Retas / slim / straight — cores fora do azul e preto", "reta/slim", ("outra",)),
    ("5. Retas / slim / straight — cor não identificada", "reta/slim", ("indefinida",)),
    ("6. Retas / slim / straight — azul e preto", "reta/slim", ("azul/preto",)),
    ("7. Modelagem não informada — cores fora do azul e preto", "não informada", ("outra",)),
    ("8. Modelagem não informada — cor não identificada", "não informada", ("indefinida",)),
    ("9. Modelagem não informada — azul e preto", "não informada", ("azul/preto",)),
]


def main():
    rows, out_count, insta = collect()
    rows.sort(key=lambda r: (not r["in_stock"], r["marca"].lower(), r["preco"] or 0))
    n_stock = sum(r["in_stock"] for r in rows)
    md = [
        "# Calças de marcas brasileiras — lista completa",
        "",
        f"Todas as calças encontradas nas lojas do [Brazil Made It](https://brazilmadeit.com.br/) e nas lojas extras: "
        f"**{len(rows)} peças** ({n_stock} com algum tamanho disponível), de "
        f"**{len({r['marca'] for r in rows})} marcas**.",
        "",
        "Ficaram de fora (pelo título, tags ou modelagem declarada): " +
        ", ".join(f"{k} ({v})" for k, v in out_count.most_common()) + ".",
        "",
        "Em cada seção: primeiro as disponíveis, depois as esgotadas; dentro disso, por marca e preço. "
        "Preço riscado = preço \"de\". Cor e modelagem saem do texto da loja — confira na foto.",
        "",
        "Referência (Cruelty bootcut P, peça deitada): cintura 41 · quadril 49 · comprimento 106 · barra 25,5 cm. "
        "Medidas por peça estão no `resultado.xlsx`.",
        "",
        "## Sumário",
        "",
    ]
    secs = []
    for title, sil, grps in SECTIONS:
        sel = [r for r in rows if r["sil"] == sil and r["grp"] in grps]
        if not sel:
            continue
        anchor = re.sub(r"[^a-z0-9 -]", "", A.unacc(title)).replace(" ", "-")
        md.append(f"- [{title}](#{anchor}) — {len(sel)} ({sum(r['in_stock'] for r in sel)} disponíveis)")
        secs.append((title, sel))
    md.append("")
    for title, sel in secs:
        md += [f"## {title}", "", table(sel), ""]
    # marcas
    per = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        per[r["marca"]][0] += 1
        per[r["marca"]][1] += r["in_stock"]
        per[r["marca"]][2] += r["sil"] == "bootcut/flare"
    md += ["## Marcas com calças na lista", "", "| Marca | Loja | Instagram | Origem | Calças | Disponíveis | Bootcut/flare |",
           "|---|---|---|---|---|---|---|"]
    for m, (n, d, bf) in sorted(per.items(), key=lambda x: (-x[1][2], -x[1][1], x[0].lower())):
        ig, src, dom = insta.get(m) or ("", "", "")
        orig = "Brazil Made It" if src == "brazilmadeit" else "fora do diretório"
        md.append(f"| {esc(m)} | [{dom}](https://{dom}) | {f'[link]({ig})' if ig else ''} | {orig} | {n} | {d} | {bf} |")
    open(OUT, "w").write("\n".join(md) + "\n")
    print(len(rows), "peças;", n_stock, "disponíveis")
    for t, sel in secs:
        print(f"  {len(sel):5}  {t}")
    print("fora:", out_count.most_common())


if __name__ == "__main__":
    main()
