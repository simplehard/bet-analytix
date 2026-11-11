"""Camisetas lisas, gola careca, regular fit, preto lavado / carvão / chumbo, comprimento 58–62 cm.

Lê cache/stores (catálogos completos Shopify/Woo/VTEX) + cache/tees (Nuvemshop/genérico/varejo).
Gera camisetas.md e camisetas.html.
"""
import glob
import json
import os
import re

import analyze as A
import lista_html as LH

HERE = A.HERE
ALVO = (58.0, 62.0)

TEE = re.compile(r"\bcamiseta|\btee\b|t-?shirt|\bcamisa basica")
NAO = re.compile(r"regata|tank|manga longa|long ?sleeve|\bml\b|polo|henley|gola v\b|v-?neck|gola alta|mock|baby ?look|"
                 r"feminin|infantil|kids|juvenil|menina|menino|bebe|dry ?fit|\buv\b|esportiv|running|treino|fitness|"
                 r"raglan|pijama|kit\b|\bpack\b|combo|segunda pele|termica|camisa social|vestido")
FIT_FORA = re.compile(r"oversized?|\bover\b|boxy|\bbox\b|\bslim\b|muscle|longline|ampla|wide|relaxed|loose|super ?size|big")
ESTAMPA = re.compile(r"estampa|estampad|print|graphic|grafic|logo|bordad|tie ?dye|listrad|stripe|xadrez|camufl|"
                     r"desenho|foto|\bart\b|patch|silk|lettering|frase|personagem|disney|marvel|anime|banda|tour")
LISA = re.compile(r"basic|basica|\blisa\b|plain|blank|essential|essencial|heavy ?weight|heavyweight|"
                  r"sem estampa|\bblank\b")
REGULAR = re.compile(r"regular|tradicional|classic|reta|standard|corte classico")
CROPPED = re.compile(r"cropped|(?<!manga )curta|short fit|boxy crop")
GENERIC = set("""camiseta camisa t shirt tshirt tee masculina masculino unissex unisex manga curta curtas washed lavada lavado
estonada estonado stone vintage faded preto preta black cinza grafite chumbo carvao charcoal grey gray em de com da do e the
regular classic classica basica basico basic malha algodao peruano pima premium heavy heavyweight tingida tingido garment dyed
dye pigment pigmentada off desbotada desbotado acid envelhecida marmorizada sun gola careca redonda crew neck essential
essencial plain blank lisa liso oversize fit reta super cotton comfort soft jersey 100 ss tee's""".split())

CORES = [  # (regex sem acento, rótulo, prioridade)
    (r"(preto|preta|black)\W+(lavad|washed|faded|stone|estonad|vintage|desbotad|tingid|garment|acid|sun|envelhecid|"
     r"used|worn)|(washed|faded|vintage|garment.?dyed|acid)\W+(preto|preta|black)|off.?black|washed ?black|"
     r"preto ?desbotad|black ?wash", "preto lavado/desbotado", 0),
    (r"carvao|charcoal|grafite|graphite|antracite|anthracite|asfalto|onix|onyx|ardosia|slate|chumbo|lead\b|"
     r"cinza ?escuro|dark ?gr[ae]y|gr[ae]y ?escuro|fume|smoke", "carvão/chumbo/cinza escuro", 1),
    (r"\bpreto\b|\bpreta\b|\bblack\b|\bnegro\b", "preto", 2),
]

TEE_MEAS = [("comprimento", r"comprimento|altura|length|compr|\bcomp\b|\balt\b"),
            ("largura", r"largura|busto|torax|peito|chest|width|\blarg\b|circunferencia"),
            ("manga", r"manga|sleeve"), ("ombro", r"ombro|shoulder")]
TEE_HDR = r"(?:comprimento|altura|length|largura|busto|torax|peito|chest|width|manga|sleeve|ombro|shoulder)"


