# IG Seguindo & Em Comum — extensão para Brave/Chrome

Roda **dentro da sua sessão do Instagram** (na própria aba do instagram.com), por isso
funciona com contas privadas **que você segue**. Nada sai do seu navegador: não há
servidor, e os dados ficam só no `chrome.storage` local da extensão.

## Funções
- **Lista**: puxa o "Seguindo" (ou "Seguidores") de um perfil, do follow **mais recente
  para o mais antigo** (#1 = quem a conta seguiu por último). Filtro, exportação CSV/JSON
  e "copiar @".
- **Em comum**: compara duas contas e mostra quem **as duas seguem** (ou os seguidores
  em comum). O resultado segue a ordem da conta A.

## Instalar no Brave
1. Abra `brave://extensions` e ative **Modo do desenvolvedor** (canto superior direito).
2. **Carregar sem compactação** → escolha esta pasta `instagram-seguindo/`.
3. Fixe o ícone da extensão. Com uma aba do instagram.com aberta e logada, clique nele
   para abrir/fechar o painel. (Se você estiver em outra aba, ele abre o Instagram.)

## Proteções da conta (padrões)
| Ajuste | Padrão |
|---|---|
| Espera entre páginas (12 perfis/página) | 3–7 s, aleatória |
| Pausa longa | 30–75 s a cada 8 páginas |
| Teto diário de requisições (somando tudo) | 300 (~3.500 perfis/dia) |
| Teto de perfis por lista | 5.000 |
| Cache de listas completas | 24 h (comparar de novo não refaz a busca) |

- Se o Instagram responder "aguarde" (429), a extensão pausa 10 min, depois 20 min,
  e então para — salvando o progresso. Buscar de novo **continua de onde parou**.
- Se aparecer checkpoint/verificação ou sessão expirada, para na hora.
- Só faz leitura (GET) — nunca segue, curte ou envia nada.
- Ritmo aproximado: ~1.000 perfis em 8–10 minutos. Deixe a aba aberta enquanto roda.

Dá para mudar os valores na aba **Ajustes**, mas diminuir as esperas aumenta o risco.

## Avisos
- Automatizar coleta vai contra os Termos do Instagram. Os limites acima reduzem o
  risco, mas não o zeram — o pior caso comum é um bloqueio temporário de ações. Use com
  moderação (ex.: evite várias contas grandes no mesmo dia).
- O Instagram não informa a **data** de cada follow, só a ordem. A ordem "mais recente
  primeiro" é a que o próprio Instagram entrega; a extensão pede explicitamente
  `date_followed_latest` e, se não aceito, usa a ordem padrão (que também é por recência).
- Os totais do perfil às vezes não batem com a lista (contas desativadas/restritas são
  omitidas). Para contas que não são suas, o Instagram pode limitar a lista de *seguidores*.
- A extensão usa endpoints internos do site; se o Instagram mudá-los, pode precisar de ajuste.
