"""Gera lista_calcas.html: visualizador simples (busca + filtros) das mesmas calças do lista_calcas.md.

Uso: python lista_html.py
"""
import json
import re
import os

import lista_md as L

OUT = os.path.join(L.A.HERE, "lista_calcas.html")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calças de marcas brasileiras</title>
<style>
  :root { --bg:#faf8f5; --card:#fff; --ink:#2b2420; --muted:#7a6f66; --line:#e7e1da; --accent:#7a4a2b; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#1b1816; --card:#25211e; --ink:#eee8e2; --muted:#a59a90; --line:#3a332e; --accent:#d29a6c; }
  }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.4 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:var(--bg); color:var(--ink); }
  header { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line); padding:12px 16px; }
  h1 { font-size:18px; margin:0 0 4px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:10px; }
  .filters { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  input[type=search], select { font:inherit; padding:7px 10px; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--ink); }
  input[type=search] { flex:1 1 220px; min-width:180px; }
  label.chk { display:flex; gap:6px; align-items:center; font-size:14px; white-space:nowrap; }
  .count { color:var(--muted); font-size:13px; margin-left:auto; }
  main { padding:16px; display:grid; grid-template-columns:repeat(auto-fill, minmax(210px, 1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; display:flex; flex-direction:column; text-decoration:none; color:inherit; }
  .card:hover { border-color:var(--accent); }
  .img { aspect-ratio:3/4; background:var(--line) center/cover no-repeat; position:relative; }
  .tag { position:absolute; top:8px; left:8px; background:rgba(0,0,0,.65); color:#fff; font-size:11px; padding:2px 7px; border-radius:20px; }
  .out { position:absolute; top:8px; right:8px; background:#b33; color:#fff; font-size:11px; padding:2px 7px; border-radius:20px; }
  .body { padding:10px 12px 12px; display:flex; flex-direction:column; gap:4px; flex:1; }
  .brand { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }
  .name { font-weight:600; font-size:14px; }
  .meta { font-size:12px; color:var(--muted); }
  .price { margin-top:auto; font-weight:700; }
  .price s { font-weight:400; color:var(--muted); font-size:12px; margin-left:4px; }
  .sizes { font-size:12px; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; vertical-align:middle; border:1px solid var(--line); }
  .empty { grid-column:1/-1; text-align:center; color:var(--muted); padding:40px; }
  button.more { grid-column:1/-1; justify-self:center; font:inherit; padding:9px 18px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--ink); cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>Calças de marcas brasileiras</h1>
  <div class="sub">__SUB__</div>
  <div class="filters">
    <input type="search" id="q" placeholder="Buscar (nome, marca, cor, tecido)…">
    <select id="sil">
      <option value="">Todas as silhuetas</option>
      <option value="bootcut/flare">Bootcut / flare</option>
      <option value="reta/slim">Reta / slim / straight</option>
      <option value="não informada">Modelagem não informada</option>
    </select>
    <select id="grp">
      <option value="">Todas as cores</option>
      <option value="outra">Fora do azul/preto</option>
      <option value="indefinida">Cor não identificada</option>
      <option value="azul/preto">Azul / preto</option>
    </select>
    <select id="brand"><option value="">Todas as marcas</option></select>
    <select id="sort">
      <option value="rel">Ordem: bootcut + cor primeiro</option>
      <option value="asc">Preço ↑</option>
      <option value="desc">Preço ↓</option>
      <option value="brand">Marca A–Z</option>
    </select>
    <label class="chk"><input type="checkbox" id="stock" checked> só disponíveis</label>
    <span class="count" id="count"></span>
  </div>
</header>
<main id="grid"></main>
<script>
const DATA = __DATA__;
const COLORS = {"marrom":"#7b4a2a","ferrugem/laranja":"#b5532a","bege/cru":"#e2d3b5","verde":"#5f6f3a","vermelho/vinho":"#7d1f2a",
  "roxo":"#6b4a7a","cinza":"#8a8a8a","branco":"#f4f4f4","amarelo/ocre":"#c9a23a","rosa":"#e3a1b4","azul":"#36577d",
  "preto":"#1d1d1d","pigmentado/overdyed":"linear-gradient(135deg,#7b4a2a,#5f6f3a)","camuflado":"#6b6b4a"};
const $ = id => document.getElementById(id);
const silRank = {"bootcut/flare":0,"reta/slim":1,"não informada":2}, grpRank = {"outra":0,"indefinida":1,"azul/preto":2};
const brl = v => v == null ? "" : v.toLocaleString("pt-BR", {style:"currency", currency:"BRL"});
const norm = s => (s||"").normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
DATA.forEach(r => r._q = norm([r.nome, r.marca, r.cor, r.tecido].join(" ")));
[...new Set(DATA.map(r => r.marca))].sort((a,b)=>a.localeCompare(b)).forEach(m => {
  const o = document.createElement("option"); o.value = o.textContent = m; $("brand").appendChild(o);
});
let shown = 0, list = [];
const PAGE = 120;
function card(r) {
  const dots = r.cor.split(", ").map(c => COLORS[c] ? `<span class="dot" style="background:${COLORS[c]}"></span>` : "").join("");
  const silTag = r.sil === "bootcut/flare" ? "bootcut/flare" : (r.sil === "reta/slim" ? "reta/slim" : "");
  const layers = [r.img, r.thumb].filter(Boolean).map(u => `url('${esc(u)}')`).join(",");
  const img = layers ? `style="background-image:${layers}"` : "";
  return `<a class="card" href="${esc(r.url)}" target="_blank" rel="noopener">
    <div class="img" ${img}>${silTag ? `<span class="tag">${silTag}</span>` : ""}${r.in_stock ? "" : '<span class="out">esgotada</span>'}</div>
    <div class="body">
      <div class="brand">${esc(r.marca)}</div>
      <div class="name">${esc(r.nome)}</div>
      <div class="meta">${dots}${esc(r.cor === "?" ? "cor não identificada" : r.cor)}${r.tecido ? " · " + esc(r.tecido) : ""}</div>
      <div class="sizes">${r.in_stock ? esc(r.disp) : ""}</div>
      <div class="price">${brl(r.preco)}${r.de ? `<s>${brl(r.de)}</s>` : ""}</div>
    </div></a>`;
}
function render(more) {
  const g = $("grid");
  if (!more) { g.innerHTML = ""; shown = 0; }
  const old = g.querySelector("button.more"); if (old) old.remove();
  const chunk = list.slice(shown, shown + PAGE);
  g.insertAdjacentHTML("beforeend", chunk.map(card).join(""));
  shown += chunk.length;
  if (!list.length) g.innerHTML = '<div class="empty">Nada encontrado com esses filtros.</div>';
  if (shown < list.length) {
    const b = document.createElement("button"); b.className = "more";
    b.textContent = `Mostrar mais (${list.length - shown} restantes)`; b.onclick = () => render(true); g.appendChild(b);
  }
}
function apply() {
  const q = norm($("q").value).split(/\s+/).filter(Boolean), sil = $("sil").value, grp = $("grp").value,
        brand = $("brand").value, stock = $("stock").checked, sort = $("sort").value;
  list = DATA.filter(r => (!sil || r.sil === sil) && (!grp || r.grp === grp) && (!brand || r.marca === brand) &&
                          (!stock || r.in_stock) && q.every(w => r._q.includes(w)));
  const P = r => r.preco ?? 1e9;
  if (sort === "asc") list.sort((a,b) => P(a) - P(b));
  else if (sort === "desc") list.sort((a,b) => (b.preco ?? -1) - (a.preco ?? -1));
  else if (sort === "brand") list.sort((a,b) => a.marca.localeCompare(b.marca) || P(a) - P(b));
  else list.sort((a,b) => silRank[a.sil] - silRank[b.sil] || grpRank[a.grp] - grpRank[b.grp] ||
                          (b.in_stock - a.in_stock) || a.marca.localeCompare(b.marca) || P(a) - P(b));
  $("count").textContent = `${list.length} de ${DATA.length} peças`;
  render(false);
}
["q","sil","grp","brand","sort","stock"].forEach(id => $(id).addEventListener("input", apply));
apply();
</script>
</body>
</html>
"""


def hires(url, w=640):
    """Pede à CDN da loja uma versão ~640 px da foto (Shopify e Nuvemshop aceitam tamanho na URL)."""
    if not url:
        return url
    if url.startswith("//"):
        url = "https:" + url
    if "cdn.shopify.com" in url or "/cdn/shop/" in url:
        url = re.sub(r"([?&])width=\d+", "", url).rstrip("?&")
        return url + ("&" if "?" in url else "?") + f"width={w}"
    if re.search(r"mitiendanube|nuvemshop|cloudfront\.net/stores", url):
        return re.sub(r"-\d+-\d+\.(webp|jpe?g|png)", rf"-{w}-0.\1", url)
    return url


def main():
    rows, out_count, _ = L.collect()
    data = [{k: r[k] for k in ("marca", "nome", "url", "sil", "grp", "cor", "tecido", "preco", "de", "disp",
                               "in_stock", "img")} for r in rows]
    for d in data:
        d["img"] = hires(d["img"])
    n_stock = sum(r["in_stock"] for r in rows)
    sub = (f"{len(rows)} peças ({n_stock} disponíveis) de {len({r['marca'] for r in rows})} marcas — "
           f"Brazil Made It + lojas extras. Fora: baggy, wide, cargo, jogger, moletom, feminina etc. "
           f"Cor e modelagem vêm do texto da loja; confira na foto.")
    html = TEMPLATE.replace("__SUB__", sub).replace(
        "__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    open(OUT, "w").write(html)
    print(OUT, len(data), "peças")


if __name__ == "__main__":
    main()
