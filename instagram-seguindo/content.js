// IG Seguindo & Em Comum — roda dentro da aba do instagram.com, usando a sua sessão.
// Todas as requisições saem da própria página (mesma origem, seus cookies), em ritmo lento.
(() => {
  if (window.__igSeguindoLoaded) return;
  window.__igSeguindoLoaded = true;

  const APP_ID = '936619743392459'; // App ID público do Instagram Web
  const DEFAULTS = {
    minDelay: 3,          // s entre páginas (mínimo)
    maxDelay: 7,          // s entre páginas (máximo)
    pageSize: 12,         // perfis por página (mesmo valor que o site usa)
    burstPages: 8,        // a cada N páginas faz uma pausa longa
    burstPauseMin: 30,    // s
    burstPauseMax: 75,    // s
    dailyRequestCap: 300, // teto de requisições por dia (todas as buscas somadas)
    maxUsers: 5000,       // teto de perfis por lista
    cacheHours: 24,       // reaproveita listas completas por este tempo
    monitorHours: 6,      // monitor: a cada quantas horas confere cada conta (1 requisição)
    fullRecheckDays: 3,   // monitor: rebaixa a lista mesmo sem mudança no contador (pega troca 1-por-1)
    maxWatched: 10,       // monitor: máximo de contas monitoradas
  };
  let settings = { ...DEFAULTS };
  let job = null; // { cancelled: boolean }

  // ---------- utilidades ----------
  const store = {
    get: async (k) => (await chrome.storage.local.get(k))[k],
    set: (k, v) => chrome.storage.local.set({ [k]: v }),
  };
  const rand = (a, b) => a + Math.random() * (b - a);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const cookie = (name) => document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))?.[1] || '';
  const myId = () => cookie('ds_user_id');
  const today = () => new Date().toLocaleDateString('sv-SE');
  const cleanUser = (s) => String(s || '').trim().replace(/^@/, '').replace(/^https?:\/\/(www\.)?instagram\.com\//i, '').replace(/[/?#].*$/, '').toLowerCase();

  class IgError extends Error {
    constructor(msg, kind, status) { super(msg); this.kind = kind; this.status = status; }
  }

  // Um único timer por espera (abas em segundo plano limitam timers encadeados); "Parar" acorda na hora.
  function sleep(ms, label) {
    return new Promise((resolve, reject) => {
      const end = Date.now() + ms;
      const j = job;
      let iv = null;
      const done = (err) => {
        clearTimeout(t); clearInterval(iv);
        if (j) j.wake = null;
        err ? reject(err) : resolve();
      };
      const t = setTimeout(() => done(), ms);
      if (j) j.wake = () => done(new IgError('Interrompido.', 'cancel'));
      if (j?.cancelled) return done(new IgError('Interrompido.', 'cancel'));
      if (label && sh) {
        const tick = () => setStatus(`${label} — ${Math.max(0, Math.ceil((end - Date.now()) / 1000))}s`);
        tick();
        iv = setInterval(tick, 1000);
      }
    });
  }

  async function countRequest() {
    let u = (await store.get('usage')) || {};
    if (u.date !== today()) u = { date: today(), requests: 0 };
    if (u.requests >= settings.dailyRequestCap) {
      throw new IgError(`Limite diário de ${settings.dailyRequestCap} requisições atingido (proteção da conta). O progresso foi salvo; continue amanhã ou ajuste em "Ajustes".`, 'cap');
    }
    u.requests++;
    await store.set('usage', u);
    refreshUsage(u);
  }

  // ---------- API do Instagram ----------
  async function igGet(path) {
    if (job?.cancelled) throw new IgError('Interrompido.', 'cancel');
    if (!myId()) throw new IgError('Você não está logado no Instagram nesta aba.', 'auth');
    await countRequest();
    let res, text;
    try {
      res = await fetch(location.origin + path, {
        credentials: 'include',
        headers: {
          'X-IG-App-ID': APP_ID,
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': cookie('csrftoken'),
          Accept: 'application/json',
        },
      });
      text = await res.text();
    } catch (e) {
      throw new IgError('Falha de rede: ' + e.message, 'net');
    }
    let data = null;
    try { data = JSON.parse(text); } catch { /* resposta não-JSON */ }
    const msg = data?.message || '';
    // Ordem importa: sem sessão o Instagram responde 401 + require_login + "Please wait a few minutes".
    if (data?.checkpoint_url || /checkpoint|challenge/i.test(msg)) {
      throw new IgError('O Instagram pediu uma verificação de segurança. Abra o app/site, resolva e espere algumas horas antes de usar de novo.', 'checkpoint', res.status);
    }
    if (res.status === 401 || data?.require_login || /login_required/i.test(msg)) {
      throw new IgError('Sessão inválida ou expirada — recarregue o Instagram e faça login de novo.', 'auth', res.status);
    }
    if (res.status === 429 || /wait a few minutes|try again later|aguarde|tente novamente/i.test(msg)) {
      throw new IgError('Instagram pediu para esperar (limite de requisições).', 'rate', res.status);
    }
    if (res.status === 404) throw new IgError('Perfil não encontrado.', 'notfound', 404);
    if (!res.ok || !data || data.status === 'fail') {
      throw new IgError(`Erro ${res.status}: ${msg || (text || '').slice(0, 120)}`, 'http', res.status);
    }
    return data;
  }

  async function getProfile(username, force = false) {
    const key = 'profile:' + username;
    const c = await store.get(key);
    if (c && !force && Date.now() - c.at < settings.cacheHours * 3600e3) return c;
    let u = null;
    try {
      const d = await igGet(`/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`);
      u = d?.data?.user;
    } catch (e) {
      if (e.kind !== 'notfound' && e.kind !== 'http') throw e;
    }
    if (!u) {
      // Plano B: busca do site, que também traz o id numérico.
      const d = await igGet(`/web/search/topsearch/?context=blended&query=${encodeURIComponent(username)}&include_reel=false`);
      const hit = (d.users || []).map((x) => x.user).find((x) => x?.username?.toLowerCase() === username);
      if (!hit) throw new IgError(`Perfil @${username} não encontrado.`, 'notfound');
      u = { id: hit.pk || hit.pk_id, username: hit.username, full_name: hit.full_name, is_private: hit.is_private,
            followed_by_viewer: hit.friendship_status?.following ?? !hit.is_private };
    }
    const p = {
      at: Date.now(),
      id: String(u.id),
      username: u.username,
      fullName: u.full_name || '',
      isPrivate: !!u.is_private,
      followedByViewer: !!u.followed_by_viewer,
      followingCount: u.edge_follow?.count ?? null,
      followersCount: u.edge_followed_by?.count ?? null,
    };
    await store.set(key, p);
    return p;
  }

  const TYPE_LABEL = { following: 'seguindo', followers: 'seguidores' };

  /**
   * Busca a lista completa (seguindo ou seguidores) de um perfil, na ordem em que o
   * Instagram entrega — para "seguindo", do follow mais recente ao mais antigo.
   * Salva o progresso a cada página: se parar no meio, a próxima busca continua de onde parou.
   */
  async function fetchList(username, type, { force = false, onProgress, profile: given } = {}) {
    const key = `list:${type}:${username}`;
    const cached = await store.get(key);
    const fresh = cached?.complete && Date.now() - cached.fetchedAt < settings.cacheHours * 3600e3;
    if (fresh && !force) {
      const h = await store.get('hist:' + key.slice(5));
      if (h) for (const u of cached.users) u.firstSeen = h.firstSeen[u.pk];
      onProgress?.(cached, true);
      return cached;
    }

    const profile = given || (await getProfile(username, force));
    const isSelf = profile.id === myId();
    if (profile.isPrivate && !profile.followedByViewer && !isSelf) {
      throw new IgError(`@${username} é privada e você não a segue — não dá para ver a lista.`, 'private');
    }
    const total = type === 'following' ? profile.followingCount : profile.followersCount;

    const resume = cached && !cached.complete && !force && cached.id === profile.id && cached.nextMaxId;
    const state = resume ? cached : {
      id: profile.id, username: profile.username, fullName: profile.fullName, type,
      total, users: [], nextMaxId: null, complete: false, truncated: false, startedAt: Date.now(), isSelf,
    };
    state.total = total;
    if (resume) setStatus(`Continuando @${username} a partir de ${state.users.length} perfis já salvos…`);

    const seen = new Set(state.users.map((u) => u.pk));
    let useOrder = type === 'following';
    let pages = 0, rateStrikes = 0;

    while (true) {
      if (state.users.length >= settings.maxUsers) { state.truncated = true; break; }
      const q = new URLSearchParams({ count: String(settings.pageSize) });
      if (state.nextMaxId) q.set('max_id', state.nextMaxId);
      if (type === 'followers') q.set('search_surface', 'follow_list_page');
      if (useOrder) q.set('order', 'date_followed_latest');

      let d;
      try {
        d = await igGet(`/api/v1/friendships/${profile.id}/${type}/?${q}`);
        rateStrikes = 0;
      } catch (e) {
        if (e.kind === 'http' && e.status === 400 && useOrder) { useOrder = false; continue; } // parâmetro não aceito: usa a ordem padrão
        if (e.kind === 'rate' && rateStrikes < 2) {
          rateStrikes++;
          await store.set(key, state);
          await sleep(rateStrikes * 10 * 60e3, `Instagram pediu calma. Pausa de ${rateStrikes * 10} min (progresso salvo)`);
          continue;
        }
        await store.set(key, state);
        throw e;
      }

      for (const u of d.users || []) {
        const pk = String(u.pk ?? u.pk_id ?? u.id);
        if (seen.has(pk)) continue;
        seen.add(pk);
        state.users.push({
          pk, username: u.username, fullName: u.full_name || '',
          isPrivate: !!u.is_private, isVerified: !!u.is_verified, pic: u.profile_pic_url || '',
        });
      }
      state.nextMaxId = d.next_max_id || null;
      pages++;
      await store.set(key, state);
      onProgress?.(state, false);

      if (!state.nextMaxId || !(d.users || []).length) { state.complete = true; break; }
      if (pages % settings.burstPages === 0) {
        await sleep(rand(settings.burstPauseMin, settings.burstPauseMax) * 1000, `Pausa longa de segurança (${state.users.length} perfis)`);
      } else {
        await sleep(rand(settings.minDelay, settings.maxDelay) * 1000, `${state.users.length}${total ? '/' + total : ''} perfis — próxima página em`);
      }
    }
    state.complete = true;
    state.fetchedAt = Date.now();
    // Cronológica de verdade só quando é a SUA lista "seguindo" e o Instagram aceitou o parâmetro de ordem.
    state.chronological = isSelf && type === 'following' && useOrder;
    state.diff = await recordSnapshot(key, state);
    await store.set(key, state);
    return state;
  }

  /**
   * Histórico por conta: guarda quando a extensão viu cada perfil pela primeira vez.
   * Para contas de terceiros é a ÚNICA forma confiável de saber quem foi seguido recentemente,
   * porque o Instagram entrega essas listas em ordem personalizada (não cronológica).
   */
  async function recordSnapshot(key, state) {
    const hk = 'hist:' + key.slice(5);
    const h = (await store.get(hk)) || { firstSeen: {}, snapshots: [], lastPks: null };
    const now = state.fetchedAt;
    const baseline = !h.lastPks;
    const prev = new Set(h.lastPks || []);
    const curr = new Set(state.users.map((u) => u.pk));
    const coverage = state.total ? state.users.length / state.total : 1;
    const added = [], removed = [];
    for (const u of state.users) {
      if (!(u.pk in h.firstSeen)) h.firstSeen[u.pk] = baseline ? 0 : now; // 0 = já estava na 1ª busca
      if (!baseline && !prev.has(u.pk)) added.push(u.pk);
    }
    if (!baseline) for (const pk of prev) if (!curr.has(pk)) removed.push(pk);
    const prevSnap = h.snapshots[h.snapshots.length - 1] || null;
    h.removedInfo = h.removedInfo || {};
    for (const pk of removed) if (h.lastUsers?.[pk]) h.removedInfo[pk] = { ...h.lastUsers[pk], removedAt: now };
    h.lastUsers = Object.fromEntries(state.users.map((u) => [u.pk, { username: u.username, fullName: u.fullName }]));
    h.lastPks = [...curr];
    h.snapshots.push({ at: now, count: curr.size, total: state.total, coverage });
    h.snapshots = h.snapshots.slice(-50);
    await store.set(hk, h);
    for (const u of state.users) u.firstSeen = h.firstSeen[u.pk];
    return {
      baseline, since: prevSnap?.at || null, added, removed,
      removedUsers: removed.map((pk) => ({ pk, ...(h.removedInfo[pk] || { username: '?' }) })),
      reliable: coverage >= 0.97 && (!prevSnap || prevSnap.coverage >= 0.97),
      coverage,
    };
  }

  // ---------- monitor: detectar quando a pessoa segue alguém ----------
  // Estratégia barata: a cada `monitorHours` lê só o perfil (1 requisição) e compara o número
  // de "seguindo". Se mudou (ou passou `fullRecheckDays`), baixa a lista e compara com a anterior.
  // Quem aparece de novo foi seguido entre a verificação anterior e esta.
  const getWatch = async () => (await store.get('watch')) || {};

  async function notifyBackground() {
    const w = await getWatch();
    const unseen = Object.values(w).reduce((n, x) => n + (x.unseen || 0), 0);
    chrome.runtime.sendMessage({ type: 'badge', count: unseen }).catch?.(() => {});
    return unseen;
  }

  async function checkAccount(username, { forceFull = false } = {}) {
    const w = await getWatch();
    const x = w[username];
    if (!x) return [];
    const now = Date.now();
    const p = await getProfile(username, true);
    if (p.isPrivate && !p.followedByViewer && p.id !== myId()) {
      throw new IgError(`@${username} é privada e você não a segue.`, 'private');
    }
    const changed = x.lastCount != null && p.followingCount !== x.lastCount;
    const stale = !x.lastFull || now - x.lastFull > settings.fullRecheckDays * 86400e3;
    const events = [];
    if (forceFull || changed || stale) {
      setStatus(`Monitor: @${username} ${changed ? `mudou de ${x.lastCount} para ${p.followingCount} seguindo — ` : ''}baixando a lista…`);
      const st = await fetchList(username, 'following', { force: true, profile: p });
      const d = st.diff;
      if (!d.baseline) {
        // Janela: da última vez em que o contador ainda estava igual até agora.
        const from = Math.max(d.since || 0, changed ? x.lastCheck || 0 : 0) || d.since;
        const byPk = Object.fromEntries(st.users.map((u) => [u.pk, u]));
        for (const pk of d.added) {
          const u = byPk[pk];
          events.push({ kind: 'follow', who: username, pk, username: u.username, fullName: u.fullName, pic: u.pic, from, to: now, unsure: !d.reliable });
        }
        for (const u of d.removedUsers) {
          events.push({ kind: 'unfollow', who: username, pk: u.pk, username: u.username, fullName: u.fullName || '', pic: '', from, to: now, unsure: !d.reliable });
        }
      }
      x.lastFull = now;
    }
    const w2 = await getWatch(); // pode ter mudado durante a busca
    if (!w2[username]) return events;
    Object.assign(w2[username], { lastCheck: now, lastFull: x.lastFull, lastCount: p.followingCount, id: p.id });
    w2[username].events = [...events, ...(w2[username].events || [])].slice(0, 500);
    w2[username].unseen = (w2[username].unseen || 0) + events.filter((e) => e.kind === 'follow').length;
    await store.set('watch', w2);
    return events;
  }

  async function acquireLock() {
    const l = await store.get('monitorLock');
    if (l && Date.now() - l.at < 30 * 60e3 && l.owner !== tabToken) return false;
    await store.set('monitorLock', { at: Date.now(), owner: tabToken });
    return true;
  }
  const tabToken = Math.random().toString(36).slice(2);
  const releaseLock = async () => { const l = await store.get('monitorLock'); if (l?.owner === tabToken) await chrome.storage.local.remove('monitorLock'); };

  /** Roda as contas monitoradas que estão vencidas. `only` = forçar uma conta (botão "verificar agora"). */
  async function monitorTick(only = null) {
    if (job || !myId()) return;
    const w = await getWatch();
    const now = Date.now();
    const due = only ? [only] : Object.keys(w).filter((u) => !w[u].lastCheck || now - w[u].lastCheck >= settings.monitorHours * 3600e3 * (w[u].jitter || 1));
    if (!due.length || !(await acquireLock())) return;
    job = { cancelled: false };
    setBusy(true);
    const found = [];
    try {
      for (const [i, u] of due.entries()) {
        if (i) await sleep(rand(settings.minDelay, settings.maxDelay) * 1000, 'Monitor: próxima conta em');
        try {
          found.push(...(await checkAccount(u, { forceFull: !w[u].lastFull })));
          const wj = await getWatch();
          if (wj[u]) { wj[u].jitter = rand(0.85, 1.15); wj[u].lastError = null; await store.set('watch', wj); }
        } catch (e) {
          if (['cancel', 'rate', 'auth', 'checkpoint', 'cap'].includes(e.kind)) throw e;
          const wj = await getWatch();
          if (wj[u]) { wj[u].lastError = e.message; wj[u].lastCheck = Date.now(); await store.set('watch', wj); }
        }
      }
      const fol = found.filter((e) => e.kind === 'follow');
      setStatus(`Monitor: ${due.length} conta(s) verificada(s). ${fol.length ? fol.length + ' novo(s) follow(s)!' : 'Nada novo.'}`);
      if (fol.length) {
        chrome.runtime.sendMessage({
          type: 'notify',
          title: `${fol.length} novo(s) follow(s)`,
          message: fol.slice(0, 4).map((e) => `@${e.who} seguiu @${e.username}`).join('\n') + (fol.length > 4 ? `\n+${fol.length - 4}` : ''),
        }).catch?.(() => {});
      }
    } catch (e) {
      setStatus(e.kind === 'cancel' ? 'Monitor interrompido.' : 'Monitor: ' + e.message, e.kind !== 'cancel');
    } finally {
      job = null;
      setBusy(false);
      await releaseLock();
      await notifyBackground();
      renderMonitor();
    }
  }

  // ---------- exportação ----------
  function download(name, content, mime) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type: mime }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  const csvCell = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  function exportCSV(name, users) {
    const rows = [['posicao', 'username', 'nome', 'privada', 'verificada', 'link']]
      .concat(users.map((u, i) => [i + 1, u.username, u.fullName, u.isPrivate ? 'sim' : 'nao', u.isVerified ? 'sim' : 'nao', `https://www.instagram.com/${u.username}/`]));
    download(name + '.csv', '﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\n'), 'text/csv;charset=utf-8');
  }
  function exportJSON(name, users) {
    download(name + '.json', JSON.stringify(users.map((u, i) => ({ posicao: i + 1, ...u })), null, 2), 'application/json');
  }

  // ---------- painel (Shadow DOM, não interfere no site) ----------
  let host, sh, current = { list: [], name: 'lista' };

  const CSS = `
    :host { all: initial; }
    .panel { position: fixed; top: 16px; right: 16px; z-index: 2147483647; width: 420px; max-height: calc(100vh - 32px);
      display: flex; flex-direction: column; background: #fff; color: #111; border-radius: 12px;
      box-shadow: 0 10px 40px rgba(0,0,0,.25); font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    header { display: flex; align-items: center; padding: 10px 12px; border-bottom: 1px solid #eee; gap: 8px; }
    header b { flex: 1; font-size: 14px; }
    .x { border: 0; background: none; font-size: 18px; cursor: pointer; color: #666; }
    nav { display: flex; border-bottom: 1px solid #eee; }
    nav button { flex: 1; padding: 8px; border: 0; background: none; cursor: pointer; font: inherit; color: #666; border-bottom: 2px solid transparent; }
    nav button.on { color: #111; border-bottom-color: #0095f6; font-weight: 600; }
    .tab { display: none; padding: 10px 12px; gap: 8px; flex-direction: column; overflow: auto; }
    .tab.on { display: flex; }
    .row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    input[type=text], input[type=number], select { font: inherit; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; min-width: 0; }
    input[type=text] { flex: 1; }
    input[type=number] { width: 70px; }
    button.b { font: inherit; padding: 6px 12px; border-radius: 6px; border: 0; background: #0095f6; color: #fff; cursor: pointer; font-weight: 600; }
    button.b.sec { background: #efefef; color: #111; }
    button.b:disabled { opacity: .5; cursor: default; }
    .status { min-height: 18px; color: #444; font-size: 12px; white-space: pre-wrap; }
    .status.err { color: #c00; }
    .bar { height: 4px; background: #eee; border-radius: 2px; overflow: hidden; }
    .bar i { display: block; height: 100%; width: 0; background: #0095f6; transition: width .3s; }
    .results { border-top: 1px solid #eee; display: flex; flex-direction: column; min-height: 0; flex: 1; }
    .results .head { padding: 8px 12px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .results .head span { flex: 1; font-weight: 600; }
    .list { overflow: auto; max-height: 45vh; padding: 0 12px 10px; }
    .u { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f3f3f3; }
    .u .n { width: 38px; color: #999; font-size: 11px; text-align: right; }
    .u img { width: 28px; height: 28px; border-radius: 50%; background: #eee; }
    .u a { color: #111; text-decoration: none; font-weight: 600; }
    .u small { color: #888; display: block; font-weight: 400; }
    .muted { color: #888; font-size: 11px; }
    .w { display: flex; align-items: center; gap: 6px; padding: 5px 0; border-bottom: 1px solid #f3f3f3; }
    .w div { flex: 1; } .w small { color: #888; display: block; } .w .er { color: #c00; }
    .w button { font: inherit; font-size: 11px; border: 0; background: #efefef; border-radius: 5px; padding: 3px 7px; cursor: pointer; }
    .ev { padding: 5px 0; border-bottom: 1px solid #f3f3f3; } .ev small { color: #888; display: block; }
    .ev a { color: #111; font-weight: 600; text-decoration: none; } .ev.un { opacity: .6; }
    .new { background: #e7f3ff; color: #0064c8; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 4px; }
    label { display: flex; align-items: center; gap: 4px; }
    .grid { display: grid; grid-template-columns: 1fr auto; gap: 6px 10px; align-items: center; }
  `;

  const HTML = `
    <div class="panel">
      <header><b>IG Seguindo &amp; Em Comum</b><button class="x" id="close" title="Fechar">×</button></header>
      <nav>
        <button data-tab="t1" class="on">Lista</button>
        <button data-tab="t2">Em comum</button>
        <button data-tab="t4">Monitorar <span id="unseen" class="new" style="display:none"></span></button>
        <button data-tab="t3">Ajustes</button>
      </nav>

      <div class="tab on" id="t1">
        <div class="row"><input type="text" id="u1" placeholder="@usuario ou link do perfil">
          <select id="type1"><option value="following">Seguindo</option><option value="followers">Seguidores</option></select></div>
        <div class="row">
          <label><input type="checkbox" id="force1"> ignorar cache</label>
          <span style="flex:1"></span>
          <button class="b" id="go1">Buscar</button>
        </div>
        <div class="row"><span>Mostrar:</span><select id="view1" style="flex:1">
          <option value="ig">Ordem do Instagram</option>
          <option value="new">Novos primeiro (detectados entre buscas)</option>
          <option value="added">Só os novos desde a busca anterior</option>
          <option value="removed">Deixaram de seguir desde a busca anterior</option>
        </select></div>
        <div class="muted" id="orderNote">Na <b>sua</b> conta, "Seguindo" vem em ordem cronológica real (mais recente primeiro).
          Em contas de <b>outras pessoas</b> o Instagram entrega uma ordem personalizada, <b>não</b> cronológica —
          para saber quem ela seguiu recentemente, busque de novo depois de alguns dias: a extensão marca os novos.</div>
      </div>

      <div class="tab" id="t2">
        <div class="row"><input type="text" id="ua" placeholder="@conta A"></div>
        <div class="row"><input type="text" id="ub" placeholder="@conta B"></div>
        <div class="row">
          <select id="type2"><option value="following">Quem as duas seguem</option><option value="followers">Seguidores em comum</option></select>
          <label><input type="checkbox" id="force2"> ignorar cache</label>
          <span style="flex:1"></span>
          <button class="b" id="go2">Comparar</button>
        </div>
        <div class="muted">A ordem do resultado segue a lista da conta A (mais recente primeiro).</div>
      </div>

      <div class="tab" id="t4">
        <div class="row"><input type="text" id="uw" placeholder="@conta para monitorar"><button class="b" id="addw">Monitorar</button></div>
        <div class="muted">Mantenha uma aba do Instagram aberta (pode fixá-la). A cada <span id="mh"></span> h a extensão confere
          o número de "seguindo" de cada conta (1 requisição); se mudar, baixa a lista e mostra quem entrou, com o intervalo em que aconteceu.</div>
        <div id="wlist"></div>
        <div class="row"><b style="flex:1">Atividade</b><select id="wfilter"><option value="follow">Só follows</option><option value="all">Follows e unfollows</option></select></div>
        <div id="feed"></div>
      </div>

      <div class="tab" id="t3">
        <div class="grid">
          <span>Espera entre páginas (s), mín / máx</span><span><input type="number" id="s_minDelay" min="1" step="0.5"> <input type="number" id="s_maxDelay" min="1" step="0.5"></span>
          <span>Pausa longa a cada N páginas</span><span><input type="number" id="s_burstPages" min="1"></span>
          <span>Duração da pausa longa (s), mín / máx</span><span><input type="number" id="s_burstPauseMin" min="5"> <input type="number" id="s_burstPauseMax" min="5"></span>
          <span>Máx. requisições por dia</span><span><input type="number" id="s_dailyRequestCap" min="10"></span>
          <span>Máx. perfis por lista</span><span><input type="number" id="s_maxUsers" min="12"></span>
          <span>Validade do cache (horas)</span><span><input type="number" id="s_cacheHours" min="0"></span>
          <span>Monitor: verificar a cada (horas)</span><span><input type="number" id="s_monitorHours" min="1" step="0.5"></span>
          <span>Monitor: rebaixar lista a cada (dias)</span><span><input type="number" id="s_fullRecheckDays" min="1"></span>
          <span>Monitor: máx. de contas</span><span><input type="number" id="s_maxWatched" min="1"></span>
        </div>
        <div class="muted" id="usage"></div>
        <div class="row"><button class="b" id="save">Salvar</button><button class="b sec" id="reset">Padrões</button><span style="flex:1"></span><button class="b sec" id="clear">Limpar cache</button></div>
        <div class="muted">Os padrões são conservadores de propósito. Diminuir as esperas aumenta o risco de bloqueio temporário.</div>
      </div>

      <div style="padding: 0 12px 8px; display:flex; flex-direction:column; gap:6px">
        <div class="bar"><i id="bar"></i></div>
        <div class="row"><div class="status" id="status" style="flex:1"></div><button class="b sec" id="stop" disabled>Parar</button></div>
      </div>

      <div class="results">
        <div class="head"><span id="rtitle">Nenhum resultado ainda</span>
          <input type="text" id="filter" placeholder="filtrar" style="flex:0 0 110px">
          <button class="b sec" id="csv">CSV</button><button class="b sec" id="json">JSON</button><button class="b sec" id="copy">Copiar @</button>
        </div>
        <div class="list" id="list"></div>
      </div>
    </div>`;

  const $ = (id) => sh.getElementById(id);

  function setStatus(text, isErr = false) {
    if (!sh) return;
    const s = $('status');
    s.textContent = text;
    s.classList.toggle('err', isErr);
  }
  function setBar(done, total) {
    if (!sh) return;
    $('bar').style.width = total ? Math.min(100, (100 * done) / total) + '%' : done ? '100%' : '0';
  }
  function refreshUsage(u) {
    if (!sh) return;
    $('usage').textContent = `Hoje: ${u?.date === today() ? u.requests : 0} de ${settings.dailyRequestCap} requisições usadas.`;
  }

  let lastState = null;
  const fmtDate = (t) => new Date(t).toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' });

  function applyView() {
    const st = lastState;
    if (!st) return;
    const v = $('view1').value;
    const base = `@${st.username} — ${TYPE_LABEL[st.type]}`;
    const name = `${st.username}_${TYPE_LABEL[st.type]}`;
    const orderTxt = st.chronological ? 'cronológica (mais recente primeiro)' : 'personalizada do Instagram (não cronológica)';
    const d = st.diff;
    if (v === 'ig') return showResult(`${base}: ${st.users.length}${st.total ? ' de ' + st.total : ''} · ordem ${orderTxt}`, st.users, name);
    if (v === 'new') {
      const list = st.users.map((u, i) => [u, i]).sort((a, b) => (b[0].firstSeen || 0) - (a[0].firstSeen || 0) || a[1] - b[1]).map((x) => x[0]);
      return showResult(`${base}: novos detectados no topo`, list, name + '_novos_primeiro');
    }
    if (!d || d.baseline) return showResult('Primeira busca desta conta — ainda não há com o que comparar.', [], name);
    if (v === 'added') {
      const set = new Set(d.added);
      return showResult(`${d.added.length} novos desde ${fmtDate(d.since)}`, st.users.filter((u) => set.has(u.pk)), name + '_novos');
    }
    showResult(`${d.removed.length} saíram da lista desde ${fmtDate(d.since)}`, d.removedUsers.map((u) => ({ pic: '', isPrivate: false, isVerified: false, fullName: '', ...u })), name + '_removidos');
  }

  function renderList() {
    const f = $('filter').value.trim().toLowerCase();
    const rows = [];
    current.list.forEach((u, i) => {
      if (f && !u.username.toLowerCase().includes(f) && !u.fullName.toLowerCase().includes(f)) return;
      if (rows.length >= 3000) return; // evita travar a página; exporte para ver tudo
      rows.push(`<div class="u"><span class="n">#${i + 1}</span>
        <img loading="lazy" referrerpolicy="no-referrer" src="${esc(u.pic)}" alt="">
        <div><a href="https://www.instagram.com/${esc(u.username)}/" target="_blank">@${esc(u.username)}${u.isVerified ? ' ✔' : ''}${u.isPrivate ? ' 🔒' : ''}</a>
        ${u.firstSeen ? `<span class="new">novo · ${fmtDate(u.firstSeen)}</span>` : ''}
        <small>${esc(u.fullName)}</small></div></div>`);
    });
    $('list').innerHTML = rows.join('') || '<div class="muted" style="padding:8px 0">Nada para mostrar.</div>';
  }
  function showResult(title, list, name) {
    current = { list, name };
    $('rtitle').textContent = title;
    renderList();
  }

  function setBusy(b) {
    if (!sh) return;
    $('addw').disabled = b;
    $('go1').disabled = b; $('go2').disabled = b; $('stop').disabled = !b;
  }

  async function runJob(fn) {
    if (job) return;
    job = { cancelled: false };
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      if (e.kind === 'cancel') setStatus('Interrompido. O progresso foi salvo — buscar de novo continua de onde parou.');
      else setStatus(e.message || String(e), true);
    } finally {
      job = null;
      setBusy(false);
    }
  }

  const progressFor = (label) => (state, fromCache) => {
    setBar(state.users.length, state.total);
    if (state.complete) { lastState = state; return applyView(); }
    showResult(`${label}: ${state.users.length}${state.total ? ' de ' + state.total : ''}`, state.users, `${state.username}_${TYPE_LABEL[state.type]}`);
    if (fromCache) setStatus(`Do cache (${new Date(state.fetchedAt).toLocaleString()}). Marque "ignorar cache" para atualizar.`);
  };

  async function doList() {
    const u = cleanUser($('u1').value);
    const type = $('type1').value;
    if (!u) return setStatus('Digite um @usuario.', true);
    await runJob(async () => {
      setStatus(`Buscando ${TYPE_LABEL[type]} de @${u}…`);
      const st = await fetchList(u, type, { force: $('force1').checked, onProgress: progressFor(`@${u} — ${TYPE_LABEL[type]}`) });
      lastState = st;
      applyView();
      const d = st.diff;
      let msg = `Pronto: ${st.users.length} perfis${st.truncated ? ` (parou no limite de ${settings.maxUsers})` : ''}.`;
      if (st.total && st.users.length < st.total * 0.97 && !st.truncated) msg += ` Vieram ${Math.round((100 * st.users.length) / st.total)}% do total do perfil — o Instagram omite contas desativadas/restritas e às vezes corta listas de terceiros.`;
      if (d?.baseline) msg += ' Primeira busca desta conta: guardei como referência. Na próxima, mostro quem entrou e quem saiu.';
      else if (d) msg += ` Desde ${fmtDate(d.since)}: +${d.added.length} novos, −${d.removed.length} saíram.` + (d.reliable ? '' : ' (Atenção: uma das buscas veio incompleta, então pode haver falsos novos/removidos.)');
      setStatus(msg);
    });
  }

  async function doCompare() {
    const a = cleanUser($('ua').value), b = cleanUser($('ub').value);
    const type = $('type2').value;
    if (!a || !b) return setStatus('Digite as duas contas.', true);
    if (a === b) return setStatus('As contas precisam ser diferentes.', true);
    const force = $('force2').checked;
    await runJob(async () => {
      setStatus(`1/2 — ${TYPE_LABEL[type]} de @${a}…`);
      const la = await fetchList(a, type, { force, onProgress: (s) => { setBar(s.users.length, s.total); setStatus(`1/2 — @${a}: ${s.users.length}${s.total ? '/' + s.total : ''}`); } });
      setStatus(`2/2 — ${TYPE_LABEL[type]} de @${b}…`);
      const lb = await fetchList(b, type, { force, onProgress: (s) => { setBar(s.users.length, s.total); setStatus(`2/2 — @${b}: ${s.users.length}${s.total ? '/' + s.total : ''}`); } });
      const inB = new Set(lb.users.map((u) => u.pk));
      const common = la.users.filter((u) => inB.has(u.pk));
      setBar(1, 1);
      const what = type === 'following' ? 'seguidos em comum' : 'seguidores em comum';
      showResult(`${common.length} ${what} — @${a} × @${b}`, common, `em_comum_${a}_${b}_${TYPE_LABEL[type]}`);
      setStatus(`@${a}: ${la.users.length} · @${b}: ${lb.users.length} · em comum: ${common.length}` +
        (la.truncated || lb.truncated ? ' (uma das listas foi cortada no limite de perfis)' : ''));
    });
  }

  const fmtDT = (t) => new Date(t).toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

  async function addWatch() {
    const u = cleanUser($('uw').value);
    if (!u) return setStatus('Digite um @usuario.', true);
    const w = await getWatch();
    if (w[u]) return setStatus(`@${u} já está sendo monitorada.`);
    if (Object.keys(w).length >= settings.maxWatched) return setStatus(`Limite de ${settings.maxWatched} contas monitoradas (ver Ajustes).`, true);
    w[u] = { addedAt: Date.now(), lastCheck: 0, lastFull: 0, lastCount: null, events: [], unseen: 0 };
    await store.set('watch', w);
    $('uw').value = '';
    renderMonitor();
    setStatus(`@${u} adicionada. Baixando a lista de referência…`);
    monitorTick(u);
  }

  async function markSeen() {
    const w = await getWatch();
    for (const x of Object.values(w)) x.unseen = 0;
    await store.set('watch', w);
    await notifyBackground();
    renderMonitor();
  }

  async function renderMonitor() {
    if (!sh) return;
    const w = await getWatch();
    $('mh').textContent = settings.monitorHours;
    const names = Object.keys(w);
    $('wlist').innerHTML = names.length ? names.map((u) => {
      const x = w[u];
      const next = x.lastCheck ? x.lastCheck + settings.monitorHours * 3600e3 * (x.jitter || 1) : Date.now();
      return `<div class="w"><div><b>@${esc(u)}</b>${x.unseen ? ` <span class="new">${x.unseen} novo(s)</span>` : ''}
        <small>${x.lastCount != null ? x.lastCount + ' seguindo · ' : ''}${x.lastCheck ? 'verificada ' + fmtDT(x.lastCheck) + ' · próxima ~' + fmtDT(next) : 'aguardando 1ª verificação'}</small>
        ${x.lastError ? `<small class="er">${esc(x.lastError)}</small>` : ''}</div>
        <button data-act="now" data-u="${esc(u)}">Verificar agora</button><button data-act="rm" data-u="${esc(u)}">Remover</button></div>`;
    }).join('') : '<div class="muted">Nenhuma conta monitorada.</div>';
    const all = $('wfilter').value === 'all';
    const evs = names.flatMap((u) => w[u].events || []).filter((e) => all || e.kind === 'follow').sort((a, b) => b.to - a.to);
    $('feed').innerHTML = evs.length ? evs.slice(0, 300).map((e) => `<div class="ev ${e.kind === 'unfollow' ? 'un' : ''}">
        <a href="https://www.instagram.com/${esc(e.who)}/" target="_blank">@${esc(e.who)}</a> ${e.kind === 'follow' ? 'seguiu' : 'deixou de seguir'}
        <a href="https://www.instagram.com/${esc(e.username)}/" target="_blank">@${esc(e.username)}</a>
        <small>entre ${fmtDT(e.from)} e ${fmtDT(e.to)}${e.unsure ? ' · incerto (lista veio incompleta)' : ''}</small></div>`).join('')
      : '<div class="muted">Nada ainda. A 1ª verificação de cada conta só guarda a referência; os follows aparecem a partir da próxima mudança.</div>';
    const unseen = names.reduce((n, u) => n + (w[u].unseen || 0), 0);
    $('unseen').style.display = unseen ? '' : 'none';
    $('unseen').textContent = unseen;
  }

  const SETTING_KEYS = Object.keys(DEFAULTS).filter((k) => k !== 'pageSize');
  function fillSettings() { for (const k of SETTING_KEYS) $('s_' + k).value = settings[k]; }

  function build() {
    host = document.createElement('div');
    host.id = 'ig-seguindo-host';
    sh = host.attachShadow({ mode: 'open' });
    sh.innerHTML = `<style>${CSS}</style>${HTML}`;
    document.documentElement.appendChild(host);

    sh.querySelectorAll('nav button').forEach((btn) => btn.addEventListener('click', () => {
      sh.querySelectorAll('nav button').forEach((x) => x.classList.toggle('on', x === btn));
      sh.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t.id === btn.dataset.tab));
    }));
    // Impede que atalhos de teclado do Instagram capturem o que é digitado no painel.
    sh.querySelector('.panel').addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter' && e.target.id === 'u1') doList();
      if (e.key === 'Enter' && (e.target.id === 'ua' || e.target.id === 'ub')) doCompare();
    });
    $('close').onclick = () => (host.style.display = 'none');
    $('go1').onclick = doList;
    $('go2').onclick = doCompare;
    $('stop').onclick = () => { if (job) { job.cancelled = true; job.wake?.(); setStatus('Parando…'); } };
    $('addw').onclick = addWatch;
    $('wfilter').onchange = renderMonitor;
    $('wlist').onclick = async (e) => {
      const b = e.target.closest('button'); if (!b) return;
      const u = b.dataset.u;
      if (b.dataset.act === 'rm') { const w = await getWatch(); delete w[u]; await store.set('watch', w); await notifyBackground(); renderMonitor(); }
      if (b.dataset.act === 'now') monitorTick(u);
    };
    sh.querySelector('nav button[data-tab=t4]').addEventListener('click', markSeen);
    $('filter').oninput = renderList;
    $('view1').onchange = applyView;
    $('csv').onclick = () => current.list.length && exportCSV(current.name, current.list);
    $('json').onclick = () => current.list.length && exportJSON(current.name, current.list);
    $('copy').onclick = async () => {
      if (!current.list.length) return;
      await navigator.clipboard.writeText(current.list.map((u) => '@' + u.username).join('\n'));
      setStatus(`${current.list.length} usernames copiados.`);
    };
    $('save').onclick = async () => {
      const s = { ...settings };
      for (const k of SETTING_KEYS) { const v = parseFloat($('s_' + k).value); if (Number.isFinite(v) && v >= 0) s[k] = v; }
      // pisos de segurança
      s.minDelay = Math.max(1, s.minDelay); s.maxDelay = Math.max(s.minDelay, s.maxDelay);
      s.burstPages = Math.max(1, Math.round(s.burstPages));
      s.burstPauseMin = Math.max(5, s.burstPauseMin); s.burstPauseMax = Math.max(s.burstPauseMin, s.burstPauseMax);
      s.dailyRequestCap = Math.max(1, Math.round(s.dailyRequestCap)); s.maxUsers = Math.max(12, Math.round(s.maxUsers));
      s.monitorHours = Math.max(1, s.monitorHours); s.fullRecheckDays = Math.max(1, s.fullRecheckDays); s.maxWatched = Math.max(1, Math.round(s.maxWatched));
      settings = s;
      await store.set('settings', s);
      fillSettings(); refreshUsage(await store.get('usage'));
      setStatus('Ajustes salvos.');
    };
    $('reset').onclick = async () => { settings = { ...DEFAULTS }; await store.set('settings', settings); fillSettings(); setStatus('Padrões restaurados.'); };
    $('clear').onclick = async () => {
      const all = await chrome.storage.local.get(null);
      const keys = Object.keys(all).filter((k) => k.startsWith('list:') || k.startsWith('profile:'));
      await chrome.storage.local.remove(keys);
      setStatus(`Cache limpo (${keys.length} itens). O histórico de novos/removidos foi mantido.`);
    };

    // Preenche com o perfil aberto na aba, se houver.
    const m = location.pathname.match(/^\/([A-Za-z0-9._]{1,30})\/?/);
    if (m && !['explore', 'direct', 'reels', 'accounts', 'stories', 'p', 'reel'].includes(m[1])) $('u1').value = m[1];

    fillSettings();
    store.get('usage').then(refreshUsage);
    renderMonitor();
  }

  async function open() {
    if (!host) build();
    host.style.display = '';
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === 'toggle') { if (host && host.style.display !== 'none') host.style.display = 'none'; else open(); }
    if (msg?.type === 'open') open();
    if (msg?.type === 'openMonitor') open().then(() => sh.querySelector('nav button[data-tab=t4]').click());
  });

  // Agenda do monitor: roda enquanto houver uma aba do Instagram aberta (uma aba por vez, via trava).
  setTimeout(() => monitorTick(), rand(20, 60) * 1000);
  setInterval(() => monitorTick(), 10 * 60e3);
  chrome.storage.onChanged.addListener((ch) => { if (ch.watch && sh && host.style.display !== 'none') renderMonitor(); });

  store.get('settings').then((s) => { if (s) settings = { ...DEFAULTS, ...s }; });
})();