SZ = r"(?:PP|P|M|G|GG|XG|XGG|EG|G1|G2|G3|2P|2G|3G|XS|S|L|XL|XXL|2XL|3XL|U)"


def tee_key(w):
    w = A.unacc(w)
    for k, rx in TEE_MEAS:
        if re.search(rx, w):
            return k
    return None


def parse_x(t):
    """'COMP x LARGURA ... P – 70 x 52 M – 72 x 54'"""
    m = re.search(r"(comp\w*|altura|largura|torax|peito|busto)(?:\W|cm){0,14}x(?:\W|cm){0,14}(comp\w*|altura|largura|torax|peito|busto)", t)
    if not m:
        return {}
    k1, k2 = tee_key(m.group(1)), tee_key(m.group(2))
    out = {}
    for sm in re.finditer(r"\b(" + SZ.lower() + r")\s*[-–:=]?\s*(\d{2,3}(?:[.,]\d)?)\s*(?:cm)?\s*x\s*(\d{2,3}(?:[.,]\d)?)",
                          t[m.end():m.end() + 600]):
        out[sm.group(1).upper()] = {k1: float(sm.group(2).replace(",", ".")), k2: float(sm.group(3).replace(",", "."))}
    return out


def parse_cols(t):
    """'S M L XL 2XL Mangas 28 29 30 31 32 Circunferencia 112 ... Comprimento 73 76 ...'"""
    best = {}
    for hm in re.finditer(r"((?:\b" + SZ.lower() + r"\b[\s|/]*){3,8})", t):
        sizes = re.findall(r"\b" + SZ.lower() + r"\b", hm.group(1))
        n = len(sizes)
        rest = t[hm.end():hm.end() + 500]
        out = {}
        for rm in re.finditer(r"([a-z][a-z ]{2,30}?)\s*(?:\(cm\))?[:\s]+((?:\d{2,3}(?:[.,]\d)?\s*(?:cm)?[\s|/-]*){%d})" % n, rest):
            k = tee_key(rm.group(1))
            vals = re.findall(r"\d{2,3}(?:[.,]\d)?", rm.group(2))
            if k and len(vals) == n:
                for sz, v in zip(sizes, vals):
                    out.setdefault(sz.upper(), {})[k] = float(v.replace(",", "."))
        if len(out) > len(best):
            best = out
    return best


def parse_measure_first(t):
    """'Comprimento: P 70 | M 72 ...  Circunferencia do torax: 2P 114cm - P 118cm'"""
    out = {}
    for seg in re.split(r"(?=\b(?:comprimento|largura|torax|peito|busto|circunferencia|manga)\b)", t):
        k = tee_key(seg[:30])
        if not k:
            continue
        for sm in re.finditer(r"\b(" + SZ.lower() + r")\s*[:=\-–]?\s*(\d{2,3}(?:[.,]\d)?)\s*(?:cm)?", seg[:220]):
            out.setdefault(sm.group(1).upper(), {}).setdefault(k, float(sm.group(2).replace(",", ".")))
    return out if sum(len(v) for v in out.values()) >= 2 else {}


def tee_meas(text_htmls, desc):
    old_meas, old_hdr = A.MEAS, A.HDR_WORD
    A.MEAS, A.HDR_WORD = TEE_MEAS, TEE_HDR
    try:
        tab = A.parse_tables(text_htmls)
        if not tab:
            tab = A.parse_header_rows(desc)
        t = A.unacc(desc)
        for fn in (parse_x, parse_cols, parse_measure_first):
            if not tab or not any("comprimento" in m for m in tab.values()):
                alt = fn(t)
                if alt and any("comprimento" in m for m in alt.values()):
                    tab = alt
        if not tab:
            tab = A.parse_text(desc)
    finally:
        A.MEAS, A.HDR_WORD = old_meas, old_hdr
    out = {}
    for sz, m in tab.items():
        m = dict(m)
        if m.get("largura") and m["largura"] > 75:
            m["largura"] = m["largura"] / 2
        if m.get("comprimento") and 40 <= m["comprimento"] <= 95:
            out[sz] = m
    return out


