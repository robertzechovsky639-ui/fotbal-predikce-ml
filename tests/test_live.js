const assert = require('assert');
const fs = require('fs');
const path = require('path');
const F = require('../web/live.js');
const rules = JSON.parse(fs.readFileSync(path.join(__dirname, '../web/names_rules.json'), 'utf8'));
F.setRules(rules);

assert.strictEqual(F.canon("Man United"), "manchester united");
assert.strictEqual(F.canon("Nott'm Forest"), "nottingham forest");
assert.strictEqual(F.canon("Bayern Munich"), "bayern munchen");
assert.strictEqual(F.canon("Sparta Prague"), "sparta praha");
assert.notStrictEqual(F.canon("Sparta Rotterdam"), F.canon("Sparta Prague"));

const mk = F.markets(1.4, 1.1, -0.05);
const sum = mk.p[0] + mk.p[1] + mk.p[2];
assert.ok(Math.abs(sum - 1) < 1e-9, 'poisson 1X2');
assert.ok(mk.ou['1.5'].over > mk.ou['2.5'].over && mk.ou['2.5'].over > mk.ou['3.5'].over, 'over klesá s linií');
assert.ok(Math.abs(mk.over - mk.ou['2.5'].over) < 1e-12);
assert.ok(mk.teams.home.ou['0.5'].over > mk.teams.home.ou['1.5'].over && mk.teams.home.ou['1.5'].over > mk.teams.home.ou['2.5'].over);
assert.ok(Math.abs(mk.teams.home.xg + mk.teams.away.xg - mk.total.xg) < 1e-9);
assert.ok(mk.total.dist.reduce((s, row) => s + row[1], 0) > 0.95);
assert.strictEqual(mk.teams.home.mode[0], mk.teams.home.dist.slice().sort((a, b) => b[1] - a[1])[0][0]);
['1.5', '2.5', '3.5'].forEach(line => assert.ok(Math.abs(mk.ou[line].over + mk.ou[line].under - 1) < 1e-9));
const liveEarly = F.liveMarkets(0, 0, ...F.remaining(1.5, 1.2, 12, [0, 0], [0, 0], 1));
const liveLate = F.liveMarkets(0, 0, ...F.remaining(1.5, 1.2, 82, [0, 0], [0, 0], 2));
assert.ok(liveEarly.ou['2.5'].over > liveLate.ou['2.5'].over, 'pozdě 0-0 snižuje over 2,5');
const already = F.liveMarkets(2, 0, 0.05, 0.05);
assert.ok(already.ou['1.5'].over > 0.99);
assert.ok(already.ou['2.5'].over < 0.2);

const early = F.remaining(1.5, 1.2, 30, [0, 0], [0, 0], 1);
const late = F.remaining(1.5, 1.2, 85, [0, 0], [0, 0], 2);
const noLate = 1.5 * (5 / 90);
assert.ok(late[0] > noLate, 'pozdní minuta zvedne očekávané góly');
const red = F.remaining(1.5, 1.2, 30, [1, 0], [0, 0], 1);
assert.ok(red[0] < early[0], 'červená sníží lambdu');

let m = { status: 'upcoming', hg: null, ag: null, minute: null, period: 1 };
assert.strictEqual(F.applyLive(m, { status: 'live', hg: 0, ag: 0, minute: 1 }), true);
assert.strictEqual(m.hg, 0);
assert.strictEqual(F.applyLive(m, { status: 'live', hg: 1, ag: 0, minute: 20 }), true);
assert.strictEqual(F.applyLive(m, { status: 'live', hg: 0, ag: 0, minute: 21 }), false);
assert.strictEqual(m.hg, 1);
assert.strictEqual(F.applyLive(m, { status: 'finished', hg: 2, ag: 0 }), true);
assert.strictEqual(F.applyLive(m, { status: 'live', hg: 2, ag: 1 }), false);
assert.strictEqual(m.status, 'finished');

let p = { status: 'live', hg: 1, ag: 0 };
assert.strictEqual(F.applyLive(p, { status: 'postponed', hg: 1, ag: 0 }), false);
assert.strictEqual(p.status, 'live');

const fresh = { teams: [{ name: 'Neznamy Klub' }, { name: 'Jiny Klub' }], region: 'asia', country: 'kor' };
F.ensurePred(fresh, { teams: [], elo_params: { ha: 70, coef: 0.55, base_h: 1.48, base_a: 1.18 } });
assert.ok(fresh.pred && fresh.pred.h > 0);
assert.strictEqual(fresh.pred_low, true);
const keep = fresh.pred.h;
F.ensurePred(fresh, { teams: [{ id: 'club:kor:neznamy klub', name: 'X', elo: 1400, n: 30 }] });
assert.strictEqual(fresh.pred.h, keep);

const fx = name => JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

const espn = F.parseEspnEvent(fx('espn_finished.json'));
assert.strictEqual(espn.homeName, 'AFC Bournemouth');
assert.strictEqual(espn.awayName, 'Sunderland');
assert.strictEqual(espn.hg, 2);
assert.strictEqual(espn.ag, 0);
assert.strictEqual(espn.status, 'finished');
assert.strictEqual(espn.minute, 97);
assert.strictEqual(espn.period, 2);
assert.deepStrictEqual(espn.reds, [0, 1]);

