# Garimpo de calças bootcut — marcas brasileiras

1. `python brands.py` — lê o diretório brazilmadeit.com.br (API Supabase pública do site, somente leitura) e soma as lojas extras → `cache/brands.json`
2. `python scraper.py [--only dom1,dom2] [--workers 8] [--force]` — varre cada loja (Shopify → Nuvemshop → WooCommerce → VTEX → genérico) e salva em `cache/stores/`. Retoma de onde parou.
3. `python analyze.py` — filtra bootcut/flare, extrai cor/tecido/medidas e gera `resultado.xlsx`.

Regras de coleta: respeita robots.txt (por isso a busca `/search/` da Nuvemshop não é usada; os produtos vêm do sitemap e das páginas de categoria), pausa de 1–2 s por loja, timeout de 15 s, nada de carrinho ou login.