WASH = r"estonad|lavad|washed|stone|faded|tingid|garment.?dye|vintage|desbotad|acid|envelhecid|sun.?faded|marmoriz"


def cor_de(text):
    t = A.unacc(text)
    if re.search(WASH, t) and re.search(r"\bpret[oa]\b|\bblack\b", t):
        return "preto lavado/desbotado", 0
    if re.search(r"\bclar[oa]\b|light|mescla clara|gelo|perola", t):
        return None, None
    if re.search(WASH, t) and re.search(r"cinza|gr[ae]y|chumbo|grafite|carvao|charcoal", t):
        return "carvão/chumbo/cinza escuro", 1
    for rx, label, prio in CORES:
        if re.search(rx, t):
            return label, prio
    return None, None


def load_brands():
    brands = json.load(open(os.path.join(A.CACHE, "brands.json")))
    p = os.path.join(A.CACHE, "brands_mass.json")
    if os.path.exists(p):
        brands += json.load(open(p))
    return {b["domain"]: b for b in brands if b["domain"]}


def iter_products():
    brands = load_brands()
    seen_hosts = set()
    files = [(f, False) for f in glob.glob(os.path.join(A.STORES, "*.json"))] + \
            [(f, True) for f in glob.glob(os.path.join(A.CACHE, "tees", "*.json"))]
    for f, is_tee_file in files:
        s = json.load(open(f))
        if s.get("status") != "ok":
            continue
        if not is_tee_file and s.get("platform") not in ("shopify", "woocommerce", "vtex"):
            continue  # Nuvemshop/genérico: as camisetas vêm de cache/tees
        if not is_tee_file and s.get("triagem"):
            continue
        dom = s["domain"]
        b = brands.get(dom, {})
        host = re.sub(r"^https?://(www\.)?", "", s.get("final_url") or dom).split("/")[0]
        key = (host, is_tee_file)
        if key in seen_hosts:
            continue
        seen_hosts.add(key)
        name = b.get("name") or s.get("name") or dom.split(".")[0].title()
        origem = "varejo" if s.get("retail") else {"brazilmadeit": "Brazil Made It", "extra": "lista manual/editorial"}.get(
            b.get("source"), "varejo" if s.get("retail") else (b.get("source") or "varejo"))
        for p in s["products"]:
            yield name, origem, b.get("instagram") or "", p


