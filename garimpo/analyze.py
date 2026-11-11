"""Lê cache/stores/*.json, filtra bootcut/flare, extrai cor/tecido/medidas e gera resultado.xlsx."""
import json
import os
import re
import unicodedata

from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STORES = os.path.join(CACHE, "stores")

REF = {"cintura": 41.0, "quadril": 49.0, "comprimento": 106.0, "barra": 25.5}
FAIXA = {"cintura": (40, 42), "quadril": (48, 51), "comprimento": (104, 108), "barra": (24, 27)}


def unacc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


KEEP = re.compile(r"\bboot\s?-?cult?\b|\bbootcut\b|\bflare[ds]?\b|\bbootleg\b|\bslim flare\b")
EXCL = [
    ("baggy", r"\bbaggy\b"), ("wide", r"\bwide\b|\bwideleg\b|\bwide-leg\b"), ("barrel", r"\bbarrel\b"),
    ("balloon", r"\bballoon\b|\bbalao\b"), ("curve", r"\bcurved?\b|\bcurvada\b"), ("oversized", r"\boversized?\b"),
    ("pantalona", r"\bpantalona\b"), ("jogger", r"\bjogger\b"), ("cargo", r"\bcargos?\b"),
    ("feminina", r"\bfeminin[ao]\b|\bdama\b|\bmodeladora\b|\bbumbum\b|\bwomen'?s?\b"), ("legging", r"\blegging\b"),
]
PANTS = re.compile(r"\bcalcas?\b|\bpants?\b|\bjeans?\b|\btrousers?\b|\bdenim\b|\bbootcut\b|\bflared?\b|\bbootleg\b")
NOT_PANTS = re.compile(r"\b(camiseta|camisa|t-?shirt|tee|shorts?|bermuda|jort|saia|skirt|vestido|jaqueta|jacket|moletom|"
                       r"hoodie|blazer|bone|cap|meia|tenis|bota|boot\b(?!\s?-?cut)|sapato|clog|sandalia|colete|top|"
                       r"bolsa|cinto|kit|regata|jersey|cropped|macacao|jardineira|footwear|gift)\b")

# ---------------------------------------------------------------- cores
COLORS = [  # (regex sem acento, rótulo, grupo)
    (r"azul|blue|indigo|navy|marinho|denim blue|light wash|dark wash|medium wash|stone\b|stonewash|delave|anil|celeste|raw denim|"
     r"denim cru|washed denim|jeans claro|jeans escuro|lavagem clara|lavagem media|lavagem escura|amaciad", "azul", "azul/preto"),
    (r"preto|preta|black|blackout|negro|onix|onyx|carvao|charcoal|grafite|graphite|ink\b", "preto", "azul/preto"),
    (r"marrom|brown|cafe\b|coffee|chocolate|tabaco|tobacco|castanho|caramelo|caramel|cognac|conhaque|mocha|"
     r"terra\b|camel|havana|choco\b|cacau|cocoa", "marrom", "outra"),
    (r"ferrugem|rust|cobre|copper|terracota|telha|laranja|orange", "ferrugem/laranja", "outra"),
    (r"bege|beige|areia|sand|cru\b|crua\b|off[ -]?white|ecru|ecrue|creme|cream|bone\b|osso|natural|khaki|caqui|"
     r"marfim|ivory|nude|kraft|palha|aveia|oat|camurca|offwhite", "bege/cru", "outra"),
    (r"oliva|olive|musgo|moss|verde|green|militar|army|khaki green|sage|salvia|menta|mint|lima|lime", "verde", "outra"),
    (r"vinho|bordo|burgundy|wine|marsala|cereja|cherry|vermelh|red\b|rubi|carmim|sangue|blood", "vermelho/vinho", "outra"),
    (r"roxo|purple|lilas|lavanda|violeta|uva|ameixa|plum|berinjela", "roxo", "outra"),
    (r"cinza|grey|gray|chumbo|cimento|prata|silver|smoke|fume", "cinza", "outra"),
    (r"branc|white", "branco", "outra"),
    (r"amarel|yellow|mostarda|mustard|ocre|ochre|dourad|gold", "amarelo/ocre", "outra"),
    (r"rosa\b|pink", "rosa", "outra"),
    (r"pigment|overdye|tinted|tingid|sobretingid|garment dye", "pigmentado/overdyed", "outra"),
    (r"camuflad|camo\b", "camuflado", "outra"),
]


