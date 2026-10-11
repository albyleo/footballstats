const ids = ['kind','metric','league','season','min_minutes','team','search','last_n','sort'];
const $ = id => document.getElementById(id);
const display = value => value == null ? '—' : typeof value === 'number' ? value.toLocaleString('it-IT') : String(value);
const formatDate = value => value ? value.split('-').reverse().join('.') : '—';
let generation = 0, page = 0, latest = null, debounce, controller;
const size = 30;
const initial = new URLSearchParams(location.search);
if (['players','teams'].includes(initial.get('kind'))) $('kind').value = initial.get('kind');
if ([...$('metric').options].some(o => o.value === initial.get('metric'))) $('metric').value = initial.get('metric');
for (const id of ['league','season','team']) {
  const value=initial.get(id);
  if(value&&value.length<=128){$(id).add(new Option(value,value));$(id).value=value;}
}
for (const id of ['sort','last_n']) {
  if([...$(id).options].some(o=>o.value===initial.get(id)))$(id).value=initial.get(id);
}
if(initial.get('search')?.length<=128)$('search').value=initial.get('search');
const initialMinutes=Number(initial.get('min_minutes'));
if(Number.isInteger(initialMinutes)&&initialMinutes>=0&&initialMinutes<=100000)$('min_minutes').value=String(initialMinutes);

function updateView() {
  const player = $('kind').value === 'players';
  $('view-players').setAttribute('aria-pressed', String(player));
  $('view-teams').setAttribute('aria-pressed', String(!player));
  $('view-kicker').textContent = player ? '01 / ANALISI INDIVIDUALE' : '02 / ANALISI COLLETTIVA';
  $('view-title').textContent = player ? 'Esplora i giocatori' : 'Esplora le squadre';
  $('view-description').textContent = player ? 'Gol, assist e prestazioni, una presenza alla volta.' : 'Produzione offensiva, risultati e continuità della formazione.';
  $('view-badge').textContent = player ? 'VISTA GIOCATORI' : 'VISTA SQUADRE';
  $('count-label').textContent = player ? 'Righe giocatore nel filtro' : 'Righe squadra nel filtro';
  $('results-title').textContent = player ? 'Prestazioni dei giocatori' : 'Prestazioni delle squadre';
  $('search-label').textContent = player ? 'Cerca giocatore' : 'Cerca squadra';
  $('search').placeholder = player ? 'Nome o squadra del giocatore…' : 'Nome della squadra…';
  $('minutes-filter').hidden = !player;
  $('min_minutes').disabled = !player;
  $('team-note').hidden = player;
  for (const metric of ['first-half-goals','corners']) {
    const option = $('metric').querySelector(`[value="${metric}"]`);
    option.hidden = player;
    if (player && $('metric').value === metric) $('metric').value = 'goals';
  }
  for (const value of ['per90','minutes']) {
    $('sort').querySelector(`[value="${value}"]`).disabled = !player;
    if (!player && $('sort').value === value) $('sort').value = 'total';
  }
  for (const n of [5,10]) $('last_n').querySelector(`[value="${n}"]`).textContent = `Ultime ${n} ${player ? 'presenze' : 'partite'}`;
  $('layout').querySelector('[value="detail"]').textContent = player ? 'Dettaglio / per 90′' : 'Dettaglio / medie';
  document.title = `${player ? 'Giocatori' : 'Squadre'} — MyCombo`;
}

