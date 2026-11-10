"""Varre cada loja e salva os produtos brutos em cache/stores/<dominio>.json.

Ordem: Shopify (/products.json) -> Nuvemshop (sitemap + categorias de calça + página de produto)
       -> WooCommerce (Store API) -> VTEX (API pública de catálogo) -> genérico (JSON-LD / og:).

Uso:  python scraper.py [--only dom1,dom2] [--limit N] [--workers 6] [--force]
"""
import argparse
import gzip
import hashlib
import html as htmlmod
import json
import os
import random
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STORES = os.path.join(CACHE, "stores")
PAGES = os.path.join(CACHE, "pages")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")
TIMEOUT = 15
MAX_PRODUCT_PAGES = 120  # por loja (Nuvemshop/genérico)

PANTS_SLUG = re.compile(
    r"cal[cç]a|jeans?\b|jean-|denim|pants?\b|pant-|trouser|bootcut|boot-cut|flare|bootleg|bottom|sarja|cotele|"
    r"veludo|carpinteir|work-?pant|calc", re.I)
PANTS_CATEGORY = re.compile(r"/(calcas?|calças?|pants|jeans|denim|bottoms?|trousers?)(/|$|-)", re.I)
SIZE_BLOCK = re.compile(r"size|medida|talle|tabela|guia|measure", re.I)
JUNK_IMG = re.compile(r"pinterest|facebook|whatsapp|twitter|icon|logo|payment|pagamento|selo|\.svg|pixel|PinExt", re.I)
NON_PRODUCT_EXT = re.compile(r"\.(jpg|jpeg|png|webp|gif|svg|css|js|pdf|xml|gz)(\?|$)", re.I)


class Blocked(Exception):
    pass


class Offline(Exception):
    pass