def colors_in(text, first_only=False):
    t = unacc(text)
    t = re.sub(r"off[ -]?white", "offwhite ecru", t)
    # cor de etiqueta/tag/linha/botão não é cor da calça
    t = re.sub(r"(etiquet|tag\b|backtab|patch|linha|costura|pesponto|botao|botoes|rebite|couro|bordad|zipe)[^.;\n]{0,60}", " ", t)
    found = []
    for rx, label, grp in COLORS:
        m = re.search(r"(?<![a-z])(" + rx + ")", t)
        if m:
            found.append((m.start(), label, grp))
    found.sort()
    if first_only and found:
        found = found[:1]
    return [(l, g) for _, l, g in found]


# ---------------------------------------------------------------- tecido
FABRICS = [("jeans/denim", r"\bjeans?\b|\bdenim\b"), ("sarja", r"\bsarja\b|\btwill\b"), ("brim", r"\bbrim\b"),
           ("veludo/cotelê", r"\bveludo\b|\bcotele\b|\bcorduroy\b|\bvelvet\b"), ("couro", r"\b(?:calca|pants?) (?:de |em )?(?:couro|leather)\b|\bcouro (?:legitimo|sintetico|ecologico) (?!(?:bovino|na|no|da|do|com))"),
           ("linho", r"\blinho\b|\blinen\b"), ("canvas/lona", r"\bcanvas\b|\blona\b"), ("moletom", r"\bmoletom\b"),
           ("nylon", r"\bnylon\b|\btactel\b"), ("alfaiataria", r"\balfaiataria\b|\btailoring\b")]


def fabric_of(text):
    t = unacc(text)
    fabs = [n for n, rx in FABRICS if re.search(rx, t)]
    oz = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:oz|onc)", t)
    comp = re.findall(r"(\d{1,3}(?:[.,]\d)?\s*%\s*(?:de\s+)?[a-z]+(?:\s+(?:organico|reciclado|ringado))?)", t)
    return (", ".join(fabs[:2]) or "", (oz.group(1).replace(",", ".") + " oz") if oz else "",
            "; ".join(dict.fromkeys(c.strip() for c in comp))[:80])


def gender_of(text):
    t = unacc(text)
    if re.search(r"unissex|unisex|agenero|genderless|sem genero", t):
        return "unissex"
    m = re.search(r"\bmasculin[oa]\b|\bmen\b|\bmale\b", t)
    f = re.search(r"\bfeminin[oa]\b|\bwomen\b|\bfemale\b", t)
    if m and f:
        return "unissex"
    return "masculino" if m else ("feminino" if f else "não indicado")


# ---------------------------------------------------------------- tamanhos
SIZE_TOK = r"(?:PP|P|M|G|GG|XG|XGG|EG|EGG|G1|G2|G3|XS|S|L|XL|XXL|2XL|3XL|U|ÚNICO|UNICO|3[0-9]|4[0-9]|5[0-6])"
SIZE_RX = re.compile(r"^" + SIZE_TOK + r"$")


def size_of_variant(v):
    for o in v.get("options") or [str(v.get("title") or "")]:
        o = str(o).strip().upper()
        for part in re.split(r"\s*/\s*|\s+-\s+", o):
            if SIZE_RX.match(part.strip()):
                return part.strip()
    return str(v.get("title") or "").strip()