def analisa():
    rows, seen = [], set()
    for marca, origem, ig, p in iter_products():
        title = (p.get("title") or "").strip()
        t = A.unacc(title)
        if not TEE.search(t) or NAO.search(t):
            continue
        url = p.get("url") or ""
        if re.search(r"^https?://[^/]+/[a-z]{2}/", url) and "/products/" not in url[:10]:
            pass
        desc = p.get("description_text") or ""
        d = A.unacc(desc[:1500])
        tags = A.unacc(" ".join(map(str, p.get("tags") or [])) + " " + (p.get("product_type") or ""))
        if re.search(r"feminin|women|infantil|kids", tags) and not re.search(r"masculin|unissex|unisex|\bmen\b", tags + d):
            continue
        if FIT_FORA.search(t) or re.search(r"modelagem (\w+ ){0,2}(oversized|boxy|ampla|slim)|caimento (\w+ ){0,2}"
                                           r"(oversized|boxy|amplo|slim)|\boversized\b|\bboxy\b", d):
            continue
        if ESTAMPA.search(t) or re.search(r"\bestampa(da)? (frontal|nas costas|central|em silk)|\bsilk\b", d):
            continue
        brand_words = set(re.findall(r"[a-z0-9]+", A.unacc(marca)))
        resto_t = [w for w in re.findall(r"[a-z0-9']+", t) if w not in GENERIC and w not in brand_words
                   and not w.isdigit() and len(w) > 2]
        lisa = bool(LISA.search(t) or (re.search(r"\blisa\b|sem estampa|basica|basic\b|plain|blank", d) and len(resto_t) <= 1))
        if re.search(r"feminin|women|infantil|kids", A.unacc(url)):
            continue
        if not lisa and re.search(WASH, t) and not re.search(r"estampa|silk|print|serigraf|bordad|aplicac|transfer|\blogo", d):
            brand_words = set(re.findall(r"[a-z0-9]+", A.unacc(marca)))
            resto = [w for w in re.findall(r"[a-z0-9']+", t) if w not in GENERIC and w not in brand_words and not w.isdigit()
                     and len(w) > 1]
            lisa = len(resto) == 0
        if not lisa and origem == "varejo" and not re.search(
                r"estampa|silk|print|serigraf|bordad|aplicac|transfer|\blogo|grafico|desenho|frase|lettering", d + " " + t):
            lisa = True
        if not lisa:
            continue
        vs = p.get("variants") or []
        var_txt = " ".join(" ".join(map(str, v.get("options") or [])) for v in vs)
        # cor: título > URL > variantes disponíveis (para produtos com várias cores, só aceita se a cor-alvo existir)
        cor, prio = cor_de(title)
        if cor is None:
            cor, prio = cor_de(url.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))
        if cor is None:
            cor, prio = cor_de(var_txt)
        if cor is None:
            continue
        # tamanhos disponíveis na cor-alvo quando a variante tem cor
        alvo_rx = next(rx for rx, lab, pr in CORES if lab == cor)
        avail = []
        for v in vs:
            if not v.get("available"):
                continue
            vt = A.unacc(" ".join(map(str, v.get("options") or [])) + " " + str(v.get("title") or ""))
            if colors_in_variant(vt) and not re.search(alvo_rx, vt) and not re.search(alvo_rx, A.unacc(title)):
                continue
            sz = A.size_of_variant(v)
            if sz and A.SIZE_RX.match(sz):
                avail.append(sz)
        known = any(v.get("available") is not None for v in vs)
        in_stock = bool(avail) if known else (p.get("in_stock") is not False)
        meas = tee_meas([p.get("description_html") or ""] + (p.get("size_tables") or []), desc)
        ok = {sz: m for sz, m in meas.items() if ALVO[0] <= m["comprimento"] <= ALVO[1]}
        perto = {sz: m for sz, m in meas.items() if ALVO[0] - 2 <= m["comprimento"] <= ALVO[1] + 2 and sz not in ok}
        fmt = lambda dd: "; ".join(f"{sz}: comp {m['comprimento']:g}" + (f" · larg {m['largura']:g}" if m.get("largura") else "")
                                   + (f" · manga {m['manga']:g}" if m.get("manga") else "") for sz, m in dd.items())
        if ok:
            medida, mrank = "✅ " + fmt(ok), 0
        elif perto:
            medida, mrank = "≈ " + fmt(perto), 1
        elif meas:
            medida, mrank = "fora (" + fmt(dict(list(meas.items())[:3])) + ")", 3
        elif p.get("extra_images"):
            medida, mrank = "tabela em imagem — conferir", 2
        else:
            medida, mrank = "sem medidas", 2
        fab, _, comp = A.fabric_of(title + " " + desc)
        gram = re.search(r"(\d{3})\s*(?:g/?m|gsm|gramas|g\b)", A.unacc(desc + " " + title))
        fit = "regular" if REGULAR.search(t + " " + d[:600]) else ""
        if CROPPED.search(t):
            fit = "cropped"
        key = (A.unacc(marca), re.sub(r"\W+", " ", t).strip(), p.get("price"))
        if key in seen:
            continue
        seen.add(key)
        price, compare = p.get("price"), p.get("compare_at")
        rows.append({
            "marca": marca, "origem": origem, "instagram": ig, "nome": title, "url": url, "img": p.get("image"),
            "cor": cor, "prio": prio, "medida": medida, "mrank": mrank, "fit": fit,
            "gramatura": (gram.group(1) + " g/m²") if gram else "", "composicao": comp,
            "preco": price, "de": compare if compare and price and compare > price else None,
            "disp": ", ".join(dict.fromkeys(avail)) or ("em estoque" if in_stock else ""), "in_stock": in_stock,
        })
    rows.sort(key=lambda r: (not r["in_stock"], r["mrank"], r["prio"], 0 if r["fit"] == "regular" else 1,
                             r["preco"] or 9999))
    return rows