function cell(row, tag, value, note) {
  const element = document.createElement(tag);
  element.textContent = display(value);
  if (tag === 'th') element.scope = 'col';
  if (note) { const small = document.createElement('small'); small.textContent = note; element.append(small); }
  row.append(element);
  return element;
}
function formCell(row, values) {
  const element = cell(row, 'td', '');
  const group = document.createElement('span'); group.className = 'form';
  for (const value of values) {
    const badge = document.createElement('span'); badge.textContent = value || '—';
    badge.className = value === 'V' ? 'win' : value === 'S' ? 'loss' : '';
    badge.title = {V:'Vittoria',P:'Pareggio',S:'Sconfitta'}[value] || 'Non disponibile';
    group.append(badge);
  }
  element.append(group);
}
function options(id, values) {
  const select = $(id), previous = select.value, placeholder = select.options[0].textContent;
  select.replaceChildren(new Option(placeholder, ''));
  values.forEach(value => select.add(new Option(value, value)));
  select.value = values.includes(previous) ? previous : '';
}
function renderTable() {
  if (!latest) return;
  const player = $('kind').value === 'players', detail = $('layout').value === 'detail';
  const metric = $('metric').value, metricName = latest.metrics[metric];
  const defaults = player ? ['goals','assists','shots-on-target','yellowcards','fouls'] : ['goals','first-half-goals','shots-on-target','yellowcards','fouls','corners'];
  const keys = [...new Set([metric, ...defaults])].filter(k => latest.metric_coverage[k] > 0);
  const table = document.createElement('table'), head = document.createElement('thead'), header = document.createElement('tr');
  const caption = document.createElement('caption'); caption.className = 'sr-only'; caption.textContent = `${player ? 'Giocatori' : 'Squadre'}: ${metricName}`; table.append(caption);
  const columns = detail ? [player?'Giocatore':'Squadra','Campionato',metricName,player?'Per 90′ osservati':'Media per partita',player?'Minuti osservati':'Partite con dato',player?'Presenze':'Partite',player?'Minuti totali':'Ultimi risultati',player?'Da titolare':'Titolari in comune'] : [player?'Giocatore':'Squadra',player?'Squadra':'Campionato',...keys.map(k=>latest.metrics[k]),player?'Minuti':'Ultimi risultati',player?'Presenze':'Partite',player?'Da titolare':'Titolari in comune'];
  columns.forEach(value => cell(header, 'th', value)); head.append(header); table.append(head);
  const body = document.createElement('tbody');
  page = Math.min(page, Math.max(0, Math.ceil(latest.rows.length/size)-1));
  for (const row of latest.rows.slice(page*size,(page+1)*size)) {
    const tr = document.createElement('tr');
    cell(tr,'td',row.name,player&&detail?row.team:null);
    cell(tr,'td',player&&!detail?row.team:row.league,player&&!detail?row.league:row.season);
    if (detail) {
      cell(tr,'td',row.total,`${row.covered}/${row.matches} con dato`).className='metric-cell';
      cell(tr,'td',player?row.per90:row.per_match,row.covered<row.matches?'Copertura parziale':null);
      cell(tr,'td',player?row.paired_minutes:row.covered);
      cell(tr,'td',row.matches);
      if (player) cell(tr,'td',row.minutes); else formCell(tr,row.form);
    } else {
      keys.forEach(k=> {const c=cell(tr,'td',row.totals[k],`${row.coverage[k]}/${row.matches} con dato`);if(k===metric)c.className='metric-cell';});
      if (player) cell(tr,'td',row.minutes); else formCell(tr,row.form);
      cell(tr,'td',row.matches);
    }
    cell(tr,'td',player?row.starts:row.same_starters==null?null:`${row.same_starters}/11`);
    body.append(tr);
  }
  table.append(body); $('table').replaceChildren(table);
  if (!latest.rows.length) {
    const p=document.createElement('p');p.className='empty';
    p.textContent=player&&latest.catalog.find(c=>c.name===$('league').value)?.scope==='teams'?'Questo campionato contiene solo statistiche di squadra. Apri la vista Squadre per esplorarle.':'Nessun risultato. Prova ad ampliare i filtri o azzerarli.';
    $('table').replaceChildren(p);
  }
  $('pagination').textContent=`${latest.rows.length?page*size+1:0}–${Math.min((page+1)*size,latest.rows.length)} di ${display(latest.rows.length)}`;
  $('prev').disabled=page===0; $('next').disabled=(page+1)*size>=latest.rows.length;
  const known=latest.rows.filter(r=>r.covered>0).length;
  $('quality').textContent=`${metricName} · ${display(known)}/${display(latest.rows.length)} righe con dati. ${Number($('last_n').value)?'Ultime '+$('last_n').value+(player?' presenze caricate.':' partite caricate.'):'Intero campione caricato.'}`;
}