# ---------------------------------------------------------------- medidas
MEAS = [  # (campo, regex sem acento) — ordem importa (entrepernas antes de comprimento)
    ("entrepernas", r"entre ?pernas?|entreperna|inseam|interno"),
    ("cintura", r"cintura|cos\b|waist"),
    ("quadril", r"quadril|hip"),
    ("barra", r"barra|boca|hem|bainha|leg opening"),
    ("gancho", r"gancho|rise"),
    ("coxa", r"coxa|thigh"),
    ("joelho", r"joelho|knee"),
    ("comprimento", r"comprimento|altura|length|lateral|externo|total"),
]


def meas_key(label):
    t = unacc(label)
    for k, rx in MEAS:
        if re.search(rx, t):
            return k
    return None


def _nums(s):
    return [float(x.replace(",", ".")) for x in re.findall(r"\d{1,3}(?:[.,]\d{1,2})?", s)]


def norm_size(s):
    s = re.sub(r"^TAM(ANHO)?\.?", "", unacc(s).upper().strip()).replace(".", "").strip(" :-")
    return s.upper()


def parse_tables(htmls):
    """Cada tabela -> {tamanho: {medida: valor}}"""
    out = {}
    for h in htmls:
        soup = BeautifulSoup(h, "lxml")
        for t in soup.find_all("table"):
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in t.find_all("tr")]
            rows = [r for r in rows if any(x for x in r)]
            if len(rows) < 2:
                continue
            header = rows[0]
            # orientação A: cabeçalho = medidas, 1ª coluna = tamanhos
            keysA = [meas_key(c) for c in header]
            if sum(1 for k in keysA if k) >= 2:
                for r in rows[1:]:
                    sz = norm_size(r[0])
                    for k, c in zip(keysA, r):
                        if k and _nums(c):
                            out.setdefault(sz, {})[k] = _nums(c)[0]
                continue
            # orientação B: 1ª coluna = medidas, cabeçalho = tamanhos
            sizes = [norm_size(c) for c in header[1:]] if len(header) > 1 else []
            if not sizes:
                continue
            for r in rows[1:]:
                k = meas_key(r[0]) if r else None
                if not k:
                    continue
                for sz, c in zip(sizes, r[1:]):
                    if _nums(c):
                        out.setdefault(sz, {})[k] = _nums(c)[0]
    return {s: m for s, m in out.items() if s and len(s) <= 6}


SZ_IN_TEXT = re.compile(r"(?:(?<=\s)|^|(?<=[(\[|/]))(?:[Tt][Aa][Mm](?:[Aa][Nn][Hh][Oo])?\.?\s*)?(" + SIZE_TOK + r")(?=\s*[:\-–)|\]]|\s+(?:cintura|quadril|"
                        r"comprimento|barra|boca|cos|waist))", re.I)


HDR_WORD = r"(?:cintura|quadril|comprimento(?: total| lateral| externo)?|barra|boca|gancho(?: frontal| traseiro)?|" \
           r"coxa|joelho|entre ?pernas?|cos|waist|hip|length|inseam|rise|thigh|hem|leg opening)"


def parse_header_rows(text):
    """'Tam. Cintura Quadril Comprimento Barra P 41 56 108 28 M 43 57,5 109 29' -> tabela."""
    t = unacc(text)
    best = {}
    for hm in re.finditer(r"((?:" + HDR_WORD + r")(?:\s*\(?cm\)?)?(?:\s*[|/,;:\-]?\s*(?:" + HDR_WORD +
                          r")(?:\s*\(?cm\)?)?){1,7})", t):
        keys = [meas_key(w) for w in re.findall(HDR_WORD, hm.group(1))]
        n = len(keys)
        rest = t[hm.end():hm.end() + 600]
        rx = re.compile(r"(?:^|\s|\|)(" + SIZE_TOK.lower() + r")\s*[:|\-]?" +
                        r"".join(r"\s*[|/;]?\s*(\d{1,3}(?:[.,]\d{1,2})?)(?:\s*cm)?" for _ in range(n)) + r"(?=\s|$|\|)")
        out, pos = {}, 0
        for m in rx.finditer(rest):
            if out and m.start() - pos > 25:
                break
            pos = m.end()
            out[norm_size(m.group(1))] = {k: float(v.replace(",", ".")) for k, v in zip(keys, m.groups()[1:]) if k}
        if len(out) > len(best):
            best = out
    return best


