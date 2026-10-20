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
assert.ok(sw.includes("fotbal-v2"), 'verze cache');

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

console.log('live ok');
