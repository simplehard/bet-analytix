"""TODAS as camisetas das marcas alternativas (diretório Brazil Made It + extras/editoriais), de todo tipo.

Classifica caimento (regular / boxy-oversized / cropped / slim / longline), estampa (lisa / estampada),
cor e, quando a loja publica, a medida mais próxima de 60 cm de comprimento.
Gera camisetas_todas.md e camisetas_todas.html (fotos embutidas, filtros).
"""
import json
import os
import re
from collections import Counter

import analyze as A
import lista_html as LH
import tees_analyze as T

HERE = A.HERE
NAO_TEE = re.compile(r"regata|tank|polo\b|baby ?look|feminin|women|infantil|kids|juvenil|menina|menino|bebe|kit\b|"
                     r"\bpack\b|combo|vestido|cropped feminin|body\b|gift ?card|cart[aã]o presente")
GRUPOS = [("preto lavado / carvão", 0), ("preto", 1), ("cinza", 2), ("branco / off-white", 3), ("outras cores", 4),
          ("cor não identificada", 5)]


def caimento(t, d):
    if re.search(r"oversized?|\bover\b|\bboxy\b|\bbox\b|super ?size|\bbig\b|\bampla\b", t) or \
            re.search(r"modelagem (\w+ ){0,2}(oversized|boxy|ampla)|caimento (\w+ ){0,2}(oversized|boxy|amplo)|"
                      r"\boversized\b|\bboxy\b", d):
        return "boxy/oversized"
    if T.CROPPED.search(t) or re.search(r"modelagem (\w+ ){0,2}cropped", d):
        return "cropped"
    if re.search(r"\bslim\b|muscle|\bfit\b(?! regular)", t) or re.search(r"modelagem (\w+ ){0,2}(slim|ajustada)", d):
        return "slim"
    if re.search(r"longline|alongad", t + " " + d[:300]):
        return "longline"
    if T.REGULAR.search(t) or re.search(r"modelagem (\w+ ){0,2}(regular|tradicional|classica|reta)|caimento regular", d):
        return "regular"
    return "não informado"


def estampa(t, d, marca):
    if T.ESTAMPA.search(t) or re.search(r"estampa|silk|serigraf|print|bordad|aplica[cç]|transfer|dtf|lettering", d):
        return "estampada"
    brand_words = set(re.findall(r"[a-z0-9]+", A.unacc(marca)))
    resto = [w for w in re.findall(r"[a-z0-9']+", t) if w not in T.GENERIC and w not in brand_words
             and not w.isdigit() and len(w) > 2]
    if T.LISA.search(t) or (re.search(r"\blisa\b|sem estampa|basica|plain|blank", d) and len(resto) <= 1):
        return "lisa"
    return "não informado"