def parse_text(text):
    """Heurística para medidas em texto corrido."""
    out = parse_header_rows(text)
    if out:
        return out
    # estilo 1: "P: cintura 41 cm / quadril 49 ..." (tamanho primeiro)
    toks = list(re.finditer(r"(?P<size>(?:(?<=\s)|^)(?:[Tt][Aa][Mm](?:[Aa][Nn][Hh][Oo])?\.?\s*)?" + SIZE_TOK +
                            r"(?=\s*[:\-–]|\s*\)|\s+(?:cintura|quadril|comprimento|barra)))|"
                            r"(?P<meas>[A-Za-zÀ-ÿ ]{3,25}?)\s*[:\-=]?\s*(?P<num>\d{1,3}(?:[.,]\d{1,2})?)\s*(?:cm)?", text))
    cur = None
    for m in toks:
        if m.group("size"):
            cur = norm_size(m.group("size"))
        elif cur and m.group("meas"):
            k = meas_key(m.group("meas"))
            if k and k not in out.get(cur, {}):
                out.setdefault(cur, {})[k] = float(m.group("num").replace(",", "."))
    if sum(len(v) for v in out.values()) >= 2:
        return out
    # estilo 2: "Cintura: P 40 | M 42 | G 44" (medida primeiro)
    out = {}
    for seg in re.split(r"(?=(?:cintura|quadril|comprimento|barra|boca|gancho|coxa|entrepernas)\b)", text, flags=re.I):
        k = meas_key(seg[:25])
        if not k:
            continue
        for sm in re.finditer(r"\b(" + SIZE_TOK + r")\s*[:=\-]?\s*(\d{1,3}(?:[.,]\d)?)\s*(?:cm)?", seg[:200]):
            out.setdefault(norm_size(sm.group(1)), {})[k] = float(sm.group(2).replace(",", "."))
    if sum(len(v) for v in out.values()) >= 2:
        return out
    # estilo 3: medidas de uma peça só ("Cintura 41cm, Quadril 50cm..." sem tamanho) -> tamanho "?"
    single = {}
    for m in re.finditer(r"(cintura|quadril|comprimento|barra|boca|gancho|coxa|entre ?pernas?)[^0-9]{0,20}?"
                         r"(\d{1,3}(?:[.,]\d)?)\s*cm", unacc(text)):
        k = meas_key(m.group(1))
        single.setdefault(k, float(m.group(2).replace(",", ".")))
    return {"(único)": single} if len(single) >= 2 else {}


def normalize_meas(m):
    """Circunferência -> largura; anota conversões."""
    notes = []
    m = dict(m)
    if m.get("cintura") and m["cintura"] > 60:
        m["cintura"] /= 2
        notes.append("cintura em circunferência (÷2)")
    if m.get("quadril") and m["quadril"] > 70:
        m["quadril"] /= 2
        notes.append("quadril em circunferência (÷2)")
    if m.get("barra") and m["barra"] > 36:
        m["barra"] /= 2
        notes.append("barra em circunferência (÷2)")
    if m.get("coxa") and m["coxa"] > 45:
        m["coxa"] /= 2
    if m.get("comprimento") and not (85 <= m["comprimento"] <= 130):
        if 60 <= m["comprimento"] < 85:
            m["entrepernas"] = m.pop("comprimento")
            notes.append("comprimento parece entrepernas")
        else:
            m.pop("comprimento")
    return m, notes