def colors_in_variant(vt):
    return bool(re.search(r"preto|preta|black|branc|white|cinza|gr[ae]y|azul|blue|verde|green|bege|off|marrom|brown|"
                          r"vermelh|red|rosa|pink|amarel|yellow|chumbo|grafite|mescla|marinho|navy|areia|cru", vt))


def money(v):
    return "" if v is None else ("R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


def write_md(rows):
    esc = lambda s: str(s).replace("|", "/").replace("\n", " ")
    n_ok = sum(1 for r in rows if r["mrank"] == 0)
    md = ["# Camisetas lisas — preto lavado / carvão / chumbo, regular, comprimento 58–62 cm", "",
          f"**{len(rows)} camisetas** de {len({r['marca'] for r in rows})} marcas "
          f"({sum(r['in_stock'] for r in rows)} disponíveis; **{n_ok} com algum tamanho medindo 58–62 cm** de comprimento).",
          "", "Critérios: camiseta lisa (sem estampa/logo grande), gola careca, sem oversized/boxy/slim/muscle/longline; "
          "cor preto lavado/desbotado → carvão/chumbo/cinza escuro → preto. \"cropped\" está sinalizada no caimento.", "",
          "Ordem: disponíveis primeiro → medida no alvo (✅) → perto (≈, até 2 cm de diferença) → sem medida → "
          "cor mais próxima → regular fit → preço.", ""]
    secs = [("1. Comprimento 58–62 cm confirmado", lambda r: r["mrank"] == 0),
            ("2. Comprimento perto (56–64 cm)", lambda r: r["mrank"] == 1),
            ("3. Sem medidas publicadas (conferir com a loja)", lambda r: r["mrank"] == 2),
            ("4. Medidas fora da faixa", lambda r: r["mrank"] == 3)]
    for title, f in secs:
        sel = [r for r in rows if f(r)]
        if not sel:
            continue
        md += [f"## {title} — {len(sel)}", "", "| Marca | Camiseta | Cor | Caimento | Medidas (cm) | Preço | Tamanhos disp. |",
               "|---|---|---|---|---|---|---|"]
        for r in sel:
            preco = money(r["preco"]) + (f" ~~{money(r['de'])}~~" if r["de"] else "")
            md.append(f"| {esc(r['marca'])} | [{esc(r['nome'])}]({r['url']}) | {r['cor']} | {r['fit']} "
                      f"| {esc(r['medida'])} | {preco} | {esc(r['disp']) if r['in_stock'] else '**esgotada**'} |")
        md.append("")
    open(os.path.join(HERE, "camisetas.md"), "w").write("\n".join(md) + "\n")


def embed(url):
    """Miniatura WebP em data URI (as fotos aparecem em qualquer visualizador, inclusive no celular)."""
    import base64, hashlib, io, requests
    from PIL import Image
    if not url:
        return None
    url = "https:" + url if url.startswith("//") else url
    d = os.path.join(A.CACHE, "thumbs")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, hashlib.sha1(url.encode()).hexdigest()[:16] + ".webp")
    if not os.path.exists(fp):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im = im.resize((260, int(im.height * 260 / im.width)), Image.LANCZOS)
            im.save(fp, "WEBP", quality=60, method=6)
        except Exception:
            return url
    return "data:image/webp;base64," + base64.b64encode(open(fp, "rb").read()).decode()


