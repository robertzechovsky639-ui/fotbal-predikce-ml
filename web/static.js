'use strict';
const STATIC = true;
const ST = { all: [], byId: {}, byPair: {}, teams: [], model: null, rules: null, generated: 0, slugs: [] };
const SOURCES = {
  sofascore: { fn: srcSofa, base: 20000, iv: 20000, lat: [] },
  s365: { fn: src365, base: 2500, iv: 2500, lat: [] },
  espn: { fn: srcEspn, base: 4000, iv: 4000, lat: [] },
};
ST.srcOk = {};
let espnCursor = 0;

function pragueDate(ts) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(ts * 1000));
  const g = t => parts.find(p => p.type === t).value;
  return g('year') + '-' + g('month') + '-' + g('day');
}
function dayOf(ts) {
  const a = Date.parse(pragueDate(Date.now() / 1000) + 'T00:00:00Z');
  const b = Date.parse(pragueDate(ts) + 'T00:00:00Z');
  return Math.round((b - a) / 864e5);
}
function pairKey(m) {
  const a = Fotbal.canon(m.teams[0].name), b = Fotbal.canon(m.teams[1].name);
  const x = a < b ? a : b, y = a < b ? b : a;
  return pragueDate(m.ts) + '|' + x + '|' + y;
}
function indexM(m) {
  if (!m.ssid && typeof m.id === 'string' && m.id.indexOf('sofa:') === 0) m.ssid = m.id.slice(5);
  ST.byId[m.id] = m; ST.byPair[pairKey(m)] = m; m.day = m.status === 'live' ? 0 : dayOf(m.ts);
}

function applyData(d) {
  const merged = Fotbal.mergeList({ generated: ST.generated, matches: ST.all }, d);
  if (!merged.changed) return false;
  ST.generated = merged.generated; ST.all = merged.matches; ST.byId = {}; ST.byPair = {};
  for (const m of ST.all) { if (!m.pred) Fotbal.ensurePred(m, predCtx()); indexM(m); if (m.status === 'live') Fotbal.liveCalc(m); }
  return true;
}
const REFRESH_MS = 7 * 60 * 1000;
function scheduleRefresh() {
  setInterval(() => {
    fetch('data/matches.json', { cache: 'no-cache' }).then(r => r.json()).then(d => {
      if (applyData(d) && typeof render === 'function') render();
      if (typeof upd === 'function') upd();
    }).catch(() => {});
  }, REFRESH_MS);
}
async function loadStatic() {
  const [rules, model, teams, data] = await Promise.all([
    fetch('names_rules.json').then(r => r.json()),
    fetch('data/model.json').then(r => r.json()).catch(() => null),
    fetch('data/teams.json').then(r => r.json()).catch(() => []),
    fetch('data/matches.json', { cache: 'no-cache' }).then(r => r.json()),
  ]);
  ST.rules = rules; Fotbal.setRules(rules); ST.model = model; ST.teams = teams || [];
  try { ST.slugs = await fetch('espn_slugs.json').then(r => r.json()); } catch (e) { ST.slugs = []; }
  applyData(data);
  for (const m of ST.all) Fotbal.ensurePred(m, { teams: ST.teams, elo_params: model && model.elo_params });
  scheduleRefresh();
}
function fileId(id) { return String(id).replace(/[^A-Za-z0-9._-]+/g, '_'); }
async function staticApi(u) {
  if (u.startsWith('/api/model')) return ST.model || {};
  if (u.startsWith('/api/teams')) {
    const q = decodeURIComponent((u.split('q=')[1] || '')).toLowerCase();
    return ST.teams.filter(t => (t.name || '').toLowerCase().includes(q)).slice(0, 8);
  }
  const mm = u.match(/\/api\/match\/(.+)/);
  if (mm) {
    const id = decodeURIComponent(mm[1]);
    const r = await fetch('data/m/' + fileId(id) + '.json', { cache: 'no-cache' });
    const d = await r.json();
    const live = ST.byId[id];
    if (live) { d.status = live.status; d.hg = live.hg; d.ag = live.ag; d.minute = live.minute; d.pred = live.pred; d.live = live.live; d.reds = live.reds; }
    return d;
  }
  if (u.startsWith('/api/predict')) {
    const q = new URLSearchParams(u.split('?')[1] || '');
    const m = { teams: [{ name: q.get('a') }, { name: q.get('b') }], country: null, region: 'europe_top', neutral: false, pred: null };
    Fotbal.ensurePred(m, { teams: ST.teams, elo_params: ST.model && ST.model.elo_params });
    return { pred: m.pred, note: m.pred_note, elo: m.elo, n: m.n, low: true };
  }
  return { matches: ST.all.filter(m => m.day === (+(new URLSearchParams(u.split('?')[1] || '').get('day') || 0))) };
}