const sofa2 = fx('sofa_2nd.json');
const s2 = F.parseSofaEvent(sofa2, sofa2.time.currentPeriodStartTimestamp + 120);
assert.strictEqual(s2.status, 'live');
assert.strictEqual(s2.period, 2);
assert.strictEqual(s2.minute, 47);
assert.strictEqual(s2.hg, 1);
assert.strictEqual(s2.ag, 2);
const capped = F.sofaMinute(sofa2, sofa2.time.currentPeriodStartTimestamp + 99999);
assert.strictEqual(capped.minute, 99);
const sofaLive = F.parseSofaEvent(Object.assign({}, fx('sofa_1st.json'), { homeScore: { current: 1, normaltime: 0 }, awayScore: { current: 0, normaltime: 0 } }), fx('sofa_1st.json').time.currentPeriodStartTimestamp + 90);
assert.strictEqual(sofaLive.hg, 1, 'živě bere current, ne zpožděné normaltime');
assert.strictEqual(sofaLive.minute, 1);

const odds = F.parseSofaOdds(fx('sofa_odds.json'));
assert.ok(odds.h > 1 && odds.d > 1 && odds.a > 1);
assert.ok(odds.a > odds.h);
assert.deepStrictEqual(F.parseSofaIncidents(fx('sofa_incidents.json')), [0, 0]);
assert.deepStrictEqual(F.parseSofaIncidents({ incidents: [{ incidentType: 'card', incidentClass: 'red', isHome: false }, { incidentType: 'card', incidentClass: 'yellowRed', isHome: true }] }), [1, 1]);

const live365 = F.parse365(fx('s365_live.json'));
assert.strictEqual(live365.status, 'live');
assert.strictEqual(live365.minute, 98);
assert.strictEqual(live365.period, 2);
assert.strictEqual(live365.hg, 0);
assert.strictEqual(live365.ag, 1);
const post = F.parse365(fx('s365_postponed.json'));
assert.strictEqual(post.status, 'postponed');
assert.notStrictEqual(post.status, 'finished');
const sched = F.parse365(fx('s365_scheduled.json'));
assert.strictEqual(sched.status, 'upcoming');
assert.strictEqual(sched.hg, null);
assert.strictEqual(sched.ag, null);
const flipped = F.parse365(Object.assign({}, fx('s365_live.json'), { isHomeAwayInverted: true }));
assert.strictEqual(flipped.homeName, 'Qadisiya Kuwait');
assert.strictEqual(flipped.hg, 1);
assert.strictEqual(flipped.ag, 0);