def best_size(table):
    best = None
    for sz, raw in table.items():
        m, notes = normalize_meas(raw)
        comp = [k for k in REF if m.get(k)]
        if not comp:
            continue
        diffs = {k: round(m[k] - REF[k], 1) for k in comp}
        w = {"cintura": 1.5, "quadril": 1.2, "barra": 1.0, "comprimento": 0.4}
        missing = 4 - len(comp)
        score = sum(abs(d) * w[k] for k, d in diffs.items()) / sum(w[k] for k in comp) + missing * 1.0
        if best is None or score < best[0]:
            best = (score, sz, m, diffs, notes)
    return best


def verdict(diffs, m):
    if not diffs:
        return "faltam medidas"
    out = []
    if all(abs(d) <= 1.5 for d in diffs.values()) and len(diffs) >= 3:
        return "próxima"
    if diffs.get("quadril", 0) > 2:
        out.append("quadril mais solto")
    if diffs.get("barra", 0) > 1.5:
        out.append("barra mais aberta")
    if diffs.get("barra", 0) < -2:
        out.append("barra mais fechada")
    if diffs.get("comprimento", 0) > 2:
        out.append("mais longa")
    if diffs.get("comprimento", 0) < -2:
        out.append("mais curta")
    if diffs.get("cintura", 0) > 2:
        out.append("cintura maior")
    if diffs.get("cintura", 0) < -2:
        out.append("cintura menor")
    if len(diffs) < 3:
        out.append("faltam medidas" if not out else "medidas parciais")
    return "; ".join(out) or "próxima"


# ---------------------------------------------------------------- produto