class Http:
    """Sessão por loja: robots.txt, pausa 1–2 s, timeout 15 s, UA de navegador."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                               "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
        self.last = 0.0
        self.robots = None
        self.nreq = 0

    def _sleep(self):
        wait = random.uniform(1.0, 2.0) - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()

    def load_robots(self):
        rp = RobotFileParser()
        try:
            self._sleep()
            r = self.s.get(self.base + "/robots.txt", timeout=TIMEOUT)
            self.nreq += 1
            if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                rp.parse(r.text.splitlines())
            else:
                rp.parse([])
        except requests.RequestException:
            rp.parse([])
        self.robots = rp

    def allowed(self, url):
        if self.robots is None:
            return True
        path = urlparse(url)
        # o robotparser do Python não entende curingas '*'; tratamos os padrões mais comuns manualmente
        if not self.robots.can_fetch(UA, url):
            return False
        for line in getattr(self, "_wild", []):
            if re.match(line, path.path + ("?" + path.query if path.query else "")):
                return False
        return True

    def get(self, url, accept_json=False, allow_404=True):
        if not self.allowed(url):
            return None
        self._sleep()
        try:
            r = self.s.get(url, timeout=TIMEOUT, allow_redirects=True)
        except requests.exceptions.SSLError as e:
            raise Offline(f"SSL: {str(e)[:80]}")
        except (requests.ConnectionError, requests.Timeout) as e:
            raise Offline(type(e).__name__)
        finally:
            self.nreq += 1
        if r.status_code in (401, 403, 429) or (r.status_code == 503 and "cloudflare" in r.text.lower()):
            if "challenge" in r.text.lower() or "cf-" in r.text.lower() or r.status_code in (403, 429):
                raise Blocked(f"HTTP {r.status_code}")
        if r.status_code >= 500:
            raise Offline(f"HTTP {r.status_code}")
        if r.status_code == 404 and allow_404:
            return None
        if r.status_code != 200:
            return None
        return r


def _wild_rules(text):
    """Converte linhas Disallow com '*' do bloco 'User-agent: *' em regex."""
    rules, active = [], False
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            active = v == "*"
        elif k == "disallow" and active and "*" in v:
            rx = "^" + re.escape(v).replace(r"\*", ".*").replace(r"\$", "$")
            rules.append(rx)
    return rules


# ---------------------------------------------------------------- cache por página

def page_cache(domain, url):
    d = os.path.join(PAGES, domain)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")


# ---------------------------------------------------------------- extração genérica de página de produto

def ld_objects(soup):
    out = []
    for s in soup.find_all("script", type="application/ld+json"):
        txt = s.string or s.get_text() or ""
        try:
            data = json.loads(txt)
        except Exception:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", txt))
            except Exception:
                continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            o = stack.pop(0)
            if isinstance(o, dict):
                out.append(o)
                for k in ("@graph", "mainEntity", "itemListElement"):
                    v = o.get(k)
                    if isinstance(v, list):
                        stack.extend(v)
                    elif isinstance(v, dict):
                        stack.append(v)
    return out


def _is_product(o):
    t = o.get("@type")
    return t == "Product" or (isinstance(t, list) and "Product" in t) or t == "ProductGroup"


def pick_main_product(objs, url):
    prods = [o for o in objs if _is_product(o)]
    if not prods:
        return None
    norm = url.rstrip("/").split("?")[0]
    for o in prods:
        for key in ("@id", "url"):
            v = o.get(key)
            if isinstance(v, str) and v.rstrip("/").split("?")[0].split("#")[0] == norm:
                return o
        mep = o.get("mainEntityOfPage")
        if isinstance(mep, dict) and str(mep.get("@id", "")).rstrip("/") == norm:
            return o
    return prods[0] if len(prods) == 1 else prods[0]


def offers_of(p):
    offs = p.get("offers") or []
    if isinstance(offs, dict):
        if offs.get("@type") == "AggregateOffer" and offs.get("offers"):
            offs = offs["offers"]
        else:
            offs = [offs]
    res = []
    for o in offs if isinstance(offs, list) else []:
        if isinstance(o, dict):
            res.append(o)
    if p.get("hasVariant"):
        for v in p["hasVariant"]:
            for o in offers_of(v):
                o = dict(o)
                o["_name"] = v.get("name")
                o["_size"] = v.get("size")
                o["_color"] = v.get("color")
                res.append(o)
    return res


def text_of(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def find_description(soup):
    cands = []
    sel = ['[data-store^="product-description"]', ".product-description", ".user-content", '[itemprop="description"]',
           ".product__description", ".product-single__description", ".woocommerce-product-details__short-description",
           "#tab-description", ".description", ".product-info", ".productDescription", "#descricao", ".descricao"]
    for s in sel:
        for el in soup.select(s):
            t = text_of(el)
            if 15 < len(t) < 20000:
                cands.append((el, t))
    if not cands:
        return "", ""
    # prefere o primeiro seletor que trouxe tabela; senão o mais longo
    with_table = [c for c in cands if c[0].find("table")]
    el, t = (with_table[0] if with_table else max(cands, key=lambda c: len(c[1])))
    return str(el), t


def meta(soup, prop):
    m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return m.get("content") if m else None


def parse_product_page(html, url):
    soup = BeautifulSoup(html, "lxml")
    objs = ld_objects(soup)
    p = pick_main_product(objs, url) or {}
    desc_html, desc_text = find_description(soup)
    if len(desc_text) < len(str(p.get("description") or "")):
        desc_text = htmlmod.unescape(str(p.get("description")))
    title = p.get("name") or meta(soup, "og:title") or (soup.title.string if soup.title else "")
    imgs = p.get("image")
    if isinstance(imgs, dict):
        imgs = imgs.get("url")
    if isinstance(imgs, str):
        imgs = [imgs]
    imgs = [i if isinstance(i, str) else i.get("url", "") for i in (imgs or [])]
    if not imgs and meta(soup, "og:image"):
        imgs = [meta(soup, "og:image")]
    # imagens extras dentro da descrição (tabelas de medida em imagem)
    desc_imgs = []
    if desc_html:
        for im in BeautifulSoup(desc_html, "lxml").find_all("img"):
            src = im.get("data-src") or im.get("src")
            if src:
                desc_imgs.append(urljoin(url, src))
    # imagens com nome/alt sugestivo de tabela de medidas, ou dentro de blocos "guia de medidas"
    size_tables = []
    for im in soup.find_all("img"):
        src = im.get("data-src") or im.get("src") or ""
        alt = (im.get("alt") or "") + " " + src
        if re.search(r"medida|tabela|size.?chart|guia.?de.?tam|sizechart|sizing|size.?guide", alt, re.I) and src:
            desc_imgs.append(urljoin(url, src))
    for blk in soup.find_all(attrs={"id": SIZE_BLOCK}) + soup.find_all(attrs={"class": SIZE_BLOCK}):
        for im in blk.find_all("img"):
            src = im.get("data-src") or im.get("src")
            if src:
                desc_imgs.append(urljoin(url, src))
    for t in soup.find_all("table"):
        tt = text_of(t).lower()
        if re.search(r"cintura|quadril|comprimento|barra|waist|hip|length|inseam|entrepernas", tt):
            size_tables.append(str(t))
    desc_imgs = [i for i in desc_imgs if not JUNK_IMG.search(i)]

    variants = []
    # Nuvemshop: data-variants (estoque por variante + preço "de")
    el = soup.find(attrs={"data-variants": True})
    if el:
        try:
            for v in json.loads(htmlmod.unescape(el["data-variants"])):
                opts = [v.get(f"option{i}") for i in range(3) if v.get(f"option{i}")]
                variants.append({"title": " / ".join(opts), "options": opts, "price": v.get("price_number"),
                                 "compare_at": v.get("compare_at_price_number"), "available": bool(v.get("available")),
                                 "stock": v.get("stock")})
        except Exception:
            pass
    option_names = []
    form = soup.select_one(".js-product-variants") or soup
    for lab in form.select(".form-label, label, .variant-label")[:6]:
        t = text_of(lab).strip(": ")
        if t and len(t) < 30:
            option_names.append(t)
    offers = offers_of(p)
    if not variants:
        for o in offers:
            avail = str(o.get("availability", "")).lower()
            variants.append({"title": o.get("_name") or o.get("name") or o.get("sku") or "",
                             "options": [x for x in (o.get("_size"), o.get("_color")) if x],
                             "price": _num(o.get("price") or o.get("lowPrice")), "compare_at": None,
                             "available": ("instock" in avail) if avail else None})
    price = None
    compare = None
    if variants:
        prices = [v["price"] for v in variants if v.get("price")]
        price = min(prices) if prices else None
        comps = [v["compare_at"] for v in variants if v.get("compare_at")]
        compare = max(comps) if comps else None
    if price is None:
        price = _num(meta(soup, "product:price:amount") or meta(soup, "nuvemshop:price"))
    # preço "de" exibido no HTML
    if compare is None:
        for s in ("#compare_price_display", ".js-compare-price-display", ".price-compare", "del .amount", "s.price",
                  ".compare-price", ".old-price"):
            el2 = soup.select_one(s)
            if el2 and _num(text_of(el2)):
                compare = _num(text_of(el2))
                break
    crumbs = [text_of(a) for a in soup.select(".breadcrumb a, .breadcrumbs a, nav[aria-label*=read] a")]
    return {
        "url": url, "title": htmlmod.unescape(str(title or "")).strip(), "description_html": desc_html,
        "description_text": desc_text, "tags": crumbs, "product_type": "",
        "option_names": option_names, "variants": variants, "price": price, "compare_at": compare,
        "image": imgs[0] if imgs else None, "extra_images": list(dict.fromkeys(desc_imgs))[:10],
        "size_tables": list(dict.fromkeys(size_tables))[:4],
        "has_ld": bool(p),
    }


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d+(?:\.\d+)?)", s)
    if not m:
        return None
    x = m.group(1)
    if "," in x:
        x = x.replace(".", "").replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


# ---------------------------------------------------------------- plataformas

def try_shopify(h, home_html):
    r = h.get(h.base + "/products.json?limit=250&page=1")
    if not r or "application/json" not in r.headers.get("content-type", ""):
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if "products" not in data:
        return None
    prods, page = [], 1
    while True:
        batch = data.get("products") or []
        if not batch:
            break
        for p in batch:
            opts = p.get("options") or []
            prods.append({
                "url": f"{h.base}/products/{p.get('handle')}", "title": p.get("title", ""),
                "description_html": p.get("body_html") or "",
                "description_text": BeautifulSoup(p.get("body_html") or "", "lxml").get_text(" ", strip=True),
                "tags": p.get("tags") if isinstance(p.get("tags"), list) else str(p.get("tags") or "").split(","),
                "product_type": p.get("product_type", ""), "option_names": [o.get("name") for o in opts],
                "variants": [{"title": v.get("title"), "options": [v.get(k) for k in ("option1", "option2", "option3")
                                                                    if v.get(k)],
                              "price": _num(v.get("price")), "compare_at": _num(v.get("compare_at_price")),
                              "available": v.get("available")} for v in p.get("variants", [])],
                "image": (p.get("images") or [{}])[0].get("src"),
                "extra_images": [i.get("src") for i in (p.get("images") or [])
                                 if re.search(r"medida|tabela|size|guia", (i.get("src") or "") + str(i.get("alt")),
                                              re.I)],
            })
        page += 1
        if len(batch) < 250 or page > 20:
            break
        r = h.get(f"{h.base}/products.json?limit=250&page={page}")
        if not r:
            break
        try:
            data = r.json()
        except ValueError:
            break
    for p in prods:
        vs = p["variants"]
        ps = [v["price"] for v in vs if v.get("price")]
        cs = [v["compare_at"] for v in vs if v.get("compare_at")]
        p["price"] = min(ps) if ps else None
        p["compare_at"] = max(cs) if cs else None
    return prods


def is_nuvemshop(html):
    return bool(re.search(r"nuvemshop|tiendanube|mitiendanube|lojavirtualnuvem", html, re.I))


def sitemap_urls(h, start_urls):
    seen, out, queue = set(), [], list(start_urls)
    while queue and len(seen) < 30:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        r = h.get(u)
        if not r:
            continue
        content = r.content
        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except OSError:
                continue
        text = content.decode("utf-8", "ignore")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
        if "<sitemapindex" in text:
            queue.extend(l for l in locs if re.search(r"product|produto|sitemap", l, re.I))
        else:
            out.extend(htmlmod.unescape(l) for l in locs)
    return out


def links_from(html, base, pattern):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        u = urljoin(base, a["href"]).split("#")[0]
        if urlparse(u).hostname and urlparse(u).hostname.removeprefix("www.") == urlparse(base).hostname.removeprefix(
                "www.") and re.search(pattern, u) and not NON_PRODUCT_EXT.search(u):
            out.append(u)
    return list(dict.fromkeys(out))


def category_pages(h, home_html, base):
    cats = [u for u in links_from(home_html, base, r".") if PANTS_CATEGORY.search(urlparse(u).path)
            and "/produtos/" not in u and "/products/" not in u and "/produto/" not in u]
    return cats[:6]


def crawl_listing(h, url, product_pat, pages=4):
    found = []
    for i in range(1, pages + 1):
        u = url if i == 1 else (url + ("&" if "?" in url else "?") + f"page={i}")
        r = h.get(u)
        if not r:
            break
        new = [l for l in links_from(r.text, h.base, product_pat) if l not in found]
        if not new:
            break
        found.extend(new)
    return found


def slim_html(html):
    """Remove CSS/JS pesado mas mantém JSON-LD; serve para cache reprocessável."""
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<svg.*?</svg>", "", html, flags=re.S | re.I)
    html = re.sub(r"<script(?![^>]*ld\+json)[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    return html


def fetch_page(h, domain, u):
    """Baixa (ou lê do cache gz) o HTML de uma página de produto. Devolve (html, url_final)."""
    cp = page_cache(domain, u).replace(".json", ".html.gz")
    if os.path.exists(cp):
        with gzip.open(cp, "rt", encoding="utf-8") as f:
            first, _, body = f.read().partition("\n")
        return body, first
    r = h.get(u)
    if not r:
        return None, None
    with gzip.open(cp, "wt", encoding="utf-8") as f:
        f.write(r.url + "\n" + slim_html(r.text))
    return r.text, r.url


def scrape_product_pages(h, domain, urls, platform):
    prods = []
    for u in urls[:MAX_PRODUCT_PAGES]:
        html, final = fetch_page(h, domain, u)
        if not html:
            continue
        try:
            rec = parse_product_page(html, final)
        except Exception as e:
            rec = {"url": u, "error": str(e)[:200]}
        if rec.get("title"):
            prods.append(rec)
    return prods


def try_nuvemshop(h, domain, home_html):
    if not is_nuvemshop(home_html):
        return None
    pat = r"/(produtos|productos|products)/[^/?#]+/?$"
    urls = sitemap_urls(h, [h.base + "/sitemap.xml"])
    prod_urls = [u for u in urls if re.search(pat, u) and not re.search(r"/(us|en|es)/products/", u)]
    picked = [u for u in prod_urls if PANTS_SLUG.search(u.rstrip("/").rsplit("/", 1)[-1])]
    for c in category_pages(h, home_html, h.base):
        picked.extend(crawl_listing(h, c, pat))
    if not prod_urls and not picked:  # sem sitemap: lista todos os produtos
        picked = crawl_listing(h, h.base + "/produtos/", pat, pages=6)
    picked = list(dict.fromkeys(u.split("?")[0] for u in picked))
    return scrape_product_pages(h, domain, picked, "nuvemshop"), len(prod_urls)


def try_woocommerce(h):
    r = h.get(h.base + "/wp-json/wc/store/products?per_page=100&page=1")
    if not r or "json" not in r.headers.get("content-type", ""):
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    prods, page = [], 1
    while data:
        for p in data:
            pr = p.get("prices") or {}
            mu = int(pr.get("currency_minor_unit") or 2)
            f = lambda x: (float(x) / 10 ** mu) if x not in (None, "") else None
            sizes = []
            for a in p.get("attributes") or []:
                for t in a.get("terms") or []:
                    sizes.append(t.get("name"))
            prods.append({
                "url": p.get("permalink"), "title": htmlmod.unescape(p.get("name", "")),
                "description_html": (p.get("description") or "") + (p.get("short_description") or ""),
                "description_text": BeautifulSoup((p.get("description") or "") + " " +
                                                  (p.get("short_description") or ""), "lxml").get_text(" ", strip=True),
                "tags": [t.get("name") for t in p.get("tags") or []] + [c.get("name") for c in p.get("categories") or []],
                "product_type": "", "option_names": [a.get("name") for a in p.get("attributes") or []],
                "variants": [{"title": s, "options": [s], "price": f(pr.get("price")), "compare_at": None,
                              "available": None} for s in sizes],
                "price": f(pr.get("price")),
                "compare_at": f(pr.get("regular_price")) if pr.get("regular_price") != pr.get("price") else None,
                "in_stock": p.get("is_in_stock"),
                "image": ((p.get("images") or [{}])[0]).get("src"), "extra_images": [],
            })
        page += 1
        if len(data) < 100 or page > 15:
            break
        r = h.get(f"{h.base}/wp-json/wc/store/products?per_page=100&page={page}")
        if not r:
            break
        try:
            data = r.json()
        except ValueError:
            break
    return prods


def try_vtex(h, home_html):
    if not re.search(r"vtex", home_html, re.I):
        return None
    prods = []
    for term in ("bootcut", "flare", "calca"):
        for frm in range(0, 200, 50):
            r = h.get(f"{h.base}/api/catalog_system/pub/products/search?ft={term}&_from={frm}&_to={frm + 49}")
            if not r:
                break
            try:
                data = r.json()
            except ValueError:
                break
            if not data:
                break
            for p in data:
                vs = []
                for it in p.get("items") or []:
                    co = ((it.get("sellers") or [{}])[0].get("commertialOffer") or {})
                    vs.append({"title": it.get("name"), "options": [it.get("name")], "price": co.get("Price"),
                               "compare_at": co.get("ListPrice") if co.get("ListPrice") != co.get("Price") else None,
                               "available": (co.get("AvailableQuantity") or 0) > 0})
                imgs = ((p.get("items") or [{}])[0].get("images") or [{}])
                prods.append({"url": p.get("link"), "title": p.get("productName", ""),
                              "description_html": p.get("description") or "",
                              "description_text": BeautifulSoup(p.get("description") or "", "lxml").get_text(" "),
                              "tags": p.get("categories") or [], "product_type": "", "option_names": [],
                              "variants": vs, "price": min([v["price"] for v in vs if v["price"]] or [0]) or None,
                              "compare_at": max([v["compare_at"] or 0 for v in vs] or [0]) or None,
                              "image": imgs[0].get("imageUrl"), "extra_images": []})
            if len(data) < 50:
                break
    uniq = {p["url"]: p for p in prods}
    return list(uniq.values()) if prods else None


def try_generic(h, domain, home_html, final_url):
    base = h.base
    host = urlparse(final_url).hostname.removeprefix("www.")
    links = links_from(home_html, final_url, r".")
    cats = [u for u in links if PANTS_CATEGORY.search(urlparse(u).path)][:5]
    cand = list(links)
    for c in cats:
        r = h.get(c)
        if r:
            cand.extend(links_from(r.text, final_url, r"."))
    sm = sitemap_urls(h, [base + "/sitemap.xml", base + "/sitemap_index.xml"])
    cand.extend(u for u in sm if (urlparse(u).hostname or "").removeprefix("www.") == host)
    cat_set = {c.rstrip("/") for c in cats}

    def looks_product(u):
        path = urlparse(u).path.rstrip("/")
        last = path.rsplit("/", 1)[-1]
        if not last or u.rstrip("/") in cat_set or PANTS_CATEGORY.search(path + "/") and path.count("/") <= 2 \
                and last.lower() in ("calcas", "calca", "pants", "jeans", "denim", "bottoms"):
            return False
        return bool(PANTS_SLUG.search(last)) and len(last) > 6
    use = list(dict.fromkeys(u.split("?")[0] for u in cand if looks_product(u)))
    prods = [p for p in scrape_product_pages(h, domain, use, "generic") if p.get("has_ld") or p.get("price")]
    return prods, len(set(cand))


# ---------------------------------------------------------------- loja

def scrape_store(brand, force=False):
    domain = brand["domain"]
    out_path = os.path.join(STORES, domain + ".json")
    if os.path.exists(out_path) and not force:
        return json.load(open(out_path))
    res = {"domain": domain, "name": brand["name"], "status": None, "platform": None, "products": [],
           "n_listed": None, "error": None, "final_url": None}
    h = None
    try:
        home = None
        for base in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
            h = Http(base)
            try:
                h._sleep()
                home = h.s.get(base + "/", timeout=TIMEOUT)
                h.nreq += 1
                break
            except requests.RequestException as e:
                res["error"] = f"{type(e).__name__}"
                home = None
        if home is None:
            raise Offline(res["error"] or "sem resposta")
        res["error"] = None
        if home.status_code in (403, 429) or (home.status_code == 503 and "cloudflare" in home.text.lower()):
            raise Blocked(f"HTTP {home.status_code} na home")
        if home.status_code >= 400:
            raise Offline(f"HTTP {home.status_code} na home")
        if "challenge" in home.url or "captcha" in home.url:
            raise Blocked("desafio anti-bot (" + urlparse(home.url).hostname + ")")
        fu = urlparse(home.url)
        h.base = f"{fu.scheme}://{fu.netloc}"
        res["final_url"] = home.url
        txt = home.text
        if re.search(r"password|senha", fu.path) or 'id="password' in txt[:20000] and "shopify" in txt.lower():
            res["status"] = "fora do ar"
            res["error"] = "loja fechada com senha"
            return _save(res, out_path)
        ttl = re.search(r"<title[^>]*>(.*?)</title>", txt, re.S | re.I)
        ttl = ttl.group(1).lower() if ttl else ""
        if re.search(r"fora de servi|temporariamente|em manuten|coming soon|em breve|opening soon|store unavailable|"
                     r"loja fechada|under construction|domain.*(sale|venda)|parked", ttl):
            res["status"], res["error"] = "fora do ar", "página: " + ttl.strip()[:60]
            return _save(res, out_path)
        h.load_robots()
        try:
            rob = h.s.get(h.base + "/robots.txt", timeout=TIMEOUT).text
            h._wild = _wild_rules(rob) if "<html" not in rob[:500].lower() else []
        except requests.RequestException:
            h._wild = []
        if not h.allowed(h.base + "/"):
            raise Blocked("robots.txt proíbe a loja")

        prods = try_shopify(h, txt)
        if prods is not None:
            res["platform"] = "shopify"
        if prods is None:
            r = try_nuvemshop(h, domain, txt)
            if r is not None:
                prods, res["n_listed"] = r
                res["platform"] = "nuvemshop"
        if prods is None:
            prods = try_woocommerce(h)
            if prods is not None:
                res["platform"] = "woocommerce"
        if prods is None:
            prods = try_vtex(h, txt)
            if prods is not None:
                res["platform"] = "vtex"
        if prods is None:
            prods, res["n_listed"] = try_generic(h, domain, txt, home.url)
            res["platform"] = "genérico"
            if not prods and len(txt) < 5000:
                res["platform"] = "genérico (JS — vazio)"
        res["products"] = prods
        res["status"] = "ok"
    except Blocked as e:
        res["status"], res["error"] = "bloqueada", str(e)
    except Offline as e:
        res["status"], res["error"] = "fora do ar", str(e)
    except Exception as e:
        res["status"], res["error"] = "erro", f"{type(e).__name__}: {str(e)[:150]}"
        traceback.print_exc()
    res["requests"] = h.nreq if h else 0
    return _save(res, out_path)


def _save(res, path):
    json.dump(res, open(path, "w"), ensure_ascii=False)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(STORES, exist_ok=True)
    brands = json.load(open(os.path.join(CACHE, "brands.json")))
    todo = [b for b in brands if b["domain"] and not b["pre_status"]]
    if a.only:
        wanted = set(a.only.split(","))
        todo = [b for b in todo if b["domain"] in wanted]
    if a.limit:
        todo = todo[:a.limit]
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(scrape_store, b, a.force): b for b in todo}
        for f in as_completed(futs):
            b = futs[f]
            r = f.result()
            with lock:
                done += 1
                print(f"[{done}/{len(todo)}] {b['domain']:<32} {r['status']:<10} {str(r['platform']):<12} "
                      f"produtos={len(r['products'])} {r.get('error') or ''}", flush=True)


if __name__ == "__main__":
    main()