const _jobs = new Map(); let _wj = null, _jid = 0;
function pollWorker() {
  if (_wj) return _wj;
  try { _wj = new Worker('poll-worker.js'); } catch (e) { return null; }
  _wj.onmessage = e => { const job = _jobs.get(e.data.id); if (!job) return; _jobs.delete(e.data.id); if (e.data.error) job.rej(new Error(e.data.error)); else job.res(e.data.data); };
  return _wj;
}
function j(u, ms) {
  ms = ms || 8000;
  const w = typeof Worker !== 'undefined' && pollWorker();
  if (!w) {
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const t = setTimeout(() => ctrl && ctrl.abort(), ms);
    return fetch(u, { cache: 'no-store', signal: ctrl && ctrl.signal }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).finally(() => clearTimeout(t));
  }
  return new Promise((res, rej) => {
    const id = ++_jid;
    const t = setTimeout(() => { if (!_jobs.has(id)) return; _jobs.delete(id); try { w.postMessage({ abort: true, id }); } catch (e) {} rej(new Error('timeout')); }, ms);
    _jobs.set(id, { res: v => { clearTimeout(t); res(v); }, rej: e => { clearTimeout(t); rej(e); } });
    w.postMessage({ id, url: u });
  });
}
function health() {
  const now = Date.now();
  return ['sofascore', 's365', 'espn', 'sofaDetail'].map(k => {
    const ok = ST.srcOk[k], err = ST.srcOk[k + 'Err'];
    return { k, state: err && !(ok > now - 10000) ? 'err' : ok > now - 20000 ? 'ok' : 'wait' };
  });
}
function freshToken(token) { return !token || !SOURCES[token.src] || SOURCES[token.src].cur === token; }
function predCtx() { return { teams: ST.teams, elo_params: ST.model && ST.model.elo_params }; }
function consider(m, upd, token) {
  if (!m || !upd) return null;
  if (!Fotbal.applyLive(m, upd, token, freshToken)) return null;
  m.day = m.status === 'live' ? 0 : dayOf(m.ts);
  return m.id;
}
function upsert(partial, token) {
  if (!partial || !partial.teams) return null;
  let m = ST.byId[partial.id] || ST.byPair[pairKey(partial)];
  if (!m) {
    m = partial;
    m.region = m.region || 'europe_lower';
    m.reds = m.reds || [0, 0];
    Fotbal.ensurePred(m, predCtx());
    ST.all.push(m); indexM(m);
    if (m.status === 'live') Fotbal.liveCalc(m);
    return m.id;
  }
  if (!m.ssid && partial.ssid) m.ssid = partial.ssid;
  const upd = Fotbal.alignUpdate(m, partial);
  if (!upd) return null;
  return consider(m, upd, token);
}

function ymd(offset) {
  const d = new Date(Date.now() + offset * 864e5);
  const p = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Prague', year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
  return p.replace(/-/g, '');
}
function women(name) { const s = (name || '').toLowerCase(); return /(^|\s)(w|women|woman|u17|u19|u20|u21|u23|youth)\b|\(w\)|femen|frauen/.test(s); }