def cor_grupo(title, url, var_txt, desc):
    label, prio = T.cor_de(title)
    if label is None:
        label, prio = T.cor_de(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))
    if label is not None:
        return ("preto lavado / carvão" if prio in (0, 1) else "preto"), label
    cs = A.colors_in(title) or A.colors_in(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")) or \
        A.colors_in(var_txt) or A.colors_in(desc[:400], True)
    if not cs:
        return "cor não identificada", "?"
    labels = list(dict.fromkeys(c[0] for c in cs))
    first = labels[0]
    if first == "preto":
        return "preto", ", ".join(labels)
    if first == "cinza":
        return "cinza", ", ".join(labels)
    if first in ("branco", "bege/cru"):
        return "branco / off-white", ", ".join(labels)
    return "outras cores", ", ".join(labels)


def coletar():
    rows, seen = [], set()
    for marca, origem, ig, p in T.iter_products():
        if origem == "varejo":
            continue
        title = (p.get("title") or "").strip()
        t = A.unacc(title)
        url = p.get("url") or ""
        if not T.TEE.search(t) or NAO_TEE.search(t) or re.search(r"feminin|women|infantil|kids", A.unacc(url)):
            continue
        tags = A.unacc(" ".join(map(str, p.get("tags") or [])) + " " + (p.get("product_type") or ""))
        desc = p.get("description_text") or ""
        d = A.unacc(desc[:2000])
        if re.search(r"feminin|women|infantil|kids", tags) and not re.search(r"masculin|unissex|unisex|\bmen\b", tags + d):
            continue
        if re.search(r"^https?://[^/]+/[a-z]{2}/", url) and "/products/" not in url[8:30]:
            continue
        key = (A.unacc(marca), re.sub(r"\W+", " ", t).strip(), p.get("price"))
        if key in seen or url in seen:
            continue
        seen.add(key)
        seen.add(url)
        vs = p.get("variants") or []
        var_txt = " ".join(" ".join(map(str, v.get("options") or [])) for v in vs)
        grupo, cor = cor_grupo(title, url, var_txt, desc)
        avail = [A.size_of_variant(v) for v in vs if v.get("available")]
        avail = [x for x in dict.fromkeys(avail) if x and A.SIZE_RX.match(x)]
        known = any(v.get("available") is not None for v in vs)
        in_stock = bool([v for v in vs if v.get("available")]) if known else (p.get("in_stock") is not False)
        meas = T.tee_meas([p.get("description_html") or ""] + (p.get("size_tables") or []), desc)
        medida, mrank = "", 3
        if meas:
            sz, m = min(meas.items(), key=lambda kv: abs(kv[1]["comprimento"] - 60))
            medida = f"{sz}: comp {m['comprimento']:g}" + (f" · larg {m['largura']:g}" if m.get("largura") else "")
            mrank = 0 if 58 <= m["comprimento"] <= 62 else (1 if 56 <= m["comprimento"] <= 64 else 2)
            medida = ("✅ " if mrank == 0 else ("≈ " if mrank == 1 else "")) + medida
        elif p.get("extra_images"):
            medida = "tabela em imagem"
        gram = re.search(r"(\d{3})\s*(?:g/?m|gsm|gramas|gr?\b)", d + " " + t)
        price, compare = p.get("price"), p.get("compare_at")
        rows.append({
            "marca": marca, "origem": origem, "nome": title, "url": url, "img": p.get("image"),
            "grupo": grupo, "cor": cor, "fit": caimento(t, d), "est": estampa(t, d, marca),
            "manga": "manga longa" if re.search(r"manga longa|long ?sleeve|\bml\b|\bl/s\b", t) else "manga curta",
            "medida": medida, "mrank": mrank, "gram": (gram.group(1) + " g/m²") if gram else "",
            "preco": price, "de": compare if compare and price and compare > price else None,
            "disp": ", ".join(avail) or ("em estoque" if in_stock else ""), "in_stock": in_stock,
        })
    gp = dict(GRUPOS)
    fitp = {"regular": 0, "não informado": 1, "cropped": 2, "slim": 3, "longline": 4, "boxy/oversized": 5}
    rows.sort(key=lambda r: (not r["in_stock"], gp[r["grupo"]], r["mrank"], fitp[r["fit"]], r["marca"].lower(),
                             r["preco"] or 9999))
    return rows


def write_md(rows):
    esc = lambda s: str(s).replace("|", "/").replace("\n", " ")
    c_fit, c_est = Counter(r["fit"] for r in rows), Counter(r["est"] for r in rows)
    md = ["# Camisetas — marcas alternativas brasileiras (todas)", "",
          f"**{len(rows)} camisetas** de **{len({r['marca'] for r in rows})} marcas** "
          f"({sum(r['in_stock'] for r in rows)} com algum tamanho disponível). Fonte: Brazil Made It + lojas extras/editoriais "
          f"(Ukio, Cacete, Normando, HIST…). Varejo está em `camisetas.md`.", "",
          "Caimento: " + ", ".join(f"{k} ({v})" for k, v in c_fit.most_common()) + ".",
          "Estampa: " + ", ".join(f"{k} ({v})" for k, v in c_est.most_common()) + ".", "",
          "Em cada seção: disponíveis primeiro → comprimento perto de 60 cm (✅ 58–62, ≈ 56–64) → regular → marca → preço. "
          "Caimento, estampa e cor saem do texto da loja — confira na foto.", "", "## Sumário", ""]
    for g, _ in GRUPOS:
        sel = [r for r in rows if r["grupo"] == g]
        if sel:
            anchor = re.sub(r"[^a-z0-9 -]", "", A.unacc(g)).replace(" ", "-")
            md.append(f"- [{g}](#{anchor}) — {len(sel)} ({sum(r['in_stock'] for r in sel)} disponíveis)")
    md.append("")
    for g, _ in GRUPOS:
        sel = [r for r in rows if r["grupo"] == g]
        if not sel:
            continue
        md += [f"## {g}", "", "| Marca | Camiseta | Cor | Caimento | Estampa | Medida (cm) | Preço | Tamanhos disp. |",
               "|---|---|---|---|---|---|---|---|"]
        for r in sel:
            preco = T.money(r["preco"]) + (f" ~~{T.money(r['de'])}~~" if r["de"] else "")
            fit = r["fit"] + (" · manga longa" if r["manga"] == "manga longa" else "")
            md.append(f"| {esc(r['marca'])} | [{esc(r['nome'])}]({r['url']}) | {esc(r['cor'])} | {fit} | {r['est']} "
                      f"| {esc(r['medida'])} | {preco} | {esc(r['disp']) if r['in_stock'] else '**esgotada**'} |")
        md.append("")
    open(os.path.join(HERE, "camisetas_todas.md"), "w").write("\n".join(md) + "\n")


def thumb(url, W=160, Q=50):
    """Miniatura pequena embutida (data URI) — as fotos abrem em qualquer visualizador, inclusive no celular."""
    import base64, hashlib, io, requests
    from PIL import Image
    if not url:
        return None
    url = "https:" + url if url.startswith("//") else url
    d = os.path.join(A.CACHE, f"thumbs{W}")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, hashlib.sha1(url.encode()).hexdigest()[:16] + ".webp")
    if not os.path.exists(fp):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)
            im.save(fp, "WEBP", quality=Q, method=6)
        except Exception:
            return url
    return "data:image/webp;base64," + base64.b64encode(open(fp, "rb").read()).decode()


