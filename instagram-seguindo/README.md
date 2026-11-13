# IG Seguindo & Em Comum — extensão para Brave/Chrome

Roda **dentro da sua sessão do Instagram** (na própria aba do instagram.com), por isso
funciona com contas privadas **que você segue**. Nada sai do seu navegador: não há
servidor, e os dados ficam só no `chrome.storage` local da extensão.

## Funções
- **Lista**: puxa o "Seguindo" (ou "Seguidores") de um perfil, com filtro, exportação
  CSV/JSON e "copiar @".
- **Novos / deixaram de seguir**: cada busca fica guardada. Buscando a mesma conta de novo
  (com "ignorar cache"), a extensão mostra quem **entrou** e quem **saiu** desde a busca
  anterior, e pode ordenar com os novos no topo.
- **Monitorar** (para ver quando alguém segue uma pessoa nova): adicione até 10 contas. A cada
  ~6 h a extensão lê só o perfil (1 requisição) e compara o número de "seguindo". Se mudou,
  baixa a lista e registra **"@fulana seguiu @ciclano — entre 13/11 08:00 e 13/11 14:00"**.
  Também mostra o número de novos no ícone e uma notificação do sistema. A cada 3 dias a lista é baixada
  mesmo sem mudança no número (pega o caso "seguiu um e deixou de seguir outro").
  Precisa de **uma aba do Instagram aberta** (pode fixar a aba). Sem aba aberta, nada roda; na
  próxima vez que abrir, as verificações atrasadas são feitas.
- **Em comum**: compara duas contas e mostra quem **as duas seguem** (ou os seguidores
  em comum). O resultado segue a ordem da conta A.

## Instalar no Brave
1. Abra `brave://extensions` e ative **Modo do desenvolvedor** (canto superior direito).
2. **Carregar sem compactação** → escolha esta pasta `instagram-seguindo/`.
3. Fixe o ícone da extensão. Com uma aba do instagram.com aberta e logada, clique nele
   para abrir/fechar o painel. (Se você estiver em outra aba, ele abre o Instagram.)

## Velocidade e proteções da conta
Em **Ajustes → Velocidade** há três ritmos (o teto diário de requisições vale em todos):

| Ritmo | Espera entre páginas | Pausa longa | Lista de 500 (páginas de 100) | Lista de 500 (páginas de 12) |
|---|---|---|---|---|
| Cautelosa | 4–8 s | 45–90 s a cada 6 páginas | ~35 s | ~10 min |
| **Equilibrada (padrão)** | 1,5–4 s | 15–35 s a cada 10 páginas | **~15 s** | **~3–4 min** |
| Rápida | 0,8–2 s | 8–20 s a cada 15 páginas | ~8 s | ~1,5–2 min |

- **Freio automático:** se o Instagram pedir para esperar uma vez, a extensão usa o ritmo cauteloso
  por 24 h, em qualquer configuração.
- A extensão aprende quantas contas **desativadas/ocultas** cada perfil tem (contadas no total mas
  nunca mostradas) e para de baixar a lista duas vezes por causa delas. Só a 1ª busca de cada
  conta faz a 2ª passada.
- Teto diário: 300 requisições. Com páginas de 100 isso dá ~30.000 perfis por dia.
- Monitor: verificação a cada ~6 h (±15%). Listas de até 1.000 perfis são baixadas inteiras
  (≈ 6–10 requisições); maiores só quando o número de seguidos muda, ou a cada 3 dias.

