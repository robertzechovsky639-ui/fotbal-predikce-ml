'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const S = { view: 'zapasy', day: 0, reg: 'focus', filt: 'all', favOnly: false, fav: new Set(JSON.parse(localStorage.fotbalFav || '[]')), detail: null, tab: 'prehled' };
const DN = ['Neděle', 'Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota'];
const pct = x => x == null ? '–' : Math.round(x * 100) + ' %';
const f2 = x => x == null ? '–' : (+x).toFixed(2);
const REG_LABEL = { europe_top: 'Evropa – nejvyšší', europe_lower: 'Evropa – nižší', czech: 'Česko', europe_cups: 'Evropské poháry', asia: 'Asie', south_america: 'Jižní Amerika', international: 'Reprezentace', other: 'Ostatní' };
function saveFav() { localStorage.fotbalFav = JSON.stringify([...S.fav]); }
function probs(m) { return (m.live && m.live.p) || m.pred || { h: null, d: null, a: null }; }
function scoreSig(m) {
  const p = probs(m);
  return [m.status, m.hg, m.ag, m.minute, m.period, (m.reds || []).join(','), p.h == null ? '' : Math.round(p.h * 100), Math.round((p.d || 0) * 100), Math.round((p.a || 0) * 100), m.pred_low ? 1 : 0].join('|');
}
function visKey() {
  if (S.view === 'oblibene') return 'fav';
  if (S.view !== 'zapasy') return 'v:' + S.view;
  return [S.day, S.reg, S.filt, S.favOnly ? 1 : 0].join('|');
}

function upd() {
  const lv = ST.all.filter(m => m.status === 'live').length;
  const age = ST.generated ? Math.round((Date.now() / 1000 - ST.generated) / 60) : null;
  const names = { sofascore: 'Sofascore', s365: '365scores', espn: 'ESPN', sofaDetail: 'detail' };
  const hd = health().map(h => `<span class="hd ${h.state}" title="${names[h.k]}">${names[h.k]}</span>`).join('');
  const html = `<span class="g"></span>${lv ? lv + ' živě' : 'Bez živých zápasů'} · predikce před ${age ?? '–'} min<div class="hrow">${hd}</div>`;
  const el = $('#upd'); if (el && el._h !== html) { el._h = html; el.innerHTML = html; }
}

