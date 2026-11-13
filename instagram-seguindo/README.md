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

## Proteções da conta (padrões)
| Ajuste | Padrão |
|---|---|
| Espera entre páginas (12 perfis/página) | 3–7 s, aleatória |
| Pausa longa | 30–75 s a cada 8 páginas |
| Teto diário de requisições (somando tudo) | 300 (~3.500 perfis/dia) |
| Teto de perfis por lista | 5.000 |
| Cache de listas completas | 24 h (comparar de novo não refaz a busca) |
| Monitor: verificação do perfil | a cada 6 h (±15%), 1 requisição por conta |
| Monitor: lista completa | só quando o número muda, ou a cada 3 dias |

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

## Confiabilidade com listas grandes (500+)
Em listas de terceiros o Instagram usa uma ordem personalizada que pode mudar durante a
paginação, fazendo a busca repetir uns perfis e pular outros. A extensão se protege assim:
- descarta repetidos e, se vierem menos de 98% do total, faz até 3 passadas e junta tudo;
- **calibração**: enquanto as buscas somadas não cobrirem 98% da lista, perfis que aparecem
  pela primeira vez entram na referência em silêncio (não viram "seguiu"). A conta mostra
  "calibrando NN%". Follows feitos durante a calibração não são registrados;
- "seguiu" só vale para quem **nunca** apareceu em nenhuma busca anterior; se a quantidade de
  "seguiu" não bater com a variação do contador, os eventos ficam marcados como **incerto**;
- "deixou de seguir" só é confirmado se o perfil sumir em 2 buscas seguidas.

Teste simulado com 540 seguindo (11 ocultas): com ordem estável, 12/12 follows e 3/3
unfollows certos, zero falsos. No pior caso (ordem reembaralhada a cada página): 2 ciclos
de calibração, depois quase todos os follows detectados (alguns um ciclo atrasado) e 1 falso,
marcado como incerto. Nesse pior caso cada mudança custa ~140 requisições para 540 perfis.