**Risco:** só há leituras (GET), as mesmas que o site faz quando você abre e rola a lista. O
Instagram não publica limites; o que costuma gerar bloqueio é **volume alto e contínuo** (muitas
listas grandes por dia, todo dia), não uma lista lida em 15 s. O pior caso comum é um "tente
novamente mais tarde" temporário. A extensão reage freando, pausando 6 h e, em caso de
verificação, parando 24 h.
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
- **Ordem "mais recente primeiro" — só é garantida na SUA conta.** O Instagram não
  expõe a data de cada follow. Na sua própria lista "Seguindo", a extensão pede
  `order=date_followed_latest` (o mesmo "Data em que seguiu: mais recente" do app) e a
  ordem é cronológica de verdade. Para **outras contas**, o Instagram ignora esse pedido
  e devolve uma ordem **personalizada para quem está vendo** (muda entre pessoas e até
  entre buscas). Não existe hoje, pelo site ou app, um jeito de pedir a lista de terceiros
  em ordem cronológica. Por isso, para saber quando alguém segue uma conta nova, use a aba
  **Monitorar**: a extensão percebe o follow comparando as listas, com precisão igual ao
  intervalo entre verificações. Follows anteriores à primeira verificação não têm como ser datados. Fontes: [instagrapi #2857](https://github.com/subzeroid/instagrapi/issues/2857)
  (out/2026) e o menu "Data em que seguiu", que só aparece na sua própria lista.
- Os totais do perfil às vezes não batem com a lista (contas desativadas/restritas são
  omitidas). Para contas que não são suas, o Instagram pode limitar a lista de *seguidores*.
- A extensão usa endpoints internos do site; se o Instagram mudá-los, pode precisar de ajuste.

## Custo do monitor (para não estourar o limite diário)
Conta que segue ~1.000 perfis: cada verificação sem mudança custa 1 requisição; cada mudança
custa ~85 (a lista inteira). Com o teto de 300 por dia, dá para acompanhar várias contas
tranquilamente, desde que elas não sigam gente nova toda hora. Contas que seguem muitos milhares
de perfis consomem bem mais.

## Como a extensão evita erros (v1.4)
Baseado no que outras extensões abertas fazem hoje (insta-track, followlens) e em relatos de
2026 sobre a API interna do Instagram.

**Na coleta**
- Páginas de 100 perfis: uma lista de 500 sai em ~6 requisições, o que dá menos chance de a
  ordem mudar no meio e menos risco para a conta.
- Para a paginação ao ver cursor repetido ou 3 páginas vazias; descarta repetidos pelo id.
- Se faltar gente, faz até 3 passadas e junta. Se uma passada extra não acha ninguém novo, o que
  falta são contas desativadas/ocultas (a lista é considerada completa).
- **Lista abaixo de 90% e ainda instável é descartada**: nada é registrado, e a extensão tenta de novo
  em até 2 h.
- Limite (429): espera 1, 2 e 4 min, respeitando o `Retry-After`. Se continuar, para por 6 h.
- Verificação de segurança, bloqueio temporário (`feedback_required`) ou redirecionamento para
  login: para na hora (24 h nos dois primeiros) e avisa.

**No monitor**
- "Seguiu" só vale para quem **nunca** apareceu em busca anterior, e só é **confirmado** se bater
  com a variação do número de "seguindo". Senão aparece como *incerto* e não conta no ícone nem
  na notificação.
- "Deixou de seguir" é **confirmado pesquisando o @ dentro da lista da pessoa** (a mesma busca da
  caixa de pesquisa do Instagram). Se essa busca não funcionar, só confirma quando o contador cair
  exatamente o mesmo número ou quando o perfil sumir em 2 buscas completas.
- Fase de calibração: até ter visto ~98% da lista, ninguém vira "seguiu".
- Listas de até 1.000 perfis são baixadas inteiras a cada verificação (~10 requisições). Isso pega
  até "seguiu um e deixou de seguir outro" no mesmo período.

**Testes** (Instagram simulado, 23 cenários, todos passando): páginas de 100; recusa de página
grande; 429 com recuperação; 429 persistente com pausa de 6 h; verificação de segurança;
`feedback_required`; redirecionamento para login; lista 60% descartada; paginação instável
moderada sem falsos; perfis pulados sem falso unfollow; busca ignorada pelo Instagram; contador
igual (troca 1-por-1); cursor repetido; diagnóstico.

**O que não dá para garantir:** a API é interna e sem documentação. O Instagram muda sem aviso, e
o comportamento varia por conta. Por isso existe **Ajustes → Testar conexão**: ele gera um
relatório do que funciona na sua conta. Se aparecer ERRO, é ele que deve ser enviado para o ajuste.