const sw = fs.readFileSync(path.join(__dirname, '../web/sw.js'), 'utf8');
assert.ok(sw.includes('fotbal-__GIT_SHA__'), 'verze cache ze SHA');
assert.ok(sw.includes('3000') && sw.includes('caches.match'), 'síť max 3 s, pak cache');
const js = fs.readFileSync(path.join(__dirname, '../web/static.js'), 'utf8');
assert.ok(!/const ymd = ymd\(/.test(js), 'ESPN datum nesmí stínit funkci ymd');
assert.ok(js.includes('sofascore: 20000') && js.includes('sofascore: 30000'), 'celý Sofascore feed nejvýš 15–30 s');
assert.ok(!/sofascore:\s*1500/.test(js) && !/sofascore:\s*2200/.test(js));
assert.ok(js.includes('7 * 60 * 1000'), 'matches.json každých 7 min');
assert.ok(js.includes('/event/'), 'detail zobrazených zápasů');
const ui = { view: 'zapasy', day: 0, reg: 'focus', filt: 'live', favOnly: false, fav: [] };
assert.strictEqual(F.listVisible({ id: 'sofa:9', region: 'asia', status: 'live', day: 0 }, ui), false);
assert.strictEqual(F.listVisible({ id: 'espn:2', region: 'europe_cups', status: 'live', day: 0 }, ui), true);
assert.strictEqual(F.listVisible({ id: 'espn:3', region: 'europe_cups', status: 'finished', day: 0 }, ui), false);

const held = { status: 'live', hg: 1, ag: 0, minute: 60, period: 2, reds: [0, 0], pred: { h: 0.55, d: 0.25, a: 0.2 }, lam: [1.4, 1.1], teams: [{ name: 'Arsenal' }, { name: 'Chelsea' }] };
F.liveCalc(held);
const heldP = held.live.p.h;
assert.strictEqual(F.applyLive(held, { status: 'live', hg: 0, ag: 0, minute: 20, period: 1 }), false);
assert.strictEqual(held.hg, 1);
assert.strictEqual(held.minute, 60);
assert.strictEqual(held.live.p.h, heldP);
let gen = 2;
assert.strictEqual(F.applyLive(held, { status: 'live', hg: 1, ag: 0, minute: 60 }, { src: 'sofascore', gen: 1, t0: 1 }, t => t.gen === gen), false);
assert.strictEqual(held.live.p.h, heldP);
assert.strictEqual(F.applyLive(held, { status: 'upcoming', hg: null, ag: null, minute: null }), false);
assert.strictEqual(F.applyLive(held, { status: 'postponed', hg: 1, ag: 0, minute: 60 }), false);
assert.strictEqual(held.status, 'live');
assert.strictEqual(F.applyLive(held, { status: 'live', hg: 1, ag: 0, minute: 70, period: 2 }), true);
assert.strictEqual(held.minute, 70);
assert.notStrictEqual(held.live.p.h, heldP);
const after = held.live.p.h;
assert.strictEqual(F.applyLive(held, { status: 'finished', hg: 1, ag: 0, minute: 97 }), true);
assert.strictEqual(F.applyLive(held, { status: 'live', hg: 2, ag: 0, minute: 98 }), false);
assert.strictEqual(held.status, 'finished');
assert.strictEqual(held.live.p.h, after);

const blank = { status: 'upcoming', hg: null, ag: null, minute: null, teams: [{ name: 'A' }, { name: 'B' }] };
assert.strictEqual(F.applyLive(blank, { status: 'live', hg: 0, ag: 0, minute: 1 }), true);
assert.strictEqual(blank.hg, 0);

const stored = { status: 'live', hg: 1, ag: 0, minute: 30, period: 1, teams: [{ name: 'Arsenal' }, { name: 'Chelsea' }], pred: { h: 0.6, d: 0.2, a: 0.2 }, lam: [1.5, 1.0], reds: [0, 0] };
F.liveCalc(stored);
const partial = { homeName: 'Chelsea', awayName: 'Arsenal', teams: [{ name: 'Chelsea' }, { name: 'Arsenal' }], status: 'live', hg: 0, ag: 2, minute: 40, period: 1 };
const aligned = F.alignUpdate(stored, partial);
assert.strictEqual(aligned.hg, 2);
assert.strictEqual(aligned.ag, 0);
assert.strictEqual(F.applyLive(stored, aligned), true);
assert.strictEqual(stored.hg, 2);
assert.strictEqual(stored.ag, 0);

const zw = F.findTeam([
  { id: 'club:ned:zwolle', name: 'Zwolle', n: 511, elo: 1600 },
  { id: 'club:ned:pec zwolle', name: 'PEC Zwolle', n: 1, elo: 1400 },
], 'PEC Zwolle', 'Netherlands');
assert.strictEqual(zw.id, 'club:ned:zwolle');
const hv = F.findTeam([
  { id: 'club:fra:le havre', n: 1227, elo: 1550 },
  { id: 'club:fra:havre', n: 1, elo: 1300 },
], 'Havre AC', 'France');
assert.strictEqual(hv.id, 'club:fra:le havre');

const varM = { status: 'live', hg: 2, ag: 0, minute: 50, period: 2, reds: [0, 0], pred: { h: 0.5, d: 0.3, a: 0.2 }, lam: [1.2, 1.0] };
assert.strictEqual(F.applyLive(varM, { status: 'live', hg: 1, ag: 0, minute: 51 }, { src: 'espn', t0: 1 }, () => true), false);
assert.strictEqual(varM.hg, 2);
assert.strictEqual(F.applyLive(varM, { status: 'live', hg: 1, ag: 0, minute: 52 }, { src: 'sofascore', t0: 2 }, () => true), true);
assert.strictEqual(varM.hg, 1);
const var2 = { status: 'live', hg: 2, ag: 0, minute: 40, period: 2, reds: [0, 0], pred: { h: 0.5, d: 0.3, a: 0.2 }, lam: [1.2, 1.0] };
const down = { status: 'live', hg: 1, ag: 0, minute: 41 };
assert.strictEqual(F.applyLive(var2, down, { src: 'espn', t0: 3 }, () => true), false);
assert.strictEqual(F.applyLive(var2, { status: 'live', hg: 2, ag: 0, minute: 42 }, { src: 'espn', t0: 4 }, () => true), true);
assert.strictEqual(var2.hg, 2);
assert.strictEqual(F.applyLive(var2, { status: 'live', hg: 1, ag: 0, minute: 43 }, { src: 'espn', t0: 5 }, () => true), false);
assert.strictEqual(F.applyLive(var2, { status: 'live', hg: 1, ag: 0, minute: 44 }, { src: 'espn', t0: 6 }, () => true), true);
assert.strictEqual(var2.hg, 1);

const finEt = F.parseSofaEvent({
  id: 9, homeTeam: { name: 'A' }, awayTeam: { name: 'B' },
  status: { type: 'finished', description: 'AET' },
  homeScore: { current: 2, normaltime: 1 }, awayScore: { current: 1, normaltime: 1 }, time: {},
});
assert.strictEqual(finEt.hg, 2);
assert.strictEqual(finEt.hg90, 1);
assert.strictEqual(finEt.ag90, 1);

const noTeam = F.parseEspnEvent({
  id: 3, date: '2026-10-18T15:00:00Z',
  competitions: [{
    status: { type: { state: 'in', name: 'STATUS_IN_PROGRESS' }, displayClock: "20'", period: 1 },
    competitors: [
      { homeAway: 'home', score: '1', team: { id: '10', displayName: 'Home FC' } },
      { homeAway: 'away', score: '0', team: { id: '20', displayName: 'Away FC' } },
    ],
    details: [{ redCard: true, team: {} }, { redCard: true, team: { id: '10' } }],
  }],
});
assert.deepStrictEqual(noTeam.reds, [1, 0]);

const older = { generated: 10, matches: [{ id: 'a', status: 'live', hg: 2, ag: 0, minute: 60, _accAt: 5, pred: { h: 0.7, d: 0.2, a: 0.1 } }] };
assert.strictEqual(F.mergeList(older, { generated: 9, matches: [{ id: 'a', status: 'live', hg: 0, ag: 0 }] }).changed, false);
const newer = F.mergeList(older, { generated: 20, matches: [{ id: 'a', status: 'upcoming', hg: 0, ag: 0, minute: 0, pred: { h: 0.4, d: 0.3, a: 0.3 } }, { id: 'b', status: 'upcoming', hg: null }] });
assert.strictEqual(newer.changed, true);
assert.strictEqual(newer.matches.find(m => m.id === 'a').hg, 2);
assert.strictEqual(newer.matches.find(m => m.id === 'a').pred.h, 0.7);
assert.ok(newer.matches.some(m => m.id === 'b'));
const kept = F.mergeList(older, { generated: 30, matches: [] });
assert.strictEqual(kept.matches.length, 1);
assert.strictEqual(kept.matches[0].id, 'a');

const goalM = {
  status: 'live', hg: 0, ag: 0, minute: 15, period: 1, reds: [0, 0],
  pred: { h: 0.45, d: 0.28, a: 0.27 }, lam: [1.5, 1.15], teams: [{ name: 'Sparta' }, { name: 'Slavia' }],
};
F.liveCalc(goalM);
const ouBefore = goalM.live.ouLines['2.5'].over;
const xgBefore = goalM.live.xg[0] + goalM.live.xg[1];
const homeBefore = goalM.live.teams.home.xg;
assert.ok(xgBefore > 0.5 && xgBefore < 3, 'živě xG je očekávaný konečný součet');
assert.ok(goalM.live.teams.home.ou['0.5'].over > goalM.live.teams.home.ou['2.5'].over);
assert.ok(goalM.live.total.dist.length >= 3);
assert.strictEqual(F.applyLive(goalM, { status: 'live', hg: 0, ag: 0, minute: 10 }, { src: 'espn', t0: 1 }, () => false), false);
assert.strictEqual(goalM.live.ouLines['2.5'].over, ouBefore, 'starší minuta nevrátí over');
assert.strictEqual(goalM.live.teams.home.xg, homeBefore, 'starší minuta nevrátí góly týmu');
assert.strictEqual(F.applyLive(goalM, { status: 'live', hg: 0, ag: 0, minute: 80, period: 2 }, { src: 'espn', t0: 2 }, () => true), true);
assert.ok(goalM.live.ouLines['2.5'].over < ouBefore, 'čerstvá pozdní minuta smí over snížit');
assert.ok(goalM.live.xg[0] + goalM.live.xg[1] < xgBefore);
assert.ok(goalM.live.teams.home.xg < homeBefore);
const label = F.goalText(goalM);
assert.ok(label.home.includes('nejč.') && label.home.includes('O0,5') && label.home.includes('O2,5'));
assert.ok(label.away.includes('O1,5'));
assert.ok(label.total.includes('O1,5') && label.total.includes('O2,5') && label.total.includes('O3,5'));
const redM = { status: 'live', hg: 0, ag: 0, minute: 30, period: 1, reds: [1, 0], pred: { h: 0.4, d: 0.3, a: 0.3 }, lam: [1.5, 1.2] };
const openM = { status: 'live', hg: 0, ag: 0, minute: 30, period: 1, reds: [0, 0], pred: { h: 0.4, d: 0.3, a: 0.3 }, lam: [1.5, 1.2] };
F.liveCalc(redM); F.liveCalc(openM);
assert.ok(redM.live.teams.home.xg < openM.live.teams.home.xg, 'červená sníží očekávané góly týmu');
assert.ok(redM.live.teams.away.xg > openM.live.teams.away.xg);
const two = { status: 'live', hg: 2, ag: 0, minute: 70, period: 2, reds: [0, 0], pred: { h: 0.5, d: 0.3, a: 0.2 }, lam: [1.4, 1.1] };
F.liveCalc(two);
assert.ok(two.live.teams.home.ou['0.5'].over > 0.99 && two.live.teams.home.ou['1.5'].over > 0.99);
assert.ok(two.live.teams.home.mode[0] >= 2);
assert.ok(two.live.total.xg > 2);
const pre = { status: 'upcoming', teams: [{ name: 'A' }, { name: 'B' }], region: 'czech', country: 'cze' };
F.ensurePred(pre, { teams: [], elo_params: { ha: 50, coef: 0.75, base_h: 1.48, base_a: 1.18 } });
assert.ok(pre.ou.lines['1.5'].over > pre.ou.lines['3.5'].over);
assert.ok(pre.teams_goals.home.ou['0.5'].over > pre.teams_goals.home.ou['2.5'].over);
assert.ok(pre.total_goals.dist.length >= 3 && pre.xg[0] > 0);
assert.ok(F.goalText(pre).home.includes('O0,5') && F.goalText(pre).total.includes('nejč.'));
const learn = fs.readFileSync(path.join(__dirname, '../.github/workflows/learn.yml'), 'utf8');
assert.ok(learn.includes('goals_h.txt') && learn.includes('goals_meta.json'));
const sw2 = fs.readFileSync(path.join(__dirname, '../web/sw.js'), 'utf8');
assert.ok(sw2.includes('fotbal-__GIT_SHA__') && !/fotbal-[0-9a-f]{7,}/.test(sw2.replace('__GIT_SHA__', '')));

const comp = JSON.parse(fs.readFileSync(path.join(__dirname, '../web/comp_rules.json'), 'utf8'));
F.setComp(comp);
assert.strictEqual(F.classify({ src: 'sofa', country_name: 'England Amateur', label: 'Isthmian League, Division One North', home: 'Bowers & Pitsea', away: 'Redbridge' }).region, 'europe_lower');
assert.strictEqual(F.classify({ src: 'sofa', country_name: 'Brazil Amateur', home: 'Salto FC U12', away: 'X U12' }).segment, 'youth');
assert.strictEqual(F.classify({ src: 's365', competition_id: 5566, country_name: 'USA', label: 'NWSL' }).segment, 'women');
assert.strictEqual(F.classify({ src: 'sofa', country_name: 'USA', label: 'NCAA III, Upper Midwest Athletic Conference', home: 'Crown Polars', away: 'Martin Luther Knights' }).segment, 'college');
const prom = F.classify({ src: 's365', competition_id: 8124, country_name: 'Panama', home: 'Herrera II', away: 'CD Universitario II' });
assert.strictEqual(prom.region, 'other');
assert.strictEqual(prom.country, 'pan');
assert.strictEqual(prom.segment, 'reserve');
assert.strictEqual(prom.cup, false);
assert.ok(prom.tags.indexOf('reserve') >= 0);
const ncaa = F.classify({ src: 'sofa', tournament_id: 36031, tournament_slug: 'ncaa-division-iii', country_name: 'USA', home: 'Augsburg', away: 'Bethany Lutheran' });
assert.strictEqual(ncaa.region, 'other');
assert.strictEqual(ncaa.country, 'usa');
assert.strictEqual(ncaa.segment, 'college');
assert.notStrictEqual(ncaa.region, 'europe_cups');
assert.strictEqual(F.classify({ src: 's365', competition_id: 573, country_name: 'Belgium', home: 'Club Brugge', away: 'Sporting' }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 's365', competition_id: 7685, country_name: 'Europe' }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 'espn', slug: 'uefa.europa' }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 'espn', slug: 'uefa.europa.conf' }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 'espn', slug: 'uefa.super_cup' }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 'espn', slug: 'uefa.euro' }).region, 'international');
assert.strictEqual(F.classify({ src: 'espn', slug: 'uefa.nations' }).region, 'international');
assert.notStrictEqual(F.classify({ src: 'espn', slug: 'uefa.europa' }).region, 'international');
const crc = F.classify({ src: 'espn', slug: 'crc.1' });
assert.strictEqual(crc.region, 'other');
assert.strictEqual(crc.country, 'crc');
assert.strictEqual(crc.tier, 1);
assert.strictEqual(F.classify({ src: 'espn', slug: 'eng.1' }).region, 'europe_top');
assert.strictEqual(F.classify({ src: 'espn', slug: 'eng.1' }).tier, 1);
assert.strictEqual(F.classify({ src: 'espn', slug: 'eng.2' }).region, 'europe_lower');
assert.strictEqual(F.classify({ src: 'espn', slug: 'eng.2' }).tier, 2);
assert.strictEqual(F.classify({ src: 'espn', slug: 'cze.1' }).region, 'czech');
assert.strictEqual(F.classify({ src: 'espn', slug: 'bel.1' }).region, 'europe_lower');
assert.strictEqual(F.classify({ src: 'espn', slug: 'usa.usl.1' }).tier, null);
assert.strictEqual(F.classify({ src: 's365', competition_id: 999999 }).region, 'other');
assert.notStrictEqual(F.classify({ src: 's365', competition_id: 999999 }).region, 'europe_cups');
assert.strictEqual(F.classify({ src: 's365', competition_id: 1, country_name: 'Algeria' }).region, 'other');
assert.strictEqual(F.classify({ src: 's365', competition_id: 1, country_name: 'Egypt' }).country, 'egy');
const promStored = F.classifyStored({ league: 's365.8124', region: 'europe_cups', country: null, country_raw: 'Panama', teams: [{ name: 'Herrera II' }, { name: 'CD Universitario II' }], league_name: 'Liga Prom - Apertura - Western Conference - North Zone' });
assert.strictEqual(promStored.region, 'other');
assert.strictEqual(promStored.segment, 'reserve');
assert.strictEqual(promStored.country, 'pan');
const sofaNcaa = F.parseSofaEvent({
  id: 1, startTimestamp: 1, status: { type: 'inprogress', description: '1st half' },
  homeTeam: { name: 'Augsburg' }, awayTeam: { name: 'Bethany Lutheran' },
  homeScore: { current: 0 }, awayScore: { current: 0 },
  time: { currentPeriodStartTimestamp: 10, initial: 0, max: 2700 },
  tournament: { id: 192723, name: 'NCAA III, Upper Midwest Athletic Conference', category: { name: 'USA', id: 26 }, uniqueTournament: { id: 36031, slug: 'ncaa-division-iii' } },
}, 70);
assert.strictEqual(sofaNcaa.region, 'other');
assert.strictEqual(sofaNcaa.segment, 'college');
assert.notStrictEqual(sofaNcaa.region, 'europe_cups');
F.set365Index([{ id: 8124, countryId: 146 }], [{ id: 146, name: 'Panama' }]);
const fromIndex = F.classifyStored({ league: 's365.8124', region: 'europe_cups', country: 'per', teams: [{ name: 'Herrera II' }, { name: 'CD Universitario II' }] });
assert.strictEqual(fromIndex.country, 'pan');
assert.strictEqual(fromIndex.region, 'other');
const live365ctx = F.parse365(Object.assign({}, fx('s365_live.json'), { competitionId: 8135 }), { comps: { 8135: { id: 8135, countryId: 19 } }, countries: { 19: 'Asia' } });
assert.strictEqual(live365ctx.region, 'asia');
assert.strictEqual(live365ctx.cup, true);
const uiCup = { view: 'zapasy', day: 0, reg: 'europe_cups', filt: 'live', favOnly: false, fav: [] };
assert.strictEqual(F.listVisible({ id: 's365:1', region: 'other', country: 'pan', segment: 'reserve', tags: ['reserve'], status: 'live', day: 0 }, uiCup), false);
assert.strictEqual(F.listVisible({ id: 'sofa:2', region: 'other', country: 'usa', segment: 'college', tags: ['college'], status: 'live', day: 0 }, uiCup), false);
assert.strictEqual(F.listVisible({ id: 'sofa:2', region: 'other', segment: 'college', tags: ['college'], status: 'live', day: 0 }, { view: 'zapasy', day: 0, reg: 'all', filt: 'live', favOnly: false, fav: [] }), false);
assert.strictEqual(F.listVisible({ id: 'sofa:2', region: 'other', segment: 'college', tags: ['college'], status: 'live', day: 0 }, { view: 'zapasy', day: 0, reg: 'focus', filt: 'live', favOnly: false, fav: [] }), false);
assert.strictEqual(F.listVisible({ id: 'sofa:2', region: 'other', segment: 'college', tags: ['college'], status: 'live', day: 0 }, { view: 'zapasy', day: 0, reg: 'special', filt: 'live', favOnly: false, fav: [] }), true);
assert.strictEqual(F.listVisible({ id: 'espn:2', region: 'europe_cups', status: 'live', day: 0 }, uiCup), true);
assert.strictEqual(F.listVisible({ id: 'sofa:2', region: 'other', segment: 'college', status: 'live', day: 0 }, { view: 'oblibene', day: 0, reg: 'focus', filt: 'all', favOnly: false, fav: ['sofa:2'] }), true);
assert.ok(sw.includes('comp_rules.json'));
assert.ok(js.includes('comp_rules.json') && js.includes('setComp'));
assert.ok(!js.includes("m.region = m.region || 'europe_lower'"));
assert.ok(!js.includes('function women'));