def write_html(rows, embed=True):
    if embed:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(16) as ex:
            imgs = list(ex.map(thumb, [r["img"] for r in rows]))
    else:
        imgs = [r["img"] for r in rows]
    data = []
    for r, im in zip(rows, imgs):
        data.append({"marca": r["marca"], "nome": r["nome"], "url": r["url"], "img": LH.hires(r["img"]),
                     "thumb": im if (im or "").startswith("data:") else None, "sil": r["fit"],
                     "grp": r["grupo"], "est": r["est"], "cor": r["cor"],
                     "tecido": " · ".join(x for x in (r["est"], r["medida"], r["gram"],
                                                       "manga longa" if r["manga"] == "manga longa" else "") if x),
                     "preco": r["preco"], "de": r["de"], "disp": r["disp"], "in_stock": r["in_stock"],
                     "mrank": r["mrank"], "prio": dict(GRUPOS)[r["grupo"]]})
    html = LH.TEMPLATE
    html = html.replace("<title>Calças de marcas brasileiras</title>", "<title>Camisetas — marcas alternativas</title>")
    html = html.replace("<h1>Calças de marcas brasileiras</h1>", "<h1>Camisetas — marcas alternativas brasileiras</h1>")
    fits = ["regular", "não informado", "cropped", "slim", "longline", "boxy/oversized"]
    html = re.sub(r'<select id="sil">.*?</select>', '<select id="sil"><option value="">Todos os caimentos</option>' +
                  "".join(f'<option value="{f}">{f}</option>' for f in fits) + "</select>" +
                  '<select id="est"><option value="">Lisas e estampadas</option><option value="lisa">Só lisas</option>'
                  '<option value="estampada">Só estampadas</option><option value="não informado">Estampa não informada</option></select>',
                  html, flags=re.S)
    html = re.sub(r'<select id="grp">.*?</select>', '<select id="grp"><option value="">Todas as cores</option>' +
                  "".join(f'<option value="{g}">{g}</option>' for g, _ in GRUPOS) + "</select>", html, flags=re.S)
    html = html.replace('<option value="rel">Ordem: bootcut + cor primeiro</option>',
                        '<option value="rel">Ordem: preto lavado/carvão + regular primeiro</option>')
    html = html.replace("const silRank = {\"bootcut/flare\":0,\"reta/slim\":1,\"não informada\":2}, grpRank = {\"outra\":0,\"indefinida\":1,\"azul/preto\":2};",
                        "const silRank = " + json.dumps({f: i for i, f in enumerate(fits)}, ensure_ascii=False) + ", grpRank = {};")
    html = html.replace("else list.sort((a,b) => silRank[a.sil] - silRank[b.sil] || grpRank[a.grp] - grpRank[b.grp] ||",
                        "else list.sort((a,b) => (b.in_stock - a.in_stock) || a.prio - b.prio || a.mrank - b.mrank || silRank[a.sil] - silRank[b.sil] ||")
    html = html.replace("const q = norm($(\"q\").value).split(/\\s+/).filter(Boolean), sil = $(\"sil\").value,",
                        "const est = $(\"est\").value, q = norm($(\"q\").value).split(/\\s+/).filter(Boolean), sil = $(\"sil\").value,")
    html = html.replace("list = DATA.filter(r => (!sil || r.sil === sil) &&", "list = DATA.filter(r => (!est || r.est === est) && (!sil || r.sil === sil) &&")
    html = html.replace('["q","sil","grp","brand","sort","stock"]', '["q","sil","est","grp","brand","sort","stock"]')
    html = html.replace('const silTag = r.sil === "bootcut/flare" ? "bootcut/flare" : (r.sil === "reta/slim" ? "reta/slim" : "");',
                        'const silTag = r.sil !== "não informado" ? r.sil : "";')
    html = html.replace('"preto":"#1d1d1d",', '"preto":"#1d1d1d","preto lavado/desbotado":"#3b3a39","carvão/chumbo/cinza escuro":"#4a4c4f",')
    sub = (f"{len(rows)} camisetas de {len({r['marca'] for r in rows})} marcas alternativas brasileiras "
           f"(Brazil Made It + extras). Caimento, estampa e cor vêm do texto da loja — confira na foto.")
    html = html.replace("__SUB__", sub).replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    open(os.path.join(HERE, "camisetas_todas.html"), "w").write(html)


def main():
    import sys
    rows = coletar()
    write_md(rows)
    write_html(rows, embed="--no-embed" not in sys.argv)
    print(len(rows), "camisetas;", sum(r["in_stock"] for r in rows), "disponíveis;", len({r["marca"] for r in rows}), "marcas")
    print(Counter(r["grupo"] for r in rows))
    print(Counter(r["fit"] for r in rows), Counter(r["est"] for r in rows))


if __name__ == "__main__":
    main()