def analyze_product(p, brand):
    title = p.get("title") or ""
    tags = [str(t) for t in (p.get("tags") or []) if t]
    desc = p.get("description_text") or ""
    head = unacc(" ".join([title, p.get("product_type") or "", " ".join(tags)]))
    full = unacc(" ".join([title, desc, p.get("product_type") or "", " ".join(tags)]))
    if NOT_PANTS.search(unacc(title)) and not re.search(r"\bcalcas?\b|\bpants?\b", unacc(title)):
        return None, False
    is_pants = bool(PANTS.search(head) or re.search(r"\bcalcas?\b|\bpants\b", unacc(desc[:300])))
    if not KEEP.search(full):
        return None, is_pants
    kws = set(m.group(0).strip() for m in KEEP.finditer(full))
    if kws <= {"bootleg"} and not re.search(r"\bcalcas?\b|\bpants?\b|\bjeans?\b|\bdenim\b|\btrousers?\b", unacc(title)):
        return None, is_pants  # "bootleg" de camisa/produto não oficial
    if not is_pants:
        return None, False
    rec = {"marca": brand, "nome": title, "url": p.get("url"), "imagem": p.get("image")}
    # exclusões
    reasons = []
    alert = ""
    for name, rx in EXCL:
        where = "título/tags" if re.search(rx, head) else ("descrição" if re.search(rx, unacc(desc)) else None)
        if not where:
            continue
        if name == "wide" and re.search(r"boot\s?-?cut\s+wide|wide\s+boot\s?-?cut", full):
            alert = "possivelmente larga"
            continue
        # "feminina" na descrição/tags não descarta peça também marcada como masculina/unissex;
        # no título do produto, descarta sempre
        if name == "feminina" and not re.search(rx, unacc(title)) and \
                re.search(r"unissex|unisex|masculin|\bmen\b", full):
            continue
        reasons.append(f"{name} ({where})")
    rec["alerta"] = alert
    # variantes
    vs = p.get("variants") or []
    avail = [size_of_variant(v) for v in vs if v.get("available")]
    sold = [size_of_variant(v) for v in vs if v.get("available") is False]
    unknown = [size_of_variant(v) for v in vs if v.get("available") is None]
    rec["tam_disponiveis"] = ", ".join(dict.fromkeys(avail))
    rec["tam_esgotados"] = ", ".join(x for x in dict.fromkeys(sold) if x not in avail)
    if unknown and not avail and not sold:
        rec["tam_disponiveis"] = ", ".join(dict.fromkeys(unknown)) + (" (estoque n/d)" if p.get("in_stock") is None
                                                                     else (" (em estoque)" if p.get("in_stock")
                                                                           else " (esgotado)"))
    if avail and not any(avail):
        rec["tam_disponiveis"] = "em estoque (tamanhos não listados)"
    if sold and not any(sold) and not avail:
        rec["tam_esgotados"] = "esgotado"
    rec["n_disp"] = len(set(avail)) if avail else (1 if p.get("in_stock") else 0)
    # cor: título > variantes > descrição
    var_txt = " ".join(" ".join(map(str, v.get("options") or [])) for v in vs)
    cs = colors_in(title)
    src = "título"
    if not cs:
        cs, src = colors_in(var_txt), "variante"
    if not cs:
        slug = (p.get("url") or "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        cs, src = colors_in(slug), "URL"
    if not cs:
        cs, src = colors_in(desc[:600], first_only=True), "descrição"
    labels = list(dict.fromkeys(c[0] for c in cs))
    grp = "outra" if any(g == "outra" for _, g in cs) else ("azul/preto" if cs else "indefinida")
    # "azul" de denim + cor de tingimento: título prevalece
    rec["cor"] = ", ".join(labels) if labels else "não identificada"
    rec["cor_fonte"] = src if labels else ""
    rec["grupo_cor"] = grp
    fab, oz, comp = fabric_of(title + " " + desc)
    rec["tecido"], rec["gramatura"], rec["composicao"] = fab, oz, comp
    rec["preco"] = p.get("price")
    rec["preco_de"] = p.get("compare_at") if p.get("compare_at") and p.get("price") and \
        p["compare_at"] > p["price"] else None
    rec["genero"] = gender_of(full)
    # medidas
    tables = [p.get("description_html") or ""] + (p.get("size_tables") or [])
    tab = parse_tables(tables)
    if not tab:
        tab = parse_text(desc)
    best = best_size(tab) if tab else None
    rec["obs_medidas"] = ""
    rec["img_tabela"] = ""
    if best:
        score, sz, m, diffs, notes = best
        rec["tam_sugerido"] = sz
        for k in REF:
            rec[f"{k}"] = round(m[k], 1) if m.get(k) else None
            rec[f"dif_{k}"] = diffs.get(k)
        rec["entrepernas"] = m.get("entrepernas")
        rec["parecer"] = verdict(diffs, m)
        fora = [k for k, (lo, hi) in FAIXA.items() if m.get(k) and not (lo <= m[k] <= hi)]
        if fora:
            notes.append("fora da faixa: " + ", ".join(fora))
        if m.get("entrepernas") and not m.get("comprimento"):
            notes.append("só entrepernas (não comparado c/ 106)")
        rec["obs_medidas"] = "; ".join(notes)
        rec["score"] = score
    else:
        rec["tam_sugerido"] = ""
        for k in REF:
            rec[k] = None
            rec[f"dif_{k}"] = None
        rec["entrepernas"] = None
        rec["score"] = None
        imgs = p.get("extra_images") or []
        if imgs:
            rec["parecer"] = "tabela em imagem — conferir manualmente"
            rec["img_tabela"] = imgs[0]
        else:
            rec["parecer"] = "faltam medidas"
    rec["motivo_descarte"] = "; ".join(reasons)
    return rec, True


# ---------------------------------------------------------------- planilha

COLS = [("marca", 16), ("nome", 40), ("url", 45), ("cor", 16), ("grupo_cor", 11), ("tecido", 14), ("gramatura", 9),
        ("composicao", 22), ("preco", 9), ("preco_de", 9), ("tam_disponiveis", 22), ("tam_esgotados", 18),
        ("genero", 11), ("tam_sugerido", 8), ("parecer", 26), ("cintura", 8), ("dif_cintura", 8), ("quadril", 8),
        ("dif_quadril", 8), ("comprimento", 8), ("dif_comprimento", 8), ("barra", 8), ("dif_barra", 8),
        ("entrepernas", 8), ("obs_medidas", 30), ("img_tabela", 30), ("alerta", 14), ("imagem", 40)]
HEAD = {"preco": "preço", "preco_de": "preço de", "tam_disponiveis": "tamanhos disponíveis",
        "tam_esgotados": "esgotados", "genero": "gênero", "tam_sugerido": "tam. sugerido", "composicao": "composição",
        "dif_cintura": "Δ cint.", "dif_quadril": "Δ quad.", "dif_comprimento": "Δ comp.", "dif_barra": "Δ barra",
        "obs_medidas": "obs. medidas", "img_tabela": "imagem tabela", "grupo_cor": "grupo cor",
        "imagem": "1ª imagem"}


def write_sheet(ws, rows, cols):
    ws.append([HEAD.get(c, c) for c, _ in cols])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="5A3E2B")
    for r in rows:
        ws.append([r.get(c) for c, _ in cols])
    for i, (c, w) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        if c in ("url", "imagem", "img_tabela", "instagram", "loja"):
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                cell = row[0]
                if cell.value and str(cell.value).startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = Font(color="0563C1", underline="single")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def rank_key(r):
    grp = {"outra": 0, "indefinida": 1, "azul/preto": 2}[r["grupo_cor"]]
    if r["parecer"] == "próxima":
        mb = 0
    elif r.get("score") is not None:
        mb = 1
    elif "imagem" in r["parecer"]:
        mb = 2
    else:
        mb = 3
    return (grp, mb, r.get("score") if r.get("score") is not None else 99, -r["n_disp"], 1 if r["alerta"] else 0)