assert.strictEqual(F.canon('N.E.C. Nijmegen'), 'nijmegen');
assert.strictEqual(F.canon('F.C. København'), 'copenhagen');
assert.strictEqual(F.canon('Union St.-Gilloise'), 'st gilloise');
assert.strictEqual(F.canon('Peterborough United'), 'peterboro');
assert.strictEqual(F.canon('Bristol Rovers'), 'bristol rvs');
assert.strictEqual(F.canon('Athletic Club'), 'athletic bilbao');
assert.strictEqual(F.canon('Charlton Athletic'), 'charlton athletic');
assert.strictEqual(F.canon('Chivas'), 'guadalajara chivas');
assert.strictEqual(F.canon('Guadalajara'), 'guadalajara chivas');
assert.strictEqual(F.canon('Deportivo Guadalajara'), 'deportivo guadalajara');
assert.strictEqual(F.canon('MK Dons'), 'milton keynes dons');
assert.strictEqual(F.canon('Atlético-MG'), 'atletico mg');
assert.strictEqual(F.canon('Atlético Mineiro'), 'atletico mg');
assert.strictEqual(F.canon('U. La Calera'), 'union la calera');
assert.strictEqual(F.canon('Central Córdoba SdE'), 'central cordoba sde');
assert.strictEqual(F.canon('Central Córdoba (Santiago del Estero)'), 'central cordoba sde');
assert.strictEqual(F.classify({ src: 's365', country_name: 'Mexico', home: 'Guadalajara Chivas (W)', away: 'Necaxa (W)', label: 'Liga MX' }).segment, 'women');
assert.strictEqual(F.classify({ src: 's365', country_name: 'Trinidad and Tobago', home: 'W Connection', away: 'Defence Force' }).segment, 'main');
const elo = [
  { id: 'club:eng:manchester united', n: 1373, elo: 1800 },
  { id: 'club:eng:manchester city', n: 1454, elo: 1850 },
  { id: 'club:eng:mansfield', n: 1507, elo: 1500 },
  { id: 'club:eng:bradford', n: 1503, elo: 1490 },
  { id: 'club:eng:peterboro', n: 1517, elo: 1480 },
  { id: 'club:den:copenhagen', n: 481, elo: 1600 },
  { id: 'club:ned:nijmegen', n: 929, elo: 1550 },
];
assert.strictEqual(F.findTeam(elo, 'Mansfield Town', 'England').id, 'club:eng:mansfield');
assert.strictEqual(F.findTeam(elo, 'Bradford City', 'England').id, 'club:eng:bradford');
assert.strictEqual(F.findTeam(elo, 'Peterborough United', 'England').id, 'club:eng:peterboro');
assert.strictEqual(F.findTeam(elo, 'Manchester United', 'England').id, 'club:eng:manchester united');
assert.strictEqual(F.findTeam(elo, 'Manchester City', 'England').id, 'club:eng:manchester city');
assert.strictEqual(F.findTeam(elo, 'F.C. København', 'Denmark').id, 'club:den:copenhagen');
assert.strictEqual(F.findTeam(elo, 'N.E.C. Nijmegen', 'Netherlands').id, 'club:ned:nijmegen');
assert.strictEqual(F.canon('D.C. United'), 'dc united');
assert.strictEqual(F.canon('Mansfield Town'), 'mansfield');
const mexican = [
  { id: 'club:bra:santos', n: 839, elo: 1700 },
  { id: 'club:mex:santos laguna', n: 877, elo: 1600 },
  { id: 'club:ned:zwolle', n: 511, elo: 1550 },
];
assert.strictEqual(F.findTeam(mexican, 'Santos', 'Mexico').id, 'club:mex:santos laguna');
assert.strictEqual(F.findTeam(mexican, 'Santos Laguna', 'Mexico').id, 'club:mex:santos laguna');
assert.strictEqual(F.findTeam(mexican, 'Santos', 'Brazil').id, 'club:bra:santos');
assert.strictEqual(F.findTeam(mexican, 'Zwolle', 'Belgium').id, 'club:ned:zwolle');
const santos = { id: 'espn', ts: 5, status: 'upcoming', pred_low: true, n: [839, 597], teams: [{ name: 'Santos' }, { name: 'Pumas UNAM' }] };
const laguna = { id: 's365', ts: 5, status: 'upcoming', pred_low: false, n: [877, 597], pred: { h: 0.4, d: 0.3, a: 0.3 }, teams: [{ name: 'Santos Laguna' }, { name: 'Pumas UNAM' }] };
const oneFixture = F.dedupeMatches([santos, laguna]);
assert.strictEqual(oneFixture.length, 1);
assert.strictEqual(oneFixture[0].pred_low, false);
assert.strictEqual(F.dedupeMatches([
  { id: 'c', ts: 5, teams: [{ name: 'Manchester City' }, { name: 'Chelsea' }] },
  { id: 'u', ts: 5, teams: [{ name: 'Manchester United' }, { name: 'Chelsea' }] },
]).length, 2);

