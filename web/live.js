/* Čistá logika: sjednocení jmen, monotónní skóre, Poisson 1X2. Stejná pravidla jako backend. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.Fotbal = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const REGION_BASE = { europe_top: 1680, europe_lower: 1500, czech: 1500, europe_cups: 1580, asia: 1500, south_america: 1560, international: 1500, other: 1480 };
  let RULES = { stop: [], city: {}, aliases: {}, countries: {} };

  function setRules(rules) { RULES = rules || RULES; }
  function strip(value) {
    return String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/['’]/g, '');
  }
  function canon(name) {
    const text = strip(name).replace(/[^a-z0-9]+/g, ' ');
    const out = [];
    for (const token of text.split(' ').filter(Boolean)) {
      if (/^\d+$/.test(token)) continue;
      if (/^(18|19|20)\d\d$/.test(token)) continue;
      if ((RULES.stop || []).indexOf(token) >= 0) continue;
      out.push((RULES.city || {})[token] || token);
    }
    const key = out.join(' ');
    return (RULES.aliases || {})[key] || key;
  }
  function codeOf(value) {
    const text = strip(value).replace(/[^a-z0-9]+/g, ' ').trim();
    if (!text) return null;
    const map = RULES.countries || {};
    if (map[text]) return map[text];
    const compact = text.replace(/ /g, '');
    return map[compact] || null;
  }
  function clubId(name, country) {
    return 'club:' + (codeOf(country) || 'xx') + ':' + (canon(name) || 'unknown');
  }

  function pois(maxg, lam) {
    lam = Math.min(6.5, Math.max(0.05, lam));
    let p = Math.exp(-lam), acc = 0;
    const arr = new Array(maxg + 1);
    for (let i = 0; i < maxg; i++) { arr[i] = p; acc += p; p *= lam / (i + 1); }
    arr[maxg] = Math.max(0, 1 - acc);
    return arr;
  }
  function scoreMatrix(lh, la, rho, maxg) {
    maxg = maxg == null ? 8 : maxg;
    const hs = pois(maxg, lh), aw = pois(maxg, la);
    const m = [];
    let total = 0;
    for (let i = 0; i <= maxg; i++) {
      m[i] = [];
      for (let j = 0; j <= maxg; j++) {
        let v = hs[i] * aw[j];
        if (rho) {
          let tau = 1;
          if (i === 0 && j === 0) tau = 1 - lh * la * rho;
          else if (i === 0 && j === 1) tau = 1 + lh * rho;
          else if (i === 1 && j === 0) tau = 1 + la * rho;
          else if (i === 1 && j === 1) tau = 1 - rho;
          v *= Math.max(1e-8, tau);
        }
        m[i][j] = Math.max(0, v);
        total += m[i][j];
      }
    }
    if (total <= 0) { m[0][0] = 1; total = 1; }
    for (let i = 0; i <= maxg; i++) for (let j = 0; j <= maxg; j++) m[i][j] /= total;
    return m;
  }
  function marketsFrom(matrix, baseH, baseA) {
    let home = 0, draw = 0, away = 0, over = 0, btts = 0;
    const exact = [];
    const n = matrix.length;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const p = matrix[i][j];
      const H = (baseH || 0) + i, A = (baseA || 0) + j;
      if (H > A) home += p; else if (H === A) draw += p; else away += p;
      if (H + A >= 3) over += p;
      if (H >= 1 && A >= 1) btts += p;
      exact.push([H + '-' + A, p]);
    }
    const t = home + draw + away || 1;
    exact.sort((a, b) => b[1] - a[1]);
    return { p: [home / t, draw / t, away / t], over, under: 1 - over, btts, exact: exact.slice(0, 5) };
  }
  function markets(lh, la, rho) { return marketsFrom(scoreMatrix(lh, la, rho || 0, 8), 0, 0); }
  function liveMarkets(hg, ag, lh, la) { return marketsFrom(scoreMatrix(Math.max(lh, 1e-4), Math.max(la, 1e-4), 0, 6), hg, ag); }

  function remaining(lh, la, minute, reds, score, period) {
    minute = minute == null ? 0 : +minute;
    period = +period || 1;
    let frac, late = 1;
    if (period > 2 || minute >= 120) frac = 0;
    else {
      const m = Math.min(Math.max(minute, 0), 99);
      const regular = Math.max(0, 90 - Math.min(m, 90));
      const extra = m > 90 ? Math.max(0, 96 - m) : 0;
      frac = (regular + extra) / 90;
      if (m > 75) late = 1 + 0.35 * Math.max(0, Math.min(m, 90) - 75) / 15;
      frac *= late;
    }
    let lh2 = lh * frac, la2 = la * frac;
    const rh = (reds && reds[0]) || 0, ra = (reds && reds[1]) || 0;
    if (rh > ra) { lh2 *= 0.68 ** (rh - ra); la2 *= 1.18 ** (rh - ra); }
    else if (ra > rh) { la2 *= 0.68 ** (ra - rh); lh2 *= 1.18 ** (ra - rh); }
    if (minute >= 60 && minute <= 100 && period <= 2) {
      const diff = ((score && score[0]) || 0) - ((score && score[1]) || 0);
      if (diff <= -1) { lh2 *= 1.10; la2 *= 0.94; }
      else if (diff >= 1) { la2 *= 1.10; lh2 *= 0.94; }
    }
    return [Math.max(lh2, 1e-4), Math.max(la2, 1e-4)];
  }

  function eloLambdas(eloH, eloA, neutral, params) {
    const p = params || { ha: 70, coef: 0.55, base_h: 1.48, base_a: 1.18 };
    const ha = neutral ? 0 : p.ha;
    const coef = p.coef;
    const baseH = neutral ? 1.3 : (p.base_h || 1.48);
    const baseA = neutral ? 1.3 : (p.base_a || 1.18);
    const diff = (eloH + ha - eloA) / 400;
    const lh = Math.min(4.8, Math.max(0.15, Math.exp(Math.log(baseH) + coef * diff)));
    const la = Math.min(4.8, Math.max(0.15, Math.exp(Math.log(baseA) - coef * diff)));
    return [lh, la];
  }

  function rankStatus(s) {
    if (s === 'live') return 1;
    if (s === 'finished' || s === 'abandoned' || s === 'cancelled') return 2;
    return 0;
  }
  function liveKey(m) {
    const r = m.reds || [0, 0];
    return [m.status, m.hg, m.ag, m.minute, m.period, r[0], r[1], m.pred && m.pred.h].join('|');
  }
  function applyLive(m, upd, token, fresh) {
    // Starší odpověď stejného zdroje smí stav jen posunout dopředu. Skóre, minuta ani predikce se nevrací.
    const stale = !!(fresh && token && !fresh(token));
    if ((m.status === 'finished' || m.status === 'abandoned') && upd.status !== 'finished' && upd.status !== 'abandoned') return false;
    if (m.status === 'cancelled' && upd.status !== 'cancelled') return false;
    if (m.status === 'live' && (upd.status === 'upcoming' || upd.status === 'postponed')) return false;
    if (m.status === 'postponed' && upd.status === 'upcoming') return false;
    if (upd.status && rankStatus(upd.status) < rankStatus(m.status)) return false;
    const uh = upd.hg, ua = upd.ag;
    if (m.hg != null && uh != null && uh < m.hg) return false;
    if (m.ag != null && ua != null && ua < m.ag) return false;
    if (upd.minute != null && m.minute != null && upd.minute < m.minute) return false;
    if (upd.period != null && m.period != null && upd.period < m.period) return false;
    if (upd.reds && m.reds && (upd.reds[0] < m.reds[0] || upd.reds[1] < m.reds[1])) return false;
    const scoreUp = (uh != null && (m.hg == null || uh > m.hg)) || (ua != null && (m.ag == null || ua > m.ag));
    const minuteUp = upd.minute != null && (m.minute == null || upd.minute > m.minute);
    const statusUp = upd.status && rankStatus(upd.status) > rankStatus(m.status);
    const redsUp = upd.reds && (upd.reds[0] > ((m.reds || [0, 0])[0]) || upd.reds[1] > ((m.reds || [0, 0])[1]));
    if (stale && !scoreUp && !minuteUp && !statusUp && !redsUp) return false;
    const before = liveKey(m);
    if (uh != null) m.hg = uh;
    if (ua != null) m.ag = ua;
    if (upd.status) m.status = upd.status;
    if (upd.minute != null) m.minute = upd.minute;
    if (upd.period != null) m.period = upd.period;
    if (upd.reds) m.reds = [upd.reds[0] || 0, upd.reds[1] || 0];
    if (upd.winner != null) m.winner = upd.winner;
    if (liveKey(m) === before) return false;
    if (token) m._accAt = token.t0 || Date.now();
    if (m.status === 'live') liveCalc(m);
    return true;
  }

  function espnMinute(clock) {
    const text = String(clock || '');
    const plus = /(\d+)\s*'\s*\+\s*(\d+)/.exec(text);
    if (plus) return (+plus[1]) + (+plus[2]);
    const n = /(\d+)/.exec(text);
    return n ? +n[1] : null;
  }
  function espnStatus(comp) {
    const st = (comp.status && comp.status.type) || {};
    const name = st.name || '';
    if (name === 'STATUS_POSTPONED') return 'postponed';
    if (name === 'STATUS_CANCELED' || name === 'STATUS_CANCELLED') return 'cancelled';
    if (name === 'STATUS_ABANDONED') return 'abandoned';
    if (st.state === 'in') return 'live';
    if (st.state === 'post' || name === 'STATUS_FULL_TIME') return 'finished';
    return 'upcoming';
  }
  function parseEspnEvent(ev) {
    const comp = (ev.competitions || [])[0];
    if (!comp) return null;
    const sides = {};
    for (const c of comp.competitors || []) sides[c.homeAway] = c;
    if (!sides.home || !sides.away) return null;
    const status = espnStatus(comp);
    const minute = espnMinute(comp.status && comp.status.displayClock);
    const period = (comp.status && +comp.status.period) || (minute > 45 ? 2 : 1);
    const reds = [0, 0];
    let saw = false;
    for (const det of comp.details || []) {
      if (!det.redCard) continue;
      saw = true;
      const tid = det.team && String(det.team.id);
      if (tid && tid === String(sides.home.team.id)) reds[0]++;
      else reds[1]++;
    }
    const goals = side => {
      if (status === 'upcoming' || side.score == null || side.score === '') return null;
      const n = +side.score;
      return Number.isFinite(n) ? n : null;
    };
    const home = sides.home.team.displayName, away = sides.away.team.displayName;
    return {
      id: 'espn:' + ev.id, src: 'espn', ts: Math.floor(Date.parse(ev.date) / 1000),
      status, minute: status === 'upcoming' ? null : minute, period: period > 2 ? period : period,
      hg: goals(sides.home), ag: goals(sides.away), reds: saw ? reds : undefined,
      homeName: home, awayName: away, teams: [{ name: home }, { name: away }],
    };
  }

  function sofaGoals(block, type) {
    if (!block) return null;
    if (type === 'finished' && block.normaltime != null) return +block.normaltime;
    if (block.current == null) return null;
    const n = +block.current;
    return n < 0 ? null : n;
  }
  function sofaMinute(ev, nowSec) {
    const st = ev.status || {};
    const desc = String(st.description || '').toLowerCase();
    const t = ev.time || {};
    if (desc.includes('halftime') || desc === 'ht') return { minute: 45, period: 1 };
    let period = 1;
    if (desc.includes('2nd')) period = 2;
    else if (desc.includes('pen')) period = 5;
    else if (desc.includes('extra') || desc.includes('aet')) period = 3;
    if (st.type === 'finished' || desc.includes('ended') || desc === 'ft' || desc.includes('after pen')) {
      return { minute: period >= 3 ? 120 : 90, period: period >= 3 ? period : 2 };
    }
    if (st.type !== 'inprogress' || !t.currentPeriodStartTimestamp) return { minute: null, period };
    const now = nowSec == null ? Date.now() / 1000 : nowSec;
    const elapsed = Math.max(0, now - (+t.currentPeriodStartTimestamp));
    let sec = (+t.initial || 0) + elapsed;
    const cap = (t.max != null ? +t.max : (period === 1 ? 2700 : 5400)) + (+t.extra || 0);
    if (sec > cap) sec = cap;
    return { minute: Math.floor(sec / 60), period };
  }
  function parseSofaEvent(ev, nowSec) {
    const home = ev.homeTeam && ev.homeTeam.name, away = ev.awayTeam && ev.awayTeam.name;
    if (!home || !away) return null;
    const type = (ev.status && ev.status.type) || '';
    const desc = String((ev.status && ev.status.description) || '').toLowerCase();
    let status = 'upcoming';
    if (type === 'inprogress') status = 'live';
    else if (type === 'finished') status = 'finished';
    else if (type === 'postponed' || desc.includes('postpon')) status = 'postponed';
    else if (desc.includes('cancel')) status = 'cancelled';
    else if (desc.includes('abandon')) status = 'abandoned';
    const clock = sofaMinute(ev, nowSec);
    return {
      id: 'sofa:' + ev.id, src: 'sofascore', ssid: ev.id, ts: ev.startTimestamp,
      status, minute: status === 'live' || status === 'finished' ? clock.minute : null, period: clock.period,
      hg: sofaGoals(ev.homeScore, type), ag: sofaGoals(ev.awayScore, type),
      homeName: home, awayName: away, teams: [{ name: home }, { name: away }],
      league_name: (ev.tournament && ev.tournament.name) || '',
    };
  }
  function parseSofaIncidents(payload) {
    const reds = [0, 0];
    for (const it of (payload && payload.incidents) || []) {
      if (it.incidentType !== 'card') continue;
      if (it.incidentClass !== 'red' && it.incidentClass !== 'yellowRed') continue;
      reds[it.isHome ? 0 : 1]++;
    }
    return reds;
  }
  function fracDec(text) {
    const [a, b] = String(text || '').split('/').map(Number);
    return b ? 1 + a / b : null;
  }
  function parseSofaOdds(payload) {
    const feat = (payload && payload.featured) || {};
    let market = null;
    for (const v of Object.values(feat)) {
      if (!v || v.marketId !== 1 || v.suspended) continue;
      const names = (v.choices || []).map(c => c.name);
      if (names.indexOf('1') >= 0 && names.indexOf('X') >= 0 && names.indexOf('2') >= 0) { market = v; break; }
    }
    if (!market) return null;
    const c = {};
    for (const x of market.choices) c[x.name] = fracDec(x.fractionalValue);
    if (!(c['1'] > 1 && c['X'] > 1 && c['2'] > 1)) return null;
    return { h: +c['1'].toFixed(2), d: +c['X'].toFixed(2), a: +c['2'].toFixed(2) };
  }

  function s365Status(g) {
    const low = String(g.statusText || '').toLowerCase();
    if (low.includes('postpon')) return 'postponed';
    if (low.includes('cancel')) return 'cancelled';
    if (low.includes('abandon')) return 'abandoned';
    if (g.statusGroup === 3 || low === '1st half' || low === '2nd half' || low === 'halftime') return 'live';
    if (g.statusGroup === 4 || low.includes('ended') || low.includes('final') || low.includes('penalt')) return 'finished';
    return 'upcoming';
  }
  function parse365(g) {
    let home = g.homeCompetitor || {}, away = g.awayCompetitor || {};
    if (g.isHomeAwayInverted) { const s = home; home = away; away = s; }
    if (!home.name || !away.name) return null;
    const status = s365Status(g);
    const goals = side => {
      if (status === 'upcoming' || side.score == null || +side.score < 0) return null;
      return +side.score;
    };
    const low = String(g.statusText || '').toLowerCase();
    let period = 1;
    if (low.includes('pen')) period = 5;
    else if (low.includes('extra')) period = 3;
    else if (low.includes('2nd') || (+g.gameTime > 45 && status === 'live')) period = 2;
    const minute = status === 'live' && g.gameTime != null && +g.gameTime >= 0 ? Math.round(+g.gameTime) : null;
    return {
      id: 's365:' + g.id, src: 's365', ts: Math.floor(Date.parse(g.startTime) / 1000),
      status, minute, period, hg: goals(home), ag: goals(away),
      homeName: home.name, awayName: away.name, teams: [{ name: home.name }, { name: away.name }],
      league_name: g.competitionDisplayName || '',
    };
  }
  function orient(m, homeName, awayName) {
    const h = canon(m.teams[0].name), a = canon(m.teams[1].name);
    const H = canon(homeName), A = canon(awayName);
    if (h === H && a === A) return 1;
    if (h === A && a === H) return -1;
    return 0;
  }
  function alignUpdate(m, partial) {
    const rel = orient(m, partial.homeName || partial.teams[0].name, partial.awayName || partial.teams[1].name);
    if (!rel) return null;
    const upd = { status: partial.status, minute: partial.minute, period: partial.period, winner: partial.winner };
    if (rel > 0) { upd.hg = partial.hg; upd.ag = partial.ag; if (partial.reds) upd.reds = partial.reds; }
    else { upd.hg = partial.ag; upd.ag = partial.hg; if (partial.reds) upd.reds = [partial.reds[1], partial.reds[0]]; }
    return upd;
  }

  function findTeam(teams, name, country) {
    const key = canon(name);
    const code = codeOf(country);
    if (code) {
      const id = 'club:' + code + ':' + key;
      const hit = (teams || []).find(t => t.id === id);
      if (hit) return hit;
    }
    const hits = (teams || []).filter(t => t.id && t.id.endsWith(':' + key));
    hits.sort((a, b) => (b.n || 0) - (a.n || 0));
    return hits[0] || null;
  }
  function priorOf(region) { return REGION_BASE[region] || 1450; }

  function ensurePred(m, ctx) {
    if (m.pred && m.pred.h != null && m.pred.d != null && m.pred.a != null) return m;
    const params = (ctx && ctx.elo_params) || { ha: 70, coef: 0.55, base_h: 1.48, base_a: 1.18 };
    const teams = (ctx && ctx.teams) || [];
    const h = findTeam(teams, m.teams[0].name, m.country);
    const a = findTeam(teams, m.teams[1].name, m.country);
    const prior = priorOf(m.region);
    const eloH = h ? h.elo : prior, eloA = a ? a.elo : prior;
    const lam = eloLambdas(eloH, eloA, !!m.neutral, params);
    const mk = markets(lam[0], lam[1], 0);
    m.pred = { h: +mk.p[0].toFixed(4), d: +mk.p[1].toFixed(4), a: +mk.p[2].toFixed(4) };
    m.lam = lam; m.rho = 0; m.ou = { over: mk.over, under: mk.under, line: 2.5 }; m.btts = mk.btts;
    m.exact = mk.exact.map(x => [x[0], +x[1].toFixed(4)]);
    m.pred_low = true;
    m.pred_note = (!h || !a || (h.n || 0) < 8 || (a.n || 0) < 8)
      ? 'Tým není v historii – odhad podle síly soutěže, nižší spolehlivost.'
      : 'Málo historie v soutěži – odhad z Elo a síly ligy, nižší spolehlivost.';
    m.elo = [Math.round(eloH), Math.round(eloA)];
    m.n = [h ? h.n : 0, a ? a.n : 0];
    return m;
  }

  function liveCalc(m) {
    if (m.status !== 'live' || !m.pred || !m.lam) { if (m.status !== 'live') m.live = m.live && m.status === 'finished' ? m.live : null; return false; }
    const key = liveKey(m);
    if (m.live && m._lk === key) return false;
    const rem = remaining(m.lam[0], m.lam[1], m.minute || 0, m.reds || [0, 0], [m.hg || 0, m.ag || 0], m.period || 1);
    const mk = liveMarkets(m.hg || 0, m.ag || 0, rem[0], rem[1]);
    m.live = { p: { h: mk.p[0], d: mk.p[1], a: mk.p[2] }, ou: mk.over, btts: mk.btts, exact: mk.exact, rem };
    m._lk = key;
    return true;
  }

  return {
    setRules, canon, codeOf, clubId, scoreMatrix, markets, liveMarkets, remaining, eloLambdas,
    applyLive, ensurePred, liveCalc, liveKey, findTeam, priorOf,
    parseEspnEvent, parseSofaEvent, parseSofaIncidents, parseSofaOdds, parse365, orient, alignUpdate, espnMinute, sofaMinute,
  };
});
