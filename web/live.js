/* Čistá logika: sjednocení jmen, monotónní skóre, Poisson 1X2. Stejná pravidla jako backend. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.Fotbal = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const REGION_BASE = { europe_top: 1680, europe_lower: 1500, czech: 1500, europe_cups: 1580, asia: 1500, south_america: 1560, international: 1500, other: 1480 };
  let RULES = { stop: [], city: {}, aliases: {}, countries: {} };
  let COMP = null;

  let S365_COUNTRY = {};
  function setRules(rules) { RULES = rules || RULES; }
  function setComp(rules) { COMP = rules || {}; }
  function set365Index(comps, countries) {
    const names = {};
    for (const c of countries || []) if (c && c.id != null && c.name) names[c.id] = c.name;
    const next = {};
    for (const c of comps || []) {
      if (!c || c.id == null) continue;
      const name = names[c.countryId];
      if (name) next[c.id] = name;
    }
    S365_COUNTRY = next;
  }
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
  function compIds(key) {
    const out = {};
    for (const raw of ((COMP && COMP[key]) || [])) out[+raw] = true;
    return out;
  }
  function compHas(key, value) {
    if (value == null || value === '') return false;
    return !!compIds(key)[+value];
  }
  function tagBlob(home, away, slug, tournamentSlug) {
    return [home, away, slug, tournamentSlug].filter(Boolean).join(' ').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }
  function tagsOf(spec) {
    const tags = [];
    const blob = tagBlob(spec.home, spec.away, spec.slug, spec.tournament_slug);
    const label = String(spec.label || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    if (/\b(women|woman|femen|feminin|frauen|ladies|damen|nwsl)\b|\(w\)/.test(blob) || compHas('women_s365', spec.competition_id) || compHas('women_sofa', spec.tournament_id)) tags.push('women');
    const slug = String(spec.tournament_slug || '');
    if (compHas('college_sofa', spec.tournament_id) || /(^|[-.])ncaa([.-]|$)/.test(slug) || String(spec.slug || '').indexOf('ncaa') >= 0 || /\bncaa\b/.test(label)) tags.push('college');
    if (/\b(u1[0-9]|u2[0-3]|youth|junior)\b/.test(blob) || compHas('youth_s365', spec.competition_id) || compHas('youth_sofa', spec.tournament_id)) tags.push('youth');
    if (/\b(ii|iii|iv|reserves|reserve|rezerva|rezervy)\b/.test(blob)) tags.push('reserve');
    return tags;
  }
  function segmentOf(tags) {
    for (const name of ['women', 'college', 'youth', 'reserve']) if (tags.indexOf(name) >= 0) return name;
    return 'main';
  }
  function countryLabel(code, raw) {
    const labels = (COMP && COMP.labels) || {};
    if (code && labels[code]) return labels[code];
    const continents = (COMP && COMP.continent) || {};
    if (raw && String(raw).trim() && !continents[String(raw).trim().toLowerCase()]) return String(raw).trim();
    return null;
  }
  function regionFromCode(code, tier, cup) {
    if (!code) return 'other';
    const top = (COMP && COMP.europe_top) || [];
    const europe = (COMP && COMP.europe) || [];
    const sa = (COMP && COMP.south_america) || [];
    const asia = (COMP && COMP.asia) || [];
    if (code === 'cze' && !cup) return 'czech';
    if (top.indexOf(code) >= 0 && tier === 1 && !cup) return 'europe_top';
    if (europe.indexOf(code) >= 0) return 'europe_lower';
    if (sa.indexOf(code) >= 0) return 'south_america';
    if (asia.indexOf(code) >= 0) return 'asia';
    return 'other';
  }
  function espnTier(slug) {
    const parts = String(slug || '').split('.');
    if (parts.length === 2 && /^\d+$/.test(parts[1])) return +parts[1];
    return null;
  }
  function espnCountry(slug) {
    const prefix = String(slug || '').split('.')[0];
    const europe = (COMP && COMP.europe) || [];
    const sa = (COMP && COMP.south_america) || [];
    const asia = (COMP && COMP.asia) || [];
    if (europe.indexOf(prefix) >= 0 || sa.indexOf(prefix) >= 0 || asia.indexOf(prefix) >= 0) return prefix;
    if (codeOf(prefix) === prefix) return prefix;
    return null;
  }
  function intlEspn(slug) {
    slug = String(slug || '');
    const exact = (COMP && COMP.international_espn_exact) || [];
    if (exact.indexOf(slug) >= 0) return true;
    return ((COMP && COMP.international_espn) || []).some(prefix => slug.indexOf(prefix) === 0);
  }
  function continentOf(name) {
    if (!name || !COMP) return null;
    return (COMP.continent || {})[String(name).trim().toLowerCase()] || null;
  }
  function countryFromRaw(raw) {
    if (!raw || continentOf(raw)) return null;
    const direct = codeOf(raw);
    if (direct) return direct;
    const tokens = strip(raw).replace(/[^a-z0-9]+/g, ' ').split(' ').filter(Boolean);
    const qual = { amateur: 1, women: 1, woman: 1, youth: 1, reserve: 1, reserves: 1, university: 1, college: 1 };
    const trimmed = tokens.filter(tok => !qual[tok]);
    if (trimmed.length && trimmed.length < tokens.length) return codeOf(trimmed.join(' '));
    return null;
  }
  function classify(spec) {
    spec = spec || {};
    const slug = spec.slug || '';
    let country = spec.country_code || null;
    const raw = spec.country_name || '';
    if (!country && raw) country = countryFromRaw(raw);
    const tags = tagsOf(spec);
    let tier = null, cup = false, region = null;
    const cups = new Set((COMP && COMP.cups_espn) || []);
    if (spec.src === 'espn' || (slug && spec.competition_id == null && spec.tournament_id == null)) {
      tier = espnTier(slug);
      if (cups.has(slug)) { region = 'europe_cups'; cup = true; country = null; }
      else if (intlEspn(slug)) { region = 'international'; country = null; }
      else if (COMP && COMP.continental_espn && COMP.continental_espn[slug]) { region = COMP.continental_espn[slug]; cup = true; country = null; }
      else { country = espnCountry(slug) || country; region = regionFromCode(country, tier, false); }
    } else if (compHas('cups_s365', spec.competition_id) || compHas('cups_sofa', spec.tournament_id)) {
      region = 'europe_cups'; cup = true; country = null;
    } else if (COMP && COMP.continental_s365 && COMP.continental_s365[String(spec.competition_id)]) {
      region = COMP.continental_s365[String(spec.competition_id)]; cup = true; country = null;
    } else if (compHas('international_s365', spec.competition_id)) {
      region = 'international'; country = null;
    } else {
      const continent = continentOf(raw);
      if (continent) {
        region = continent; country = null;
        const low = String(raw).trim().toLowerCase();
        cup = low === 'africa' || low === 'north america' || low === 'south america' || low === 'asia';
      } else region = regionFromCode(country, tier, false);
    }
    if (!region) region = 'other';
    return {
      region, country, tier, tags, segment: segmentOf(tags), cup,
      neutral: region === 'europe_cups' || region === 'international',
      country_name: countryLabel(country, cup ? null : raw),
    };
  }
  function classifyStored(match) {
    const teams = (match && match.teams) || [];
    const spec = {
      home: (match && match.home_name) || (teams[0] && teams[0].name),
      away: (match && match.away_name) || (teams[1] && teams[1].name),
      tournament_id: match && match.ut,
      tournament_slug: match && match.ut_slug,
      country_code: match && match.country,
      country_name: match && match.country_raw,
      label: match && match.league_name,
    };
    const league = String((match && match.league) || '');
    if (league.indexOf('s365.') === 0) {
      spec.src = 's365';
      const tail = league.slice(5);
      spec.competition_id = /^\d+$/.test(tail) ? +tail : null;
      const mapped = spec.competition_id != null ? S365_COUNTRY[spec.competition_id] : null;
      if (mapped) spec.country_name = mapped;
    } else if (league.indexOf('sofa.') === 0) spec.src = 'sofa';
    else { spec.src = 'espn'; spec.slug = league; }
    if (spec.country_name) spec.country_code = null;
    return classify(spec);
  }
  function lowConfidence(m) {
    if (!m) return false;
    if (m.segment && m.segment !== 'main') return true;
    return !!(m.tags && m.tags.length);
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
  function countMarket(mass, ouLines) {
    const keys = Object.keys(mass).map(Number).sort((a, b) => a - b);
    if (!keys.length) {
      const ou = {};
      ouLines.forEach(line => { ou[line.toFixed(1)] = { over: 0, under: 1 }; });
      return { xg: 0, ou, mode: [0, 1], dist: [[0, 1]] };
    }
    let sum = 0, xg = 0, modeK = keys[0], modeP = -1;
    keys.forEach(k => {
      const p = mass[k];
      sum += p;
      xg += k * p;
      if (p > modeP || (p === modeP && k < modeK)) { modeP = p; modeK = k; }
    });
    sum = sum || 1;
    const ou = {};
    ouLines.forEach(line => {
      const need = line + 0.5;
      let over = 0;
      keys.forEach(k => { if (k >= need) over += mass[k]; });
      ou[line.toFixed(1)] = { over: over / sum, under: 1 - over / sum };
    });
    const dist = [];
    keys.forEach(k => { const p = mass[k] / sum; if (p >= 0.004) dist.push([k, p]); });
    return { xg: xg / sum, ou, mode: [modeK, modeP / sum], dist };
  }
  function marketsFrom(matrix, baseH, baseA) {
    let home = 0, draw = 0, away = 0, btts = 0;
    const overs = { '1.5': 0, '2.5': 0, '3.5': 0 };
    const homeC = {}, awayC = {}, totC = {};
    const exact = [];
    const n = matrix.length;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const p = matrix[i][j];
      const H = (baseH || 0) + i, A = (baseA || 0) + j;
      const goals = H + A;
      if (H > A) home += p; else if (H === A) draw += p; else away += p;
      if (goals >= 2) overs['1.5'] += p;
      if (goals >= 3) overs['2.5'] += p;
      if (goals >= 4) overs['3.5'] += p;
      if (H >= 1 && A >= 1) btts += p;
      homeC[H] = (homeC[H] || 0) + p;
      awayC[A] = (awayC[A] || 0) + p;
      totC[goals] = (totC[goals] || 0) + p;
      exact.push([H + '-' + A, p]);
    }
    const t = home + draw + away || 1;
    exact.sort((a, b) => b[1] - a[1]);
    const ou = {};
    ['1.5', '2.5', '3.5'].forEach(line => { ou[line] = { over: overs[line], under: 1 - overs[line] }; });
    const teams = {
      home: countMarket(homeC, [0.5, 1.5, 2.5]),
      away: countMarket(awayC, [0.5, 1.5, 2.5]),
    };
    const summed = countMarket(totC, [1.5, 2.5, 3.5]);
    const total = { xg: summed.xg, ou: summed.ou, mode: summed.mode, dist: summed.dist, lines: ou };
    return { p: [home / t, draw / t, away / t], over: overs['2.5'], under: 1 - overs['2.5'], ou, btts, exact: exact.slice(0, 5), teams, total };
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
    if (upd.minute != null && m.minute != null && upd.minute < m.minute) return false;
    if (upd.period != null && m.period != null && upd.period < m.period) return false;
    if (upd.reds && m.reds && (upd.reds[0] < m.reds[0] || upd.reds[1] < m.reds[1])) return false;
    const drop = (m.hg != null && uh != null && uh < m.hg) || (m.ag != null && ua != null && ua < m.ag);
    if (drop) {
      if (stale) return false;
      const sig = uh + '-' + ua;
      const src = (token && token.src) || '';
      const prev = m._var;
      const confirmed = !!(prev && prev.sig === sig && ((src && prev.src !== src) || prev.n >= 1));
      if (!confirmed) {
        m._var = { sig, src, n: prev && prev.sig === sig && prev.src === src ? prev.n + 1 : 1 };
        return false;
      }
      m._var = null;
    } else if (m._var && uh != null && ua != null && uh >= m.hg && ua >= m.ag) {
      m._var = null;
    }
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
      const tid = det.team && det.team.id != null && det.team.id !== '' ? String(det.team.id) : '';
      if (!tid) continue;
      const homeId = sides.home.team && sides.home.team.id != null ? String(sides.home.team.id) : '';
      const awayId = sides.away.team && sides.away.team.id != null ? String(sides.away.team.id) : '';
      if (tid === homeId) { reds[0]++; saw = true; }
      else if (tid === awayId) { reds[1]++; saw = true; }
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

  function sofaNum(raw) {
    if (raw == null || raw === '') return null;
    const n = +raw;
    return Number.isFinite(n) && n >= 0 ? n : null;
  }
  function sofaGoals(block) {
    if (!block) return null;
    return sofaNum(block.current);
  }
  function sofaRegulation(block) {
    if (!block) return null;
    return sofaNum(block.normaltime);
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
    const tourn = ev.tournament || {};
    const cat = tourn.category || {};
    const ut = tourn.uniqueTournament || {};
    const type = (ev.status && ev.status.type) || '';
    const desc = String((ev.status && ev.status.description) || '').toLowerCase();
    let status = 'upcoming';
    if (type === 'inprogress') status = 'live';
    else if (type === 'finished') status = 'finished';
    else if (type === 'postponed' || desc.includes('postpon')) status = 'postponed';
    else if (desc.includes('cancel')) status = 'cancelled';
    else if (desc.includes('abandon')) status = 'abandoned';
    const clock = sofaMinute(ev, nowSec);
    const row = {
      id: 'sofa:' + ev.id, src: 'sofascore', ssid: ev.id, ts: ev.startTimestamp,
      status, minute: status === 'live' || status === 'finished' ? clock.minute : null, period: clock.period,
      hg: sofaGoals(ev.homeScore), ag: sofaGoals(ev.awayScore),
      hg90: sofaRegulation(ev.homeScore), ag90: sofaRegulation(ev.awayScore),
      homeName: home, awayName: away, teams: [{ name: home }, { name: away }],
      league_name: tourn.name || '',
      league: tourn.id != null ? 'sofa.' + tourn.id : undefined,
      ut: ut.id, ut_slug: ut.slug, country_raw: cat.name,
    };
    return Object.assign(row, classify({
      src: 'sofa', tournament_id: ut.id, tournament_slug: ut.slug, country_name: cat.name, home, away, label: tourn.name || '',
    }));
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
  function parse365(g, ctx) {
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
    const comp = (ctx && ctx.comps && ctx.comps[g.competitionId]) || {};
    const raw = ctx && ctx.countries ? (ctx.countries[comp.countryId] || '') : '';
    const row = {
      id: 's365:' + g.id, src: 's365', ts: Math.floor(Date.parse(g.startTime) / 1000),
      status, minute, period, hg: goals(home), ag: goals(away),
      homeName: home.name, awayName: away.name, teams: [{ name: home.name }, { name: away.name }],
      league_name: g.competitionDisplayName || '',
      league: g.competitionId != null ? 's365.' + g.competitionId : undefined,
      country_raw: raw || undefined,
    };
    return Object.assign(row, classify({
      src: 's365', competition_id: g.competitionId, country_name: raw, home: home.name, away: away.name,
      label: g.competitionDisplayName || '',
    }));
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

  function idCanon(id) {
    const parts = String(id || '').split(':');
    if (parts[0] !== 'club' || parts.length < 3) return null;
    return { code: parts[1], key: canon(parts.slice(2).join(':')) };
  }
  function findTeam(teams, name, country) {
    const key = canon(name);
    const code = codeOf(country);
    const all = [];
    for (const t of teams || []) {
      const p = idCanon(t && t.id);
      if (!p || p.key !== key) continue;
      all.push(t);
    }
    let hits = code ? all.filter(t => idCanon(t.id).code === code) : all;
    if (!hits.length) hits = all;
    hits.sort((a, b) => (b.n || 0) - (a.n || 0));
    return hits[0] || null;
  }
  function mergeList(prev, payload) {
    const prevGen = (prev && prev.generated) || 0;
    const matches = (prev && prev.matches) || [];
    if (!payload || !(payload.generated > prevGen)) return { generated: prevGen, matches, changed: false };
    const byId = new Map();
    for (const m of matches) if (m && m.id) byId.set(m.id, m);
    const out = [];
    const seen = new Set();
    const keep = ['hg', 'ag', 'minute', 'period', 'status', 'reds', 'winner', 'live', 'pred', 'lam', 'rho', 'ou', 'btts', 'exact', '_accAt', '_lk', '_var'];
    for (const raw of payload.matches || []) {
      if (!raw || !raw.id) continue;
      seen.add(raw.id);
      const cur = byId.get(raw.id);
      if (!cur) { out.push(raw); continue; }
      const merged = Object.assign({}, cur, raw);
      if (cur._accAt || cur.status === 'live') {
        for (const k of keep) if (cur[k] != null) merged[k] = cur[k];
      }
      out.push(merged);
    }
    for (const m of matches) {
      if (m && m.id && !seen.has(m.id) && m.status === 'live') out.push(m);
    }
    return { generated: payload.generated, matches: out, changed: true };
  }
  function priorOf(region) { return REGION_BASE[region] || 1450; }
  function listVisible(m, ui) {
    if (!m || !ui) return false;
    const fav = ui.fav;
    const hasFav = !!(fav && (typeof fav.has === 'function' ? fav.has(m.id) : fav.indexOf(m.id) >= 0));
    if (ui.view === 'oblibene') return hasFav;
    if (ui.view !== 'zapasy') return false;
    const day = ui.day || 0;
    if (!(m.day === day || (day === 0 && m.status === 'live'))) return false;
    const special = lowConfidence(m);
    if (ui.reg === 'special') { if (!special) return false; }
    else if (special) return false;
    if (ui.reg === 'focus' && m.region !== 'europe_top' && m.region !== 'czech' && m.region !== 'europe_cups') return false;
    if (ui.reg && ui.reg !== 'all' && ui.reg !== 'focus' && ui.reg !== 'special' && m.region !== ui.reg) return false;
    if (ui.filt === 'live' && m.status !== 'live') return false;
    if (ui.filt === 'up' && m.status !== 'upcoming') return false;
    if (ui.filt === 'fin' && m.status !== 'finished') return false;
    if (ui.favOnly && !hasFav) return false;
    return true;
  }

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
    m.lam = lam; m.rho = 0;
    m.xg = [mk.teams.home.xg, mk.teams.away.xg];
    m.teams_goals = mk.teams;
    m.total_goals = mk.total;
    m.ou = { over: mk.over, under: mk.under, line: 2.5, lines: mk.ou };
    m.btts = mk.btts;
    m.exact = mk.exact.map(x => [x[0], +x[1].toFixed(4)]);
    m.pred_low = true;
    m.pred_note = (!h || !a || (h.n || 0) < 8 || (a.n || 0) < 8)
      ? 'Tým není v historii – odhad podle síly soutěže, nižší spolehlivost.'
      : 'Málo historie v soutěži – odhad z Elo a síly ligy, nižší spolehlivost.';
    m.elo = [Math.round(eloH), Math.round(eloA)];
    m.n = [h ? h.n : 0, a ? a.n : 0];
    return m;
  }

  function goalView(m) {
    if (!m) return null;
    const live = m.status === 'live' && m.live;
    const lines = (live && m.live.ouLines) || (m.ou && m.ou.lines) || (live && m.live.total && m.live.total.lines) || null;
    let over25 = null;
    if (lines && lines['2.5']) over25 = lines['2.5'].over;
    else if (live && m.live.ou != null) over25 = m.live.ou;
    else if (m.ou) over25 = m.ou.over;
    const btts = live ? m.live.btts : m.btts;
    const teams = (live && m.live.teams) || m.teams_goals || null;
    const total = (live && m.live.total) || m.total_goals || null;
    let xg = live && m.live.xg ? m.live.xg : (m.xg || m.lam || null);
    if (teams && teams.home && teams.away) xg = [teams.home.xg, teams.away.xg];
    const exact = (live && m.live.exact) || m.exact || null;
    return { xg, over25, btts, lines, exact, teams, total };
  }
  function goalText(m) {
    const view = goalView(m);
    if (!view || !view.xg) return null;
    const n = v => (Math.round(+v * 100) / 100).toFixed(2);
    const pc = v => v == null ? '–' : Math.round(+v * 100) + ' %';
    const side = (block, fallback) => {
      if (!block) return n(fallback);
      const ou = block.ou || {};
      const o = k => ou[k] ? pc(ou[k].over) : '–';
      const mode = block.mode ? block.mode[0] + ' (' + pc(block.mode[1]) + ')' : '–';
      return n(block.xg) + ' · nejč. ' + mode + ' · O0,5 ' + o('0.5') + ' · O1,5 ' + o('1.5') + ' · O2,5 ' + o('2.5');
    };
    const tot = view.total;
    let totalLine;
    if (tot) {
      const src = tot.lines || view.lines || {};
      const o = k => src[k] ? pc(src[k].over) : '–';
      const mode = tot.mode ? tot.mode[0] + ' (' + pc(tot.mode[1]) + ')' : '–';
      totalLine = n(tot.xg) + ' · nejč. ' + mode + ' · O1,5 ' + o('1.5') + ' · O2,5 ' + o('2.5') + ' · O3,5 ' + o('3.5');
    } else {
      totalLine = n((+view.xg[0]) + (+view.xg[1])) + ' · O2,5 ' + pc(view.over25);
    }
    return { home: side(view.teams && view.teams.home, view.xg[0]), away: side(view.teams && view.teams.away, view.xg[1]), total: totalLine };
  }

  function liveCalc(m) {
    if (m.status !== 'live' || !m.pred || !m.lam) { if (m.status !== 'live') m.live = m.live && m.status === 'finished' ? m.live : null; return false; }
    const key = liveKey(m);
    if (m.live && m._lk === key) return false;
    const rem = remaining(m.lam[0], m.lam[1], m.minute || 0, m.reds || [0, 0], [m.hg || 0, m.ag || 0], m.period || 1);
    const mk = liveMarkets(m.hg || 0, m.ag || 0, rem[0], rem[1]);
    m.live = {
      p: { h: mk.p[0], d: mk.p[1], a: mk.p[2] },
      ou: mk.over,
      ouLines: mk.ou,
      btts: mk.btts,
      exact: mk.exact,
      xg: [mk.teams.home.xg, mk.teams.away.xg],
      teams: mk.teams,
      total: mk.total,
      rem,
    };
    m._lk = key;
    return true;
  }

  return {
    setRules, setComp, set365Index, canon, codeOf, clubId, classify, classifyStored, lowConfidence,
    scoreMatrix, markets, liveMarkets, remaining, eloLambdas,
    goalView, goalText,
    applyLive, ensurePred, liveCalc, liveKey, findTeam, priorOf, listVisible, mergeList, sofaGoals, sofaRegulation,
    parseEspnEvent, parseSofaEvent, parseSofaIncidents, parseSofaOdds, parse365, orient, alignUpdate, espnMinute, sofaMinute,
  };
});