def write_html(rows):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        imgs = list(ex.map(embed, [r["img"] for r in rows]))
    for r, im in zip(rows, imgs):
        r["img"] = im
    data = [{"marca": r["marca"], "nome": r["nome"], "url": r["url"], "img": ("https:" + r["img"]) if (r["img"] or "").startswith("//") else r["img"],
             "sil": r["fit"] or "—", "grp": r["cor"], "cor": r["cor"], "tecido": " · ".join(x for x in (r["medida"], r["gramatura"]) if x),
             "preco": r["preco"], "de": r["de"], "disp": r["disp"], "in_stock": r["in_stock"],
             "mrank": r["mrank"], "prio": r["prio"]} for r in rows]
    html = LH.TEMPLATE
    html = html.replace("<title>Calças de marcas brasileiras</title>", "<title>Camisetas lisas — preto lavado / carvão</title>")
    html = html.replace("<h1>Calças de marcas brasileiras</h1>", "<h1>Camisetas lisas — preto lavado / carvão · 58–62 cm</h1>")
    html = re.sub(r'<select id="sil">.*?</select>', '''<select id="sil">
      <option value="">Todos os caimentos</option><option value="regular">regular</option>
      <option value="cropped">cropped</option><option value="—">não informado</option></select>''', html, flags=re.S)
    html = re.sub(r'<select id="grp">.*?</select>', '''<select id="grp">
      <option value="">Todas as cores</option><option value="preto lavado/desbotado">Preto lavado/desbotado</option>
      <option value="carvão/chumbo/cinza escuro">Carvão / chumbo / cinza escuro</option><option value="preto">Preto</option>
      </select>''', html, flags=re.S)
    html = html.replace('<option value="rel">Ordem: bootcut + cor primeiro</option>', '<option value="rel">Ordem: medida 58–62 + cor primeiro</option>')
    html = html.replace("const silRank = {\"bootcut/flare\":0,\"reta/slim\":1,\"não informada\":2}, grpRank = {\"outra\":0,\"indefinida\":1,\"azul/preto\":2};",
                        "const silRank = {\"regular\":0,\"cropped\":1,\"—\":2}, grpRank = {};")
    html = html.replace("else list.sort((a,b) => silRank[a.sil] - silRank[b.sil] || grpRank[a.grp] - grpRank[b.grp] ||",
                        "else list.sort((a,b) => (b.in_stock - a.in_stock) || a.mrank - b.mrank || a.prio - b.prio || silRank[a.sil] - silRank[b.sil] ||")
    html = html.replace('const silTag = r.sil === "bootcut/flare" ? "bootcut/flare" : (r.sil === "reta/slim" ? "reta/slim" : "");',
                        'const silTag = r.mrank === 0 ? "58–62 cm ✓" : (r.mrank === 1 ? "≈ 58–62 cm" : "");')
    html = html.replace('"preto":"#1d1d1d",', '"preto":"#1d1d1d","preto lavado/desbotado":"#3b3a39","carvão/chumbo/cinza escuro":"#4a4c4f",')
    sub = (f"{len(rows)} camisetas de {len({r['marca'] for r in rows})} marcas (indie + varejo). Lisas, gola careca, "
           f"sem oversized/boxy/slim. Medidas e cor vêm do texto da loja — confira na foto.")
    html = html.replace("__SUB__", sub).replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    open(os.path.join(HERE, "camisetas.html"), "w").write(html)


def main():
    rows = analisa()
    write_md(rows)
    write_html(rows)
    from collections import Counter
    print(len(rows), "camisetas;", sum(r["in_stock"] for r in rows), "disponíveis")
    print("medida:", Counter(r["mrank"] for r in rows), "cor:", Counter(r["cor"] for r in rows))


if __name__ == "__main__":
    main()