let ft = { status: 'live', hg: 1, ag: 0, minute: 94, period: 2, ht: false, pred: { h: 0.5, d: 0.3, a: 0.2 }, lam: [1.2, 0.8] };
assert.strictEqual(F.applyLive(ft, { status: 'finished', hg: 1, ag: 0, minute: 90, period: 2 }), true);
assert.strictEqual(ft.status, 'finished');
assert.strictEqual(ft.minute, 94);
assert.strictEqual(ft.ht, false);
let half = { status: 'live', hg: 0, ag: 0, minute: 47, period: 1, pred: { h: 0.4, d: 0.3, a: 0.3 }, lam: [1.1, 0.9] };
assert.strictEqual(F.applyLive(half, { status: 'live', hg: 0, ag: 0, minute: 45, period: 1, ht: true }), true);
assert.strictEqual(half.minute, 47);
assert.strictEqual(half.ht, true);
assert.strictEqual(half.period, 1);
assert.strictEqual(F.clockText(half), 'HT');
const etRem = F.remaining(1.5, 1.2, 100, [0, 0], [0, 0], 3);
const regRem = F.remaining(1.5, 1.2, 100, [0, 0], [0, 0], 2);
assert.ok(etRem[0] > regRem[0], 'prodloužení má zbývající čas');
assert.ok(F.remaining(1.5, 1.2, 120, [0, 0], [0, 0], 5)[0] < 0.01);
const sofaEt = F.sofaMinute({ status: { type: 'inprogress', description: 'Extra time' }, time: { initial: 5400, currentPeriodStartTimestamp: 1000 } }, 1180);
assert.strictEqual(sofaEt.period, 3);
assert.strictEqual(sofaEt.minute, 93);
assert.strictEqual(F.sofaMinute({ status: { description: 'Halftime' }, time: {} }, 0).ht, true);
const pending = F.parse365({
  id: 9, statusText: 'Pending', statusGroup: 3, gameTime: 12,
  homeCompetitor: { name: 'A', score: 0 }, awayCompetitor: { name: 'B', score: 0 },
  startTime: '2026-10-20T18:00:00Z', competitionDisplayName: 'Liga',
});
assert.strictEqual(pending.status, 'live');
assert.strictEqual(pending.period, 1);
const pens = F.parse365({
  id: 10, statusText: 'Penalties', statusGroup: 3, gameTime: 120,
  homeCompetitor: { name: 'A', score: 1 }, awayCompetitor: { name: 'B', score: 1 },
  startTime: '2026-10-20T18:00:00Z',
});
assert.strictEqual(pens.status, 'live');
assert.strictEqual(pens.period, 5);
assert.strictEqual(F.clockText({ status: 'live', minute: 120, period: 5 }), 'PEN');
assert.strictEqual(F.clockText({ status: 'live', minute: 100, period: 3 }), "100' ET");
const espnHt = F.parseEspnEvent({
  id: '77', date: '2026-10-20T18:00:00Z',
  competitions: [{
    status: { type: { name: 'STATUS_HALFTIME', state: 'in' }, displayClock: '45:00', period: 1 },
    competitors: [
      { homeAway: 'home', score: '1', team: { id: '1', displayName: 'A' } },
      { homeAway: 'away', score: '0', team: { id: '2', displayName: 'B' } },
    ],
  }],
});
assert.strictEqual(espnHt.status, 'live');
assert.strictEqual(espnHt.ht, true);
assert.strictEqual(espnHt.minute, null);
const day0 = F.pragueCalendar(0, Date.UTC(2026, 9, 20, 22, 30));
const day1 = F.pragueCalendar(1, Date.UTC(2026, 9, 20, 22, 30));
assert.strictEqual(day0.y, 2026);
assert.strictEqual(day0.m, 10);
assert.strictEqual(day0.d, 21);
assert.strictEqual(day1.d, 22);
assert.strictEqual(day1.w, (day0.w + 1) % 7);
const gilloise = { id: 'sofa:1', ts: 1000, status: 'live', minute: 20, hg: 1, ag: 0, teams: [{ name: 'Union St.-Gilloise' }, { name: "Hapoel Be'er Sheva" }] };
const gilloise2 = { id: 's365:2', ts: 1000, status: 'live', minute: 20, hg: 1, ag: 0, teams: [{ name: 'Union St. Gilloise' }, { name: 'Hapoel Beer Sheva' }] };
const folded = F.dedupeMatches([gilloise, gilloise2]);
assert.strictEqual(folded.length, 1);
assert.ok(folded[0]._ids.indexOf('sofa:1') >= 0 && folded[0]._ids.indexOf('s365:2') >= 0);
assert.strictEqual(folded[0].hg, 1);
const reversed = { id: 'espn:3', ts: 1000, status: 'live', minute: 20, hg: 0, ag: 1, teams: [{ name: 'Hapoel Beer Sheva' }, { name: 'Union St. Gilloise' }] };
const keptSide = F.dedupeMatches([gilloise, reversed]);
assert.strictEqual(keptSide.length, 1);
assert.strictEqual(keptSide[0].hg, 1);
assert.strictEqual(keptSide[0].ag, 0);
assert.strictEqual(keptSide[0].teams[0].name, 'Union St.-Gilloise');
const further = { id: 'espn:4', ts: 1000, status: 'live', minute: 20, hg: 0, ag: 4, teams: [{ name: 'Hapoel Beer Sheva' }, { name: 'Union St. Gilloise' }] };
const takenSide = F.dedupeMatches([gilloise, further]);
assert.strictEqual(takenSide.length, 1);
assert.strictEqual(takenSide[0].hg, 4);
assert.strictEqual(takenSide[0].ag, 0);
assert.strictEqual(takenSide[0].teams[0].name, 'Union St.-Gilloise');
assert.strictEqual(F.dedupeMatches([gilloise, { id: 'x', ts: 1000, teams: [{ name: 'Arsenal' }, { name: 'Chelsea' }] }]).length, 2);
function card(id, home, away, extra) {
  return Object.assign({ id, ts: 5000, status: 'live', minute: 10, hg: 0, ag: 0, segment: 'main', teams: [{ name: home }, { name: away }] }, extra);
}
const chivas = F.dedupeMatches([
  card('espn:g', 'Guadalajara', 'Necaxa', { minute: 11, hg: 0, ag: 0, pred_low: true }),
  card('s365:g', 'Chivas', 'Necaxa', { minute: 30, hg: 1, ag: 0, pred_low: false, pred: { h: 0.5, d: 0.3, a: 0.2 } }),
]);
assert.strictEqual(chivas.length, 1);
assert.strictEqual(chivas[0].hg, 1);
assert.strictEqual(chivas[0].minute, 30);
assert.strictEqual(chivas[0].pred_low, false);
assert.ok(chivas[0]._ids.indexOf('espn:g') >= 0 && chivas[0]._ids.indexOf('s365:g') >= 0);
assert.strictEqual(F.dedupeMatches([
  card('espn:g', 'Guadalajara', 'Necaxa'),
  card('s365:w', 'Guadalajara Chivas (W)', 'Necaxa (W)', { segment: 'women', ts: 5000 + 10740 }),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('espn:g', 'Guadalajara', 'Necaxa'),
  card('s365:w', 'Guadalajara Chivas (W)', 'Necaxa (W)', { ts: 5000 + 10740 }),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('espn:dep', 'Deportivo Guadalajara', 'Necaxa'),
  card('s365:chi', 'Chivas', 'Necaxa'),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('a', 'Blackpool', 'Milton Keynes Dons'),
  card('b', 'Blackpool', 'MK Dons'),
]).length, 1);
assert.strictEqual(F.dedupeMatches([
  card('a', 'Sanfrecce Hiroshima', 'Kyoto Sanga'),
  card('b', 'Hiroshima Sanfrecce', 'Kyoto'),
]).length, 1);
assert.strictEqual(F.dedupeMatches([
  card('a', 'Avispa Fukuoka', 'Fagiano Okayama'),
  card('b', 'Fukuoka', 'Okayama'),
]).length, 1);
const youthLive = card('sofa:c', 'Criciúma U20', 'Flamengo U20', { segment: 'youth', status: 'live', minute: 91, hg: 0, ag: 2 });
const youthFt = card('s365:c', 'Criciúma/Sc Youth', 'Flamengo/RJ Youth', { segment: 'youth', status: 'finished', minute: null, hg: 0, ag: 2 });
const youth = F.dedupeMatches([youthFt, youthLive]);
assert.strictEqual(youth.length, 1);
assert.strictEqual(youth[0].status, 'live');
assert.strictEqual(youth[0].minute, 91);
assert.strictEqual(youth[0].ag, 2);
const youthGoal = F.dedupeMatches([youthLive, card('s365:c2', 'Criciúma/Sc Youth', 'Flamengo/RJ Youth', { segment: 'youth', status: 'finished', minute: null, hg: 0, ag: 3 })]);
assert.strictEqual(youthGoal[0].status, 'finished');
assert.strictEqual(youthGoal[0].ag, 3);
const staleFt = F.dedupeMatches([
  card('ft', 'Blackpool', 'MK Dons', { status: 'finished', minute: null, hg: 0, ag: 0 }),
  card('lv', 'Blackpool', 'Milton Keynes Dons', { status: 'live', minute: 50, hg: 1, ag: 0 }),
]);
assert.strictEqual(staleFt[0].hg, 1);
assert.strictEqual(staleFt[0].status, 'live');
const missed = F.dedupeMatches([
  card('late', 'Avispa Fukuoka', 'Okayama', { minute: 70, hg: 1, ag: 0 }),
  card('goals', 'Fukuoka', 'Okayama', { minute: 40, hg: 2, ag: 0 }),
]);
assert.strictEqual(missed[0].hg, 2);
assert.strictEqual(missed[0].minute, 70);
assert.strictEqual(F.dedupeMatches([
  card('u', 'Manchester United', 'Chelsea'),
  card('c', 'Manchester City', 'Chelsea'),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('a', "Hapoel Ra'anana", 'Maccabi Haifa'),
  card('b', 'Hapoel Afula', 'Maccabi Haifa'),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('a', 'Arsenal', 'Chelsea', { ts: 1000 }),
  card('b', 'Arsenal', 'Chelsea', { ts: 1000 + 3 * 3600, hg: 1 }),
]).length, 2);
assert.strictEqual(F.dedupeMatches([
  card('a', 'Real Madrid', 'Getafe'),
  card('b', 'Real', 'Getafe'),
]).length, 2);
const postponed = F.dedupeMatches([
  card('espn:p', 'Universidad de Chile', 'Antofagasta', { status: 'upcoming', hg: null, ag: null, minute: null }),
  card('s365:p', 'Universidad de Chile', 'Deportes Antofagasta', { status: 'postponed', hg: null, ag: null, minute: null }),
]);
assert.strictEqual(postponed.length, 1);
assert.strictEqual(postponed[0].status, 'postponed');
const stillLive = F.dedupeMatches([
  card('espn:l', 'Arsenal', 'Chelsea', { status: 'live', minute: 20, hg: 1, ag: 0 }),
  card('s365:l', 'Arsenal', 'Chelsea', { status: 'postponed', hg: null, ag: null, minute: null }),
]);
assert.strictEqual(stillLive[0].status, 'live');
assert.strictEqual(stillLive[0].hg, 1);
assert.strictEqual(F.listVisible({ id: 'keep', _ids: ['keep', 'drop'], region: 'europe_top', status: 'live', day: 0, segment: 'main' }, { view: 'oblibene', fav: ['drop'] }), true);
const pages = fs.readFileSync(path.join(__dirname, '../.github/workflows/pages.yml'), 'utf8');
assert.ok(pages.includes("github.event_name == 'push'"));
assert.ok(pages.includes('cancel-in-progress: false'));
assert.ok(pages.includes('origin/main') && pages.includes('needs.build.outputs.deploy'));

console.log('live ok');