function focusOk(m) { return m.region === 'europe_top' || m.region === 'czech' || m.region === 'europe_cups'; }
function filt(list) {
  return list.filter(m => {
    if (S.reg === 'focus' && !focusOk(m)) return false;
    if (S.reg !== 'all' && S.reg !== 'focus' && m.region !== S.reg) return false;
    if (S.filt === 'live' && m.status !== 'live') return false;
    if (S.filt === 'up' && m.status !== 'upcoming') return false;
    if (S.filt === 'fin' && m.status !== 'finished') return false;
    if (S.favOnly && !S.fav.has(m.id)) return false;
    return true;
  });
}
function scoreText(m) {
  if (m.hg == null || m.ag == null) return '';
  return m.hg + '–' + m.ag;
}
function card(m) {
  const p = probs(m);
  const t = new Date(m.ts * 1000).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Prague' });
  const line = (i) => `<div class="row"><div class="pl ${m.winner === i ? 'w' : ''}">${esc(m.teams[i].name)}</div><div class="scoreline">${m.status === 'upcoming' ? (i === 0 ? t : '') : (i === 0 ? (m.hg ?? '') : (m.ag ?? ''))}</div></div>`;
  const tri = p.h == null ? '<div class="na">Predikce se počítá…</div>' : `<div class="lbl">${m.status === 'live' ? 'PREDIKCE TEĎ' : 'PREDIKCE'}${m.pred_low ? ' <span class="low">nižší jistota</span>' : ''}</div><div class="tri"><div class="h"><b>${pct(p.h)}</b>1</div><div class="d"><b>${pct(p.d)}</b>X</div><div class="a"><b>${pct(p.a)}</b>2</div></div>`;
  const live = m.status === 'live' ? `<span class="livebadge">▶ ${m.minute != null ? m.minute + "'" : 'živě'}</span>` : '';
  return `<div class="m" data-id="${esc(m.id)}" data-sig="${esc(scoreSig(m))}">${line(0)}${line(1)}${live}${tri}${m.odds ? `<div class="odds"><span>1 ${f2(m.odds.h)}</span><span>X ${f2(m.odds.d)}</span><span>2 ${f2(m.odds.a)}</span></div>` : ''}</div>`;
}
function matchesView(fav) {
  const today = new Date();
  let h = '';
  if (!fav) {
    h += `<h1>ZÁPASY <span class="pill">● ${ST.all.filter(m => m.status === 'live').length} živě</span></h1><div class="days">`;
    for (let d = -2; d <= 2; d++) {
      const x = new Date(today); x.setDate(x.getDate() + d);
      const n = d === 0 ? 'Dnes' : d === -1 ? 'Včera' : d === 1 ? 'Zítra' : DN[x.getDay()];
      h += `<button data-day="${d}" class="${d === S.day ? 'on' : ''}"><b>${n}</b><small>${x.getDate()}. ${x.getMonth() + 1}.</small></button>`;
    }
    const regs = [['focus', 'Top + Česko + poháry'], ['all', 'Vše'], ...Object.entries(REG_LABEL)];
    h += `</div><div class="filters"><div class="sel"><label>SOUTĚŽE</label><select id="reg">${regs.map(([v, t]) => `<option value="${v}" ${S.reg === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      <div class="sel"><label>FILTR</label><select id="filt">${[['all', 'Vše'], ['live', 'Živě'], ['up', 'Nadcházející'], ['fin', 'Dohrané']].map(([v, t]) => `<option value="${v}" ${S.filt === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      <button class="star ${S.favOnly ? 'on' : ''}" id="favt">${S.favOnly ? '★' : '☆'}</button></div>`;
  } else h += `<h1>OBLÍBENÉ</h1>`;
  const all = fav ? ST.all.filter(m => S.fav.has(m.id)) : filt(ST.all.filter(m => m.day === S.day || (S.day === 0 && m.status === 'live')));
  if (!all.length) return h + `<div class="empty">${ST.all.length ? 'Žádné zápasy pro zvolený filtr.' : 'Načítám…'}${fav ? '<br>Hvězdičkou v detailu přidáš oblíbené.' : ''}</div>`;
  const g = {};
  for (const m of all) { const k = (m.league_name || m.league || 'Soutěž') + '|' + (m.region || ''); (g[k] = g[k] || []).push(m); }
  for (const k in g) {
    const m = g[k][0];
    h += `<div class="grp"><div class="ghead"><div>${esc(m.league_name || m.league)}<small>${esc(REG_LABEL[m.region] || m.region || '')}${m.country ? ' · ' + esc(m.country) : ''}</small></div></div>${g[k].map(card).join('')}</div>`;
  }
  return h;
}
function predView() {
  return `<h1>PREDIKCE</h1><div class="box"><h3>VLASTNÍ ZÁPAS</h3><input class="q" id="pa" placeholder="Domácí (např. Arsenal)"><div id="pal"></div><br><input class="q" id="pb" placeholder="Hosté (např. Chelsea)"><div id="pbl"></div><div id="pres"></div><p class="note">V prohlížeči počítá Elo a Poisson. U zápasů v seznamu je směs LightGBM a Elo ze serveru.</p></div>`;
}
function num(pack, key) { return pack && pack[key] != null ? pack[key] : null; }
function modelView() {
  const m = ST.model;
  if (!m || !m.test) return `<h1>MODEL</h1><div class="box note">Model se ještě nenačetl.</div>`;
  const row = (k, n) => { const p = m.test[k]; if (!p) return ''; return `<tr><td>${n}</td><td>${p.n}</td><td>${(p.accuracy * 100).toFixed(2)} %</td><td>${p.log_loss.toFixed(4)}</td><td>${p.rps.toFixed(4)}</td></tr>`; };
  const regs = Object.entries(m.by_region || {}).filter(([, v]) => v).map(([k, v]) => `<tr><td>${esc(REG_LABEL[k] || k)}</td><td>${v.blend.n}</td><td>${v.blend.log_loss.toFixed(3)}</td><td>${v.blend.rps.toFixed(3)}</td><td>${v.elo.log_loss.toFixed(3)}</td></tr>`).join('');
  const cov = Object.entries(m.coverage || {}).map(([k, v]) => `<tr><td>${esc(REG_LABEL[k] || k)}</td><td>${v.matches.toLocaleString('cs-CZ')}</td><td>${v.n_leagues}</td><td>${esc(v.from)} – ${esc(v.to)}</td></tr>`).join('');
  const notes = (m.notes || []).map(n => `<li>${esc(n)}</li>`).join('');
  return `<h1>MODEL</h1><div class="box"><h3>TEST ${esc(m.split || '')}</h3><table><tr><th></th><th>N</th><th>PŘESNOST</th><th>LOG LOSS</th><th>RPS</th></tr>${row('blend', 'Směs')}${row('lightgbm', 'LightGBM')}${row('elo', 'Elo')}${row('baseline', 'Frekvence')}${row('dixon', 'Dixon-Coles')}</table>
    <p class="note">Zápasů v datech: ${(m.n_matches || 0).toLocaleString('cs-CZ')} · trénink ${m.train_rows || '–'} · test ${m.test_rows || '–'} · váha LightGBM ${m.blend_w} · brána ${m.gate && m.gate.ok ? 'prošla' : 'neprošla'}${m.gate ? ' (' + esc(m.gate.reason) + ')' : ''}</p></div>
    <div class="box"><h3>PODLE REGIONU (směs)</h3><table><tr><th></th><th>N</th><th>LOG LOSS</th><th>RPS</th><th>ELO LL</th></tr>${regs || '<tr><td colspan="5">bez testovacích zápasů</td></tr>'}</table></div>
    <div class="box"><h3>POKRYTÍ HISTORIE</h3><table><tr><th></th><th>ZÁPASY</th><th>LIG</th><th>OD–DO</th></tr>${cov}</table></div>
    <div class="box"><h3>POZNÁMKY</h3><ul class="note">${notes}</ul></div>`;
}
function chatView() { return `<h1>CHAT</h1><div id="msgs"><div class="msg">Napiš dvojici, třeba „Arsenal vs Chelsea“. Odpovím z Elo v prohlížeči.</div></div><div style="padding:12px;display:flex;gap:8px"><input class="q" id="cq" placeholder="Zpráva…"><button class="ob" id="cs">➤</button></div>`; }
function teamsView() { return `<h1>TÝMY</h1><div style="padding:0 12px"><input class="q" id="ps" placeholder="Hledat tým…"></div><div id="plist"></div>`; }

function render() {
  const v = $('#view'); let h = '';
  if (S.view === 'zapasy') h = matchesView(false);
  else if (S.view === 'oblibene') h = matchesView(true);
  else if (S.view === 'predikce') h = predView();
  else if (S.view === 'model') h = modelView();
  else if (S.view === 'chat') { if (v.dataset.v === 'chat') return; h = chatView(); }
  else if (S.view === 'tymy') { if (v.dataset.v === 'tymy') return; h = teamsView(); }
  v.dataset.v = S.view; v.innerHTML = h; bind();
  if (S.view === 'zapasy' || S.view === 'oblibene') S.vis = visKey();
}
function showPred(box, nameA, nameB) {
  const m = { teams: [{ name: nameA }, { name: nameB }], region: 'europe_top', country: null, neutral: false };
  Fotbal.ensurePred(m, { teams: ST.teams, elo_params: ST.model && ST.model.elo_params });
  box.innerHTML = `<div class="tri" style="margin-top:12px"><div class="h"><b>${pct(m.pred.h)}</b>1</div><div class="d"><b>${pct(m.pred.d)}</b>X</div><div class="a"><b>${pct(m.pred.a)}</b>2</div></div><p class="note">${esc(m.pred_note || '')} Elo ${m.elo[0]} : ${m.elo[1]}</p>`;
}
function bind() {
  document.querySelectorAll('.days button').forEach(b => b.onclick = () => { S.day = +b.dataset.day; render(); });
  const reg = $('#reg'); if (reg) reg.onchange = e => { S.reg = e.target.value; render(); };
  const filtEl = $('#filt'); if (filtEl) filtEl.onchange = e => { S.filt = e.target.value; render(); };
  const fav = $('#favt'); if (fav) fav.onclick = () => { S.favOnly = !S.favOnly; render(); };
  document.querySelectorAll('.m[data-id]').forEach(x => x.onclick = () => openDetail(x.dataset.id));
  if (S.view === 'predikce') {
    const go = () => { const a = $('#pa').value.trim(), b = $('#pb').value.trim(); if (a && b) showPred($('#pres'), a, b); };
    $('#pa').onchange = go; $('#pb').onchange = go; $('#pa').onkeydown = e => { if (e.key === 'Enter') go(); }; $('#pb').onkeydown = e => { if (e.key === 'Enter') go(); };
  }
  if (S.view === 'tymy') {
    const i = $('#ps'); let t;
    i.oninput = () => { clearTimeout(t); t = setTimeout(() => { const q = i.value.toLowerCase(); const rows = q.length < 2 ? [] : ST.teams.filter(x => (x.name || '').toLowerCase().includes(q)).slice(0, 20); $('#plist').innerHTML = '<div class="box">' + (rows.map(p => `<div class="fac"><span>${esc(p.name)}</span><span class="na">Elo ${p.elo} · ${p.n} z.</span></div>`).join('') || '<div class="note">Nic nenalezeno</div>') + '</div>'; }, 200); };
  }
  if (S.view === 'chat') {
    const send = () => {
      const q = $('#cq').value.trim(); if (!q) return; $('#cq').value = '';
      $('#msgs').insertAdjacentHTML('beforeend', `<div class="msg me">${esc(q)}</div>`);
      const mm = q.split(/\s+vs\s+/i);
      let ans = 'Napiš to jako „Arsenal vs Chelsea“.';
      if (mm.length === 2) { const fake = document.createElement('div'); showPred(fake, mm[0], mm[1]); ans = mm[0] + ' vs ' + mm[1] + ': ' + fake.innerText.replace(/\s+/g, ' '); }
      $('#msgs').insertAdjacentHTML('beforeend', `<div class="msg">${esc(ans)}</div>`);
    };
    $('#cs').onclick = send; $('#cq').onkeydown = e => { if (e.key === 'Enter') send(); };
  }
}
async function openDetail(id) {
  S.detail = ST.byId[id]; S.tab = 'prehled';
  try { const d = await staticApi('/api/match/' + encodeURIComponent(id)); if (d && d.id) S.detail = Object.assign(ST.byId[id] || {}, d); } catch (e) {}
  drawDetail();
}
function drawDetail() {
  const d = S.detail; if (!d) return;
  const el = $('#detail'); el.classList.remove('hidden');
  const p = probs(d);
  const score = d.hg == null ? '–' : (d.hg + ' : ' + d.ag);
  let h = `<div class="dh"><button class="back" id="bk">‹</button><div class="tt"><b>${esc(d.league_name || '')}</b><small>${esc(REG_LABEL[d.region] || '')}</small></div><button class="star ${S.fav.has(d.id) ? 'on' : ''}" id="fv">${S.fav.has(d.id) ? '★' : '☆'}</button></div>
    <div class="score"><div class="pp"><div class="av">${esc((d.teams[0].name || '?').slice(0, 2).toUpperCase())}</div><b>${esc(d.teams[0].name)}</b></div>
    <div class="mid"><div class="big">${score}</div><small>${d.status === 'live' ? 'živě ' + (d.minute != null ? d.minute + "'" : '') : d.status === 'finished' ? 'konec' : new Date(d.ts * 1000).toLocaleString('cs-CZ', { timeZone: 'Europe/Prague', weekday: 'short', hour: '2-digit', minute: '2-digit' })}</small></div>
    <div class="pp"><div class="av">${esc((d.teams[1].name || '?').slice(0, 2).toUpperCase())}</div><b>${esc(d.teams[1].name)}</b></div></div>
    <div class="tabs">${[['prehled', 'Přehled'], ['predikce', 'Predikce'], ['kurzy', 'Kurzy'], ['h2h', 'H2H'], ['stat', 'Statistiky']].map(([k, t]) => `<button data-t="${k}" class="${S.tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>`;
  h += ({ prehled: tPre, predikce: tPred, kurzy: tKur, h2h: tH, stat: tStat }[S.tab])(d, p);
  el.innerHTML = h;
  $('#bk').onclick = () => { el.classList.add('hidden'); S.detail = null; };
  $('#fv').onclick = () => { S.fav.has(d.id) ? S.fav.delete(d.id) : S.fav.add(d.id); saveFav(); drawDetail(); };
  el.querySelectorAll('.tabs button').forEach(b => b.onclick = () => { S.tab = b.dataset.t; drawDetail(); });
}
function tPre(d, p) {
  return `<div class="box"><div class="tri"><div class="h"><b>${pct(p.h)}</b>1</div><div class="d"><b>${pct(p.d)}</b>X</div><div class="a"><b>${pct(p.a)}</b>2</div></div>
    <p class="note">${d.pred_low ? esc(d.pred_note || '') : '1X2 po 90 minutách. Over/under 2,5: ' + pct(d.ou && d.ou.over) + ' · oba dají gól ' + pct(d.btts) + '.'}</p></div>`;
}
function tPred(d) {
  const ex = (d.exact || []).map(x => `<div class="fac"><span>${esc(x[0])}</span><b>${pct(x[1])}</b></div>`).join('');
  return `<div class="box"><h3>PŘESNÝ VÝSLEDEK</h3>${ex || '<div class="note">Není</div>'}<p class="note">Elo ${((d.elo || [])[0]) ?? '–'} : ${((d.elo || [])[1]) ?? '–'} · zápasy v historii ${(d.n || [])[0] ?? 0} / ${(d.n || [])[1] ?? 0}</p></div>`;
}
function tKur(d) {
  if (!d.odds) return `<div class="box note">Kurzy teď nejsou. Bereme jen předzápasové ceny, closing ne.</div>`;
  return `<div class="box"><table><tr><th></th><th>1</th><th>X</th><th>2</th></tr><tr><td>Kurz</td><td>${f2(d.odds.h)}</td><td>${f2(d.odds.d)}</td><td>${f2(d.odds.a)}</td></tr></table></div>`;
}
function tH(d) {
  const list = d.h2h_list || [];
  return `<div class="box"><h3>VZAJEMNÉ ZÁPASY</h3>${list.map(x => `<div class="fac"><span>${esc(x.date)}</span><b>${esc(x.score)}</b></div>`).join('') || '<div class="note">Zatím spolu nehráli, nebo jich v datech máme málo.</div>'}</div>`;
}
function tStat(d) {
  const c = d.cards || [];
  if (!c[0]) return `<div class="box note">Statistiky doplní denní model.</div>`;
  const cell = t => t ? `${t.elo ?? '–'} · forma gólů ${(t.f5_gf || []).join(',') || '–'}` : '–';
  return `<div class="box"><table><tr><th></th><th>${esc(d.teams[0].name)}</th><th>${esc(d.teams[1].name)}</th></tr><tr><td>Elo / góly</td><td>${esc(cell(c[0]))}</td><td>${esc(cell(c[1]))}</td></tr></table></div>`;
}
function patchCard(el, m) {
  const sig = scoreSig(m);
  if (el.dataset.sig === sig) return true;
  const lines = el.querySelectorAll('.scoreline');
  const tri = el.querySelectorAll('.tri b');
  const wantLive = m.status === 'live';
  if (lines.length < 2 || tri.length < 3 || wantLive !== !!el.querySelector('.livebadge')) return false;
  const p = probs(m);
  const t = new Date(m.ts * 1000).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Prague' });
  lines[0].textContent = m.status === 'upcoming' ? t : (m.hg ?? '');
  lines[1].textContent = m.status === 'upcoming' ? '' : (m.ag ?? '');
  if (m.hg !== lines[0]._g) { lines[0].classList.add('flash'); lines[0]._g = m.hg; }
  tri[0].textContent = pct(p.h); tri[1].textContent = pct(p.d); tri[2].textContent = pct(p.a);
  const badge = el.querySelector('.livebadge');
  if (badge) badge.textContent = '▶ ' + (m.minute != null ? m.minute + "'" : 'živě');
  const low = el.querySelector('.low');
  if (m.pred_low && !low) return false;
  el.dataset.sig = sig;
  return true;
}
let _pq = null, _raf = 0;
function paintList(ids) {
  if (!ids || !ids.length) return;
  if (!_pq) _pq = new Set();
  for (const id of ids) if (id) _pq.add(id);
  if (_raf) return;
  _raf = (window.requestAnimationFrame || (f => setTimeout(f, 16)))(() => { _raf = 0; const q = _pq; _pq = null; paintListNow([...q]); });
}
function paintListNow(ids) {
  if (S.view !== 'zapasy' && S.view !== 'oblibene') {
    if (S.detail && ids.indexOf(S.detail.id) >= 0) refreshDetail();
    return;
  }
  if (visKey() !== S.vis) { render(); return; }
  let missing = false;
  for (const id of ids) {
    const m = ST.byId[id]; if (!m) continue;
    const el = document.querySelector('.m[data-id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (!el) { missing = true; continue; }
    if (!patchCard(el, m)) {
      const tmp = document.createElement('div'); tmp.innerHTML = card(m);
      const n = tmp.firstElementChild; if (!n) { missing = true; continue; }
      n.onclick = () => openDetail(m.id); el.replaceWith(n);
    }
  }
  if (missing) render();
  const pill = document.querySelector('h1 .pill');
  if (pill) { const t = '● ' + ST.all.filter(m => m.status === 'live').length + ' živě'; if (pill.textContent !== t) pill.textContent = t; }
  if (S.detail && ids.indexOf(S.detail.id) >= 0) refreshDetail();
}
function refreshDetail() {
  const live = ST.byId[S.detail.id]; if (!live) return;
  const sig = scoreSig(live);
  if (S.detail._lsig === sig) return;
  S.detail = Object.assign(S.detail, live);
  S.detail._lsig = sig;
  drawDetail();
}

document.querySelectorAll('nav.bottom button').forEach(b => b.onclick = () => {
  S.view = b.dataset.v;
  document.querySelectorAll('nav.bottom button').forEach(x => x.classList.toggle('on', x === b));
  $('#detail').classList.add('hidden'); S.detail = null; render();
});
loadStatic().then(() => { render(); upd(); staticLoop(); }).catch(err => { $('#view').innerHTML = '<div class="empty">Data se nepodařilo načíst.</div>'; console.error(err); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