async function refresh() {
  const mine = ++generation;
  controller?.abort(); controller = new AbortController();
  const minutes=Number($('min_minutes').value);
  $('min_minutes').value=String(Number.isFinite(minutes)?Math.max(0,Math.min(100000,Math.floor(minutes))):0);
  const params = new URLSearchParams(ids.map(id=>[id,$(id).value]));
  if ($('kind').value==='teams') params.set('min_minutes','0');
  history.replaceState(null,'','/providers?'+params);
  latest=null; $('table').replaceChildren(); $('table').setAttribute('aria-busy','true');
  $('status').textContent='Caricamento archivio…'; $('quality').textContent=''; $('pagination').textContent='—';
  $('reload').disabled=true; $('prev').disabled=true; $('next').disabled=true;
  for(const id of ['count-rows','count-matches','count-latest','count-seasons']) $(id).textContent='—';
  $('data-warnings').hidden=true; $('dates').textContent='';
  try {
    const response=await fetch('/api/providers/report?'+params,{cache:'no-cache',signal:controller.signal});
    const data=await response.json(); if(mine!==generation)return;
    if(!response.ok)throw new Error(data.error||'Archivio non disponibile');
    for(const option of $('metric').options) {
      const unavailable=option.hidden||!data.metric_coverage[option.value];
      option.disabled=unavailable; option.textContent=data.metrics[option.value]+(unavailable?' · non disponibile':'');
    }
    if($('metric').selectedOptions[0].disabled) {
      const first=[...$('metric').options].find(o=>!o.disabled);
      if(first){$('metric').value=first.value;return refresh();}
    }
    latest=data; page=0;
    options('league',data.leagues);options('season',data.seasons);options('team',data.teams);
    $('count-rows').textContent=display(data.rows.length);
    $('count-matches').textContent=display(data.fixtures);
    $('count-latest').textContent=formatDate(data.dates.at(-1));
    $('count-seasons').textContent=display(new Set(data.rows.map(r=>r.season)).size);
    $('status').textContent=`${display(data.rows.length)} risultati · ${display(data.fixtures)} partite nel campione`;
    $('dates').textContent=data.dates.length?`Campione: ${formatDate(data.dates[0])} → ${formatDate(data.dates.at(-1))} · Acquisizione: ${new Date(data.updated).toLocaleString('it-IT')}`:'Nessuna partita nel campione selezionato.';
    if(data.warnings?.length) {
      $('data-warnings').textContent=`${data.warnings.length} avviso/i di qualità nell’archivio. I dati incoerenti vengono esclusi; consulta la documentazione per i dettagli.`;
      const link=document.createElement('a');link.href='/documentation#qualita';link.textContent=' Vedi controlli ↗';$('data-warnings').append(link);$('data-warnings').hidden=false;
    }
    $('docs-link').href='/documentation'+($('league').value?'?league='+encodeURIComponent($('league').value):'');
    renderTable();
  } catch(error) {
    if(mine===generation && error.name!=='AbortError') {
      $('status').textContent=error.message;
      const p=document.createElement('p');p.className='empty';p.textContent='Impossibile caricare i dati. Usa “Rileggi archivio” per riprovare.';$('table').replaceChildren(p);
    }
  } finally {if(mine===generation){$('reload').disabled=false;$('table').setAttribute('aria-busy','false');}}
}

document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{
  if($('kind').value===button.dataset.view)return;
  clearTimeout(debounce);$('kind').value=button.dataset.view;$('search').value='';updateView();refresh();
}));
ids.filter(id=>!['kind','search'].includes(id)).forEach(id=>$(id).addEventListener('change',()=>{
  clearTimeout(debounce);
  if(id==='league')$('team').value='';
  if(id==='min_minutes') {
    const minutes=Number($('min_minutes').value);
    $('min_minutes').value=String(Number.isFinite(minutes)?Math.max(0,Math.min(100000,Math.floor(minutes))):0);
  }
  updateView();refresh();
}));
$('reset').addEventListener('click',()=>{
  clearTimeout(debounce);for(const id of ['league','season','team','search'])$(id).value='';
  $('min_minutes').value='0';$('last_n').value='0';$('sort').value='total';$('metric').value=$('kind').value==='players'?'shots-on-target':'goals';updateView();refresh();
});
$('search').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(refresh,250);});
$('min_minutes').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(refresh,400);});
$('layout').addEventListener('change',renderTable);
$('prev').addEventListener('click',()=>{page--;renderTable();$('table').scrollTop=0;});
$('next').addEventListener('click',()=>{page++;renderTable();$('table').scrollTop=0;});
$('reload').addEventListener('click',()=>{clearTimeout(debounce);refresh();});
updateView();refresh();