def main(out="resultado.xlsx"):
    brands = json.load(open(os.path.join(CACHE, "brands.json")))
    _mass = os.path.join(CACHE, "brands_mass.json")
    if os.path.exists(_mass):
        _known = {b["domain"] for b in brands}
        brands += [b for b in json.load(open(_mass)) if b["domain"] not in _known]
    cands, disc, marcas = [], [], []
    final_hosts = {}
    for b in brands:
        row = {"marca": b["name"], "instagram": b["instagram"], "loja": b["shop_url"] or "", "regiao": b["region"],
               "fonte": b["source"], "plataforma": "", "produtos": 0, "calcas": 0, "bootcut": 0, "obs": ""}
        if b["pre_status"]:
            row["status"] = b["pre_status"]
            marcas.append(row)
            continue
        path = os.path.join(STORES, b["domain"] + ".json")
        if not os.path.exists(path):
            row["status"] = "não varrida"
            marcas.append(row)
            continue
        s = json.load(open(path))
        fh = (re.sub(r"^https?://(www\.)?", "", s.get("final_url") or "").split("/")[0])
        if fh and fh in final_hosts and s["status"] == "ok":
            row["status"] = "duplicada"
            row["obs"] = f"mesma loja que {final_hosts[fh]} ({fh})"
            marcas.append(row)
            continue
        if fh:
            final_hosts[fh] = b["name"]
        row["plataforma"] = s.get("platform") or ""
        row["produtos"] = len(s["products"])
        if s["status"] != "ok":
            row["status"] = s["status"] if s["status"] in ("bloqueada", "fora do ar") else "erro"
            row["obs"] = s.get("error") or ""
            marcas.append(row)
            continue
        n_pants = n_boot = 0
        seen = set()
        for p in s["products"]:
            key = (p.get("url") or p.get("title") or "").rstrip("/")
            if re.search(r"^https?://[^/]+/[a-z]{2}/", p.get("url") or "") and "/products/" not in (p.get("url") or "")[:12] \
                    and s.get("platform") == "nuvemshop":
                continue  # cópia em outro idioma/moeda (Nuvemshop internacional)
            k2 = (re.sub(r"\W*\(?copia\)?\s*$", "", unacc(p.get("title") or "")).strip(), p.get("price"),
                  re.sub(r"[-_]?[a-z0-9]{0,1}\d*$", "", (p.get("url") or "").rstrip("/").rsplit("/", 1)[-1]))
            if key in seen or k2 in seen:
                continue
            seen.add(key)
            seen.add(k2)
            rec, pants = analyze_product(p, b["name"])
            n_pants += pants
            if not rec:
                continue
            n_boot += 1
            (disc if rec["motivo_descarte"] else cands).append(rec)
        row["calcas"], row["bootcut"] = n_pants, n_boot
        if not s["products"]:
            row["status"] = "sem calças"
            row["obs"] = "nenhum produto extraído" + (f" ({s['platform']})" if s.get("platform") else "")
        elif n_pants == 0:
            row["status"] = "sem calças"
        elif n_boot == 0:
            row["status"] = "sem bootcut"
        else:
            row["status"] = "varrida"
        if s.get("platform") in ("nuvemshop", "genérico") and s.get("n_listed"):
            row["obs"] = (row["obs"] + f" {s['n_listed']} produtos no sitemap; abertos só os de calça").strip()
        marcas.append(row)

    cands.sort(key=rank_key)
    cor = [r for r in cands if r["grupo_cor"] != "azul/preto"]
    azp = [r for r in cands if r["grupo_cor"] == "azul/preto"]
    instock = [r for r in cands if r["n_disp"] > 0 and r["grupo_cor"] != "azul/preto"]
    top = instock[:15]
    if len(top) < 15:
        top += [r for r in cands if r not in top][:15 - len(top)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Top 15"
    top_cols = [("marca", 16), ("nome", 40), ("url", 45), ("preco", 9), ("preco_de", 9), ("cor", 16),
                ("tecido", 14), ("gramatura", 9), ("tam_sugerido", 8), ("parecer", 26), ("dif_cintura", 8),
                ("dif_quadril", 8), ("dif_comprimento", 8), ("dif_barra", 8), ("tam_disponiveis", 22),
                ("obs_medidas", 30), ("img_tabela", 30), ("alerta", 14), ("genero", 11)]
    write_sheet(ws, top, top_cols)
    write_sheet(wb.create_sheet("Candidatas cor"), cor, COLS)
    write_sheet(wb.create_sheet("Candidatas azul-preto"), azp, COLS)
    write_sheet(wb.create_sheet("Descartadas"), disc, [("motivo_descarte", 28)] + COLS[:5] + [("preco", 9)])
    mcols = [("marca", 22), ("status", 22), ("plataforma", 12), ("instagram", 38), ("loja", 38), ("regiao", 8),
             ("fonte", 12), ("produtos", 9), ("calcas", 8), ("bootcut", 8), ("obs", 50)]
    HEAD.update({"produtos": "produtos analisados", "calcas": "calças", "bootcut": "bootcut/flare", "regiao": "região"})
    write_sheet(wb.create_sheet("Marcas"), marcas, mcols)
    wb.save(os.path.join(HERE, out))
    json.dump({"top": top, "cor": cor, "azp": azp, "disc": disc, "marcas": marcas},
              open(os.path.join(CACHE, "analise.json"), "w"), ensure_ascii=False, indent=1, default=str)
    return top, cor, azp, disc, marcas


if __name__ == "__main__":
    import sys
    from collections import Counter
    top, cor, azp, disc, marcas = main(*(sys.argv[1:2] or []))
    print("candidatas cor:", len(cor), "| azul/preto:", len(azp), "| descartadas:", len(disc))
    print(Counter(m["status"] for m in marcas))
    for r in top:
        print(f"- {r['marca']} | {r['nome']} | {r['cor']} | R${r['preco']} | {r['tam_sugerido']} {r['parecer']} "
              f"| disp: {r['tam_disponiveis']} | {r['url']}")
