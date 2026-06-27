const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const api = async (p, opt) => (await fetch(p, opt)).json();
const post = (p, b) => api(p, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(b||{})});
const esc = s => (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const toast = m => { const t=document.createElement('div'); t.className='toast'; t.textContent=m;
  document.body.appendChild(t); setTimeout(()=>t.remove(), 2600); };

const LANGS = ['Hindi','Marathi','Bengali','Telugu','Kannada','Gujarati','Tamil','Bhojpuri','Awadhi','Maithili'];
const NATIVE = {Hindi:'हिन्दी',Marathi:'मराठी',Bengali:'বাংলা',Telugu:'తెలుగు',Kannada:'ಕನ್ನಡ',
  Gujarati:'ગુજરાતી',Tamil:'தமிழ்',Bhojpuri:'भोजपुरी',Awadhi:'अवधी',Maithili:'मैथिली'};
const AGES = [['0-12','👶'],['13-17','🧒'],['18-40','🧑'],['41-60','🧔'],['61-70','👴'],['71-80','👴'],['80+','🧓']];
const VOICE_SAMPLES = ['old woman, white saree, walks with a stick, hard of hearing',
  'elderly man, saffron kurta, rudraksha mala, confused, asking for Ramkund',
  'old man in dhoti, cannot remember his name, came with his son'];

const S = {node:'A', kind:'missing', lang:'Maithili', age:'71-80', gender:'Female', online:true};

// ---------- tabs (hash-routed, so each tab is deep-linkable: #intake #queue #map #dash) ----------
function selectTab(name){
  const b = $(`nav.tabs button[data-tab="${name}"]`); if(!b) return;
  $$('nav.tabs button').forEach(x => x.classList.remove('active')); b.classList.add('active');
  $$('main > section').forEach(s => s.classList.add('hidden'));
  $('#tab-'+name).classList.remove('hidden');
  if (name === 'map') setTimeout(initMap, 60);
  if (name === 'dash') loadDash();
  if (location.hash.slice(1) !== name) history.replaceState(null, '', '#'+name);
}
$$('nav.tabs button').forEach(b => b.onclick = () => selectTab(b.dataset.tab));
window.addEventListener('hashchange', () => selectTab(location.hash.slice(1) || 'intake'));

// ---------- pickers ----------
function pick(container, items, render, onsel, selFirst){
  const el = $(container); el.innerHTML='';
  items.forEach((it,i) => {
    const b = document.createElement('button'); b.className='opt'+((selFirst&&i===0)?' sel':'');
    b.innerHTML = render(it);
    b.onclick = () => { [...el.children].forEach(c=>c.classList.remove('sel')); b.classList.add('sel'); onsel(it); };
    el.appendChild(b);
  });
}
function initPickers(places){
  // language
  const lg = $('#langPick'); lg.innerHTML='';
  LANGS.forEach(l => { const b=document.createElement('button'); b.className='lang'+(l===S.lang?' sel':'');
    b.textContent=NATIVE[l]; b.title=l;
    b.onclick=()=>{ [...lg.children].forEach(c=>c.classList.remove('sel')); b.classList.add('sel'); S.lang=l; }; lg.appendChild(b); });
  // age — highlight the chip matching S.age (keep visual + state consistent)
  pick('#agePick', AGES, a=>`<span class="ic">${a[1]}</span>${a[0]}`, a=>S.age=a[0]);
  $$('#agePick .opt').forEach(b=>{ if(b.textContent.trim().endsWith(S.age)) b.classList.add('sel'); });
  // gender
  $$('#genderPick .opt').forEach(b=>b.onclick=()=>{ $$('#genderPick .opt').forEach(c=>c.classList.remove('sel')); b.classList.add('sel'); S.gender=b.dataset.g; });
  $$('#genderPick .opt')[1].classList.add('sel');
  // node + kind
  $$('#nodePick .opt').forEach(b=>b.onclick=()=>{ $$('#nodePick .opt').forEach(c=>c.classList.remove('sel')); b.classList.add('sel'); S.node=b.dataset.node; });
  $$('#kindPick .opt').forEach(b=>b.onclick=()=>{ $$('#kindPick .opt').forEach(c=>c.classList.remove('sel')); b.classList.add('sel'); S.kind=b.dataset.kind; });
  // places
  const opts = places.map(p=>`<option>${esc(p)}</option>`).join('');
  $('#place').innerHTML=opts; $('#qPlace').innerHTML='<option value="">any location</option>'+opts; $('#rPlace').innerHTML=opts;
  $('#place').value='Ramkund Ghat'; $('#rPlace').value='Ramkund Ghat';
}

// ---------- demo scenario ----------
const chipByAttr = (sel, attr, val)=>{ const b=$$(sel).find(x=>x.dataset[attr]===val); if(b) b.click(); };
const chipByText = (sel, txt)=>{ const b=$$(sel).find(x=>x.textContent.trim().includes(txt)); if(b) b.click(); };
$('#demoBtn').onclick = async ()=>{
  const r = await post('/api/scenario', {});
  await refreshNet();
  $('nav.tabs button[data-tab="intake"]').click();
  const f = r.found_suggestion;
  chipByAttr('#nodePick .opt','node','B');
  chipByAttr('#kindPick .opt','kind','found');
  $(`#langPick .lang[title="${f.language}"]`)?.click();
  chipByText('#agePick .opt', f.age_band);
  chipByAttr('#genderPick .opt','g','Female');
  $('#place').value=f.last_seen; $('#name').value=''; $('#desc').value=f.description; $('#state').value='';
  $('#resultCard').classList.add('hidden');
  toast('🎬 Demo loaded: a mother (Lakshmi Jha) is missing at Center A · network OFFLINE');
  setTimeout(()=>toast('Now press “Register & search” — B can\'t see her yet. Then Courier sync → search again.'), 2900);
};

$('#voiceBtn').onclick = async (e)=>{ e.preventDefault();
  const spoken = VOICE_SAMPLES[Math.floor(Math.random()*VOICE_SAMPLES.length)];
  toast('🎤 listening…');
  const r = await post('/api/claude/voice', {text:spoken, language:S.lang});
  $('#desc').value = r.description || spoken;
  if(r.name) $('#name').value = r.name;
  toast(r.source==='claude' ? '✨ Claude cleaned & structured the speech' : '🎤 structured (Claude offline — deterministic)');
};

$('#nameCheck').onclick = async ()=>{
  const a=$('#nameA').value.trim(), b=$('#nameB').value.trim();
  $('#nameResult').innerHTML='<span class="sub">checking…</span>';
  const r = await api(`/api/claude/name?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  const pct = Math.round(r.equiv*100);
  const cls = r.equiv>=0.85?'AUTOSUGGEST':r.equiv>=0.5?'REVIEW':'WEAK';
  $('#nameResult').innerHTML = `<div class="match"><div class="hdr">
    <span class="band ${cls}">${pct}% same person</span>
    <span class="pill">${r.source==='claude'?'✨ Claude live':'offline fallback'}</span></div>
    <div class="meta">${esc(r.rationale)}</div></div>`;
};

// ---------- network ----------
async function refreshNet(){
  const st = await api('/api/state'); S.online = st.online;
  $('#netdot').className = 'dot'+(st.online?'':' off');
  $('#nettext').textContent = st.online ? 'online' : 'OFFLINE — partitioned';
  $('#toggleNet').textContent = st.online ? 'Pull the cable' : 'Reconnect';
  return st;
}
$('#toggleNet').onclick = async ()=>{ const r=await post('/api/online',{online:!S.online});
  S.online=r.online; toast(r.online?'Network online':'Network OFFLINE — centers partitioned'); refreshNet(); };
$('#syncBtn').onclick = async ()=>{ const r=await post('/api/sync',{});
  const n=r.synced.A_to_B+r.synced.B_to_A; toast(`📨 Courier synced ${n} records (A→B ${r.synced.A_to_B}, B→A ${r.synced.B_to_A})`); };

// ---------- intake ----------
let lastFound = null;
$('#submitIntake').onclick = async ()=>{
  const rec = { node:S.node, kind:S.kind, language:S.lang, age_band:S.age, gender:S.gender,
    last_seen:$('#place').value, state:$('#state').value.trim(), name:$('#name').value.trim(),
    description:$('#desc').value.trim(), mobile:$('#mobile').value.trim(),
    center: S.node==='A'?'Adgaon Kho-Ya-Paya':'Sadhugram Lost Found' };
  $('#intakeNote').textContent='registering…';
  const r = await post('/api/intake', rec);
  $('#intakeNote').textContent = `saved as ${r.case_id}`;
  lastFound = { node:S.node, rec, case_id:r.case_id };
  $('#resultCard').classList.remove('hidden');
  showResult(r.matches);
  $('#resultCard').scrollIntoView({behavior:'smooth'});
};
function showResult(matches){
  const off = $('#nettext').textContent.indexOf('OFFLINE')>=0;
  $('#resultSub').innerHTML = (off
    ? `<b style="color:var(--red)">OFFLINE</b> — searched only Center ${lastFound.node}'s local replica. `
    : `Searched <b>every center</b> live. `) + `${matches.length} candidate(s). `
    + `<button class="btn" id="researchBtn" style="margin-left:8px">🔁 Re-search all centers</button>`;
  renderMatches('#results', matches, lastFound.node, lastFound.case_id);
  $('#researchBtn').onclick = async ()=>{
    const q = new URLSearchParams({ node:lastFound.node, kind:'found', ...lastFound.rec });
    const r = await api('/api/search?'+q.toString());
    showResult(r.matches);
    toast(`Re-searched — ${r.matches.length} candidate(s) across all synced centers`);
  };
}

// ---------- match rendering ----------
function bandClass(b){ return b==='AUTO-SUGGEST'?'AUTOSUGGEST':b; }
function reachTag(p){ if(p==null) return '';
  const c = p>=0.7?'hi':p>=0.4?'mid':'lo';
  return `<span class="reach ${c}" title="geographic plausibility — could they have reached the found spot?">reach ${p}</span>`; }

function renderMatches(sel, matches, node, queryId){
  const box=$(sel);
  if(!matches.length){ box.innerHTML='<div class="sub">No candidate matches in reach.</div>'; return; }
  box.innerHTML = matches.map((m,i)=>`
    <div class="match ${i===0&&m.band==='AUTO-SUGGEST'?'top':''}" id="m-${m.case_id}">
      <div class="hdr">
        <span class="band ${bandClass(m.band)}">${m.band}</span>
        ${reachTag(m.reach_plausibility)}
        <span class="pill">${m.origin_node===node?'this center':'Center '+m.origin_node}</span>
        <span class="score">${m.score}</span>
      </div>
      <div class="meta"><span>${esc(m.age_band||'?')}</span><span>seen: ${esc(m.last_seen_zone||'—')}</span><span>${esc(m.status||'')}</span></div>
      ${m.note?`<div class="note">⚠ ${esc(m.note)}</div>`:''}
      <div class="acts">
        <button class="btn" onclick="reveal('${node}','${m.case_id}')">Reveal record (audited)</button>
        ${queryId?`<button class="btn primary" onclick="confirmReunion('${node}','${queryId}','${m.case_id}')">Confirm reunion</button>`:''}
      </div>
      <div class="pii hidden" id="pii-${m.case_id}"></div>
    </div>`).join('');
}

window.reveal = async (node, cid)=>{
  const el=$('#pii-'+cid); if(!el) return; el.classList.remove('hidden');
  const r = await api(`/api/record/${node}/${cid}?role=operator&reason=match%20review`);
  if(r.minor_block){ el.innerHTML='🔒 <b>Minor</b> — routed to the police-only queue, hidden from kiosk operators.'; el.style.color='var(--red)'; return; }
  const x=r.record; el.innerHTML = `<b>${esc(x.name)||'(no name on file)'}</b> · ${esc(x.gender)} ${esc(x.age_band)} · ${esc(x.state)} · ${esc(x.language)}<br>
    📞 ${esc(x.mobile)||'no number'} · “${esc(x.description)}”<br><span class="sub" style="margin:0">center: ${esc(x.center)} · status: ${esc(x.status)}</span>`;
};

window.confirmReunion = (node, foundId, missingId)=>{
  const m=document.createElement('div'); m.className='modal';
  m.innerHTML=`<div class="box"><h2>Verify the family</h2>
    <div class="sub">Ask the <b>searching family</b> (never the confused person) a withheld detail:</div>
    <p>“What was she wearing? Who did she come with? Any mark?”</p>
    <div class="row"><button class="btn primary" id="yes">Family confirmed ✓</button>
    <button class="btn" id="no">Cancel</button></div></div>`;
  document.body.appendChild(m);
  m.querySelector('#no').onclick=()=>m.remove();
  m.querySelector('#yes').onclick=async()=>{
    const r = await post('/api/confirm',{node,found_id:foundId,missing_id:missingId});
    const n = r.notification||{};
    m.querySelector('.box').innerHTML = `<h2>✅ Reunion confirmed</h2>
      <div class="sub">Both records marked Reunited. Reunification dispatched:</div>
      <div class="pii" style="margin-top:6px"><b>🤝 Handoff:</b> ${esc(n.handoff||'')}</div>
      <div class="pii" style="margin-top:8px">${esc(n.pa_announcement||'')}</div>
      <div class="pii" style="margin-top:8px">${esc(n.sms_to_family||'')}</div>
      <div class="note" style="color:var(--green);margin-top:8px">🛡 ${esc(n.safeguard||'')}</div>
      <div class="row" style="margin-top:14px"><button class="btn primary" id="done">Done</button></div>`;
    m.querySelector('#done').onclick=()=>m.remove();
    toast('✅ Reunion confirmed & dispatched');
  };
};

// ---------- queue search ----------
$('#qSearch').onclick = async ()=>{
  if(!$('#qDesc').value.trim() && !$('#qPlace').value){
    $('#qResults').innerHTML='<div class="sub">Enter a description or pick a location to search.</div>'; return;
  }
  const node=$('#qNode').value;
  $('#qResults').innerHTML='<div class="sub">searching…</div>';
  const q = new URLSearchParams({node, kind:'found', description:$('#qDesc').value, last_seen:$('#qPlace').value});
  const r = await api('/api/search?'+q.toString());
  renderMatches('#qResults', r.matches, node, '');
};

// ---------- map ----------
let MAP, layers=[];
async function initMap(){
  if(MAP){ MAP.invalidateSize(); return; }
  MAP = L.map('map').setView([20.0, 73.78], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18, attribution:'© OSM'}).addTo(MAP);
  const {features} = await api('/api/geojson');
  const col = {'very high':'#cf3b3b','high':'#cf8a00','medium':'#1d9e75'};
  features.forEach(f=>{
    if(f.t==='cam') L.circleMarker([f.lat,f.lng],{radius:2,color:'#9a8',opacity:.5,fillOpacity:.4}).addTo(MAP);
    else if(f.t==='police') L.circleMarker([f.lat,f.lng],{radius:5,color:'#2b6cb0',fillColor:'#2b6cb0',fillOpacity:.9}).addTo(MAP).bindPopup('👮 '+f.name);
    else if(f.t==='choke') L.circleMarker([f.lat,f.lng],{radius:7,color:col[f.risk]||'#888',fillColor:col[f.risk]||'#888',fillOpacity:.7}).addTo(MAP).bindPopup(`<b>${f.name}</b><br>${f.category}<br>risk: ${f.risk}`);
  });
}
$('#rGo').onclick = async ()=>{
  const q=new URLSearchParams({place:$('#rPlace').value,date:$('#rDate').value,t0:$('#rT0').value,t1:$('#rT1').value});
  const s=await api('/api/reachability?'+q.toString());
  if(s.error){ toast(s.error); return; }
  layers.forEach(l=>MAP.removeLayer(l)); layers=[];
  const c=[s.lat,s.lng];
  layers.push(L.circle(c,{radius:s.max_radius_km*1000,color:'#e87722',fillColor:'#e87722',fillOpacity:.12,weight:2}).addTo(MAP));
  layers.push(L.circle(c,{radius:s.likely_radius_km*1000,color:'#b65a12',fillColor:'#e87722',fillOpacity:.22,weight:1}).addTo(MAP));
  layers.push(L.marker(c).addTo(MAP).bindPopup(`<b>${s.place}</b><br>last-known`).openPopup());
  MAP.setView(c, s.max_radius_km>1.2?13:15);
  $('#rInfo').innerHTML = `density <b>${s.density}</b> → speed ×${s.speed_factor} · reachable <b>${s.max_radius_km} km</b> (tight ${s.likely_radius_km} km) · ${s.cameras_to_review} cams`;
};