function slowNet() {
  const narrow = typeof matchMedia === 'function' && matchMedia('(max-width: 760px)').matches;
  const c = navigator.connection;
  return !!(narrow || (c && (c.saveData || c.effectiveType === 'slow-2g' || c.effectiveType === '2g' || c.effectiveType === '3g')));
}
function pollPlan() {
  return slowNet()
    ? { sofascore: 30000, s365: 5000, espn: 8000, detail: 1800, lag: { sofascore: 0, s365: 700, espn: 1400 } }
    : { sofascore: 20000, s365: 2500, espn: 4000, detail: 1100, lag: { sofascore: 0, s365: 400, espn: 800 } };
}
async function srcSofa(changed, token) {
  const d = await j('https://api.sofascore1.com/api/v1/sport/football/events/live');
  for (const ev of d.events || []) {
    const partial = Fotbal.parseSofaEvent(ev);
    if (!partial || women(partial.homeName) || women(partial.awayName) || women(partial.league_name)) continue;
    const id = upsert(partial, token);
    if (id) changed.add(id);
  }
}
async function src365(changed, token) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Prague', day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date()).split('/');
  const stamp = parts[0] + '/' + parts[1] + '/' + parts[2];
  const d = await j('https://webws.365scores.com/web/games/allscores/?sports=1&startDate=' + stamp + '&endDate=' + stamp + '&timezoneName=Europe/Prague&userCountryId=1');
  for (const g of d.games || []) {
    const partial = Fotbal.parse365(g);
    if (!partial || women(partial.homeName) || women(partial.awayName) || women(partial.league_name)) continue;
    const id = upsert(partial, token);
    if (id) changed.add(id);
  }
}
async function srcEspn(changed, token) {
  const slugs = ST.slugs || [];
  if (!slugs.length) throw new Error('bez lig');
  const batch = [];
  for (let i = 0; i < 5; i++) batch.push(slugs[(espnCursor + i) % slugs.length]);
  espnCursor = (espnCursor + 5) % slugs.length;
  const stamp = ymd(0);
  let ok = 0;
  await Promise.all(batch.map(async slug => {
    try {
      const d = await j('https://site.api.espn.com/apis/site/v2/sports/soccer/' + slug + '/scoreboard?dates=' + stamp);
      ok++;
      for (const ev of d.events || []) {
        const partial = Fotbal.parseEspnEvent(ev);
        if (!partial || women(partial.homeName) || women(partial.awayName)) continue;
        partial.league = slug;
        const id = upsert(partial, token);
        if (id) changed.add(id);
      }
    } catch (e) {}
  }));
  if (!ok) throw new Error('espn');
}
async function sofaDetail(onChange) {
  let i = 0;
  const step = async () => {
    let wait = pollPlan().detail;
    try {
      if (document.hidden) { setTimeout(step, 15000); return; }
      const open = (typeof S !== 'undefined' && S.detail && S.detail.id) || null;
      const onScreen = new Set([...document.querySelectorAll('#view .m')].map(el => el.dataset.id));
      let list = ST.all.filter(m => m.status === 'live' && m.ssid);
      if (onScreen.size) list = list.filter(m => m.id === open || onScreen.has(m.id));
      else list = list.slice(0, 4);
      if (list.length) {
        const m = list[i++ % list.length];
        const ev = await j('https://api.sofascore1.com/api/v1/event/' + m.ssid);
        const event = ev.event || ev;
        const partial = Fotbal.parseSofaEvent(event);
        const ids = [];
        if (partial) {
          const reds = Fotbal.parseSofaIncidents(await j('https://api.sofascore1.com/api/v1/event/' + m.ssid + '/incidents').catch(() => ({})));
          partial.reds = reds;
          const id = upsert(partial, { src: 'sofascore', t0: Date.now(), gen: 'detail' });
          if (id) ids.push(id);
        }
        if (!(m.ss_odds_t > Date.now() - 60000)) {
          m.ss_odds_t = Date.now();
          const odds = Fotbal.parseSofaOdds(await j('https://api.sofascore1.com/api/v1/event/' + m.ssid + '/odds/1/featured').catch(e => { if (/404/.test(String(e))) return {}; throw e; }));
          if (odds && !m.odds) { m.odds = odds; ids.push(m.id); }
        }
        if (ids.length) onChange(ids);
      }
      ST.srcOk.sofaDetail = Date.now();
      delete ST.srcOk.sofaDetailErr;
    } catch (e) {
      ST.srcOk.sofaDetailErr = String(e);
      wait = Math.min(30000, wait * 2);
    }
    setTimeout(step, wait);
  };
  setTimeout(step, 2500);
}
function staticLoop() {
  const plan = pollPlan();
  sofaDetail(ids => { if (typeof paintList === 'function') paintList(ids); if (typeof upd === 'function') upd(); });
  for (const [k, Src] of Object.entries(SOURCES)) {
    Src.base = plan[k]; Src.iv = Src.base;
    const run = async () => {
      const changed = new Set();
      const t0 = performance.now();
      const next = pollPlan();
      Src.base = next[k];
      const token = { src: k, t0: Date.now(), gen: (Src.gen = (Src.gen || 0) + 1) };
      Src.cur = token;
      try {
        await Src.fn(changed, token);
        Src.iv = Src.base;
        ST.srcOk[k] = Date.now();
        delete ST.srcOk[k + 'Err'];
      } catch (e) {
        Src.iv = Math.min((Src.iv || Src.base) * 2, 30000);
        ST.srcOk[k + 'Err'] = String(e);
      }
      Src.lat = [...(Src.lat || []).slice(-29), performance.now() - t0];
      if (changed.size && Src.cur === token && typeof paintList === 'function') paintList([...changed]);
      if (typeof upd === 'function') upd();
      const wait = document.hidden ? Math.max(Src.iv, 15000) : Src.iv;
      setTimeout(run, wait);
    };
    setTimeout(run, plan.lag[k] || 0);
  }
}