// ---------- dashboard ----------
async function loadDash(){
  const st=await api('/api/state');
  $('#nodeStats').innerHTML = Object.entries(st.nodes).map(([n,s])=>`
    <div class="nodebox"><h3><span class="nodetag">Center ${n}</span> ${esc(s.centers[0])} …</h3>
      <div class="statgrid">
        <div class="stat"><div class="n">${s.total}</div><div class="l">records</div></div>
        <div class="stat"><div class="n">${s.reunited}</div><div class="l">reunited</div></div>
        <div class="stat"><div class="n">${s.found}</div><div class="l">found logged</div></div>
        <div class="stat"><div class="n">${s.from_peer}</div><div class="l">synced from peer</div></div>
      </div></div>`).join('');
  const a=await api('/api/audit?node=A'), b=await api('/api/audit?node=B');
  const all=[...a.audit,...b.audit].slice(0,10);
  $('#auditLog').innerHTML = all.length? all.map(x=>`<div>${esc(x.ts)} · ${esc(x.role)} · ${esc(x.action)} · ${esc(x.case_id)}</div>`).join('') : '<div>no PII accessed yet</div>';
  loadHotspots();
}
async function loadHotspots(){
  const mult = $('#hSnan').value || '1';
  const {hotspots}=await api('/api/hotspots?snan='+mult);
  const col={'very high':'#cf3b3b','high':'#cf8a00','medium':'#1d9e75'};
  $('#hotspots').innerHTML = hotspots.map(h=>`<div class="match"><div class="hdr">
    <span class="band" style="background:${col[h.risk]}22;color:${col[h.risk]}">${h.risk}</span>
    <b>${esc(h.name)}</b><span class="score">score ${h.score}</span></div>
    <div class="meta"><span>${h.reports} reports</span><span>${h.cams} cameras ≤400m</span></div></div>`).join('');
}

// ---------- boot ----------
(async function(){
  const [{places},{snan}] = [await api('/api/places'), await api('/api/snan')];
  initPickers(places);
  // date / snan dropdowns
  const dates = [['2027-07-20 (ordinary day)','2027-07-20'], ...Object.entries(snan).map(([d,v])=>[`${d} — ${v[0]} (×${v[2]})`,d])];
  $('#rDate').innerHTML = dates.map(([t,v])=>`<option value="${v}">${esc(t)}</option>`).join('');
  $('#rDate').value='2027-09-11';
  $('#hSnan').innerHTML = [['ordinary day (×1)','1'], ...Object.entries(snan).map(([d,v])=>[`${d} — ${v[0]} (×${v[2]})`,v[2]])]
    .map(([t,v])=>`<option value="${v}">${esc(t)}</option>`).join('');
  $('#hSnan').onchange = loadHotspots;
  api('/api/claude/status').then(cs=>{ $('#claudeStatus').textContent = cs.available?'Claude live ✨':'Claude: offline fallback'; });
  refreshNet();
  selectTab(location.hash.slice(1) || 'intake');   // deep-link support (#map etc.)
})();
