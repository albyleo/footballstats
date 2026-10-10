const ids = ['kind','metric','league','season','min_minutes','team','search','last_n','sort'];
let generation = 0, page = 0, latest = null, debounce;
const size = 30;
const $ = id => document.getElementById(id);
const display = value => value == null ? '—' : typeof value === 'number' ? value.toLocaleString('it-IT') : String(value);
function cell(row, tag, value, note) {
  const e=document.createElement(tag);e.textContent=display(value);
  if(note){const small=document.createElement('small');small.textContent=note;e.append(small);}
  row.append(e);return e;
}
function options(id, values){
  const select=$(id), previous=select.value, placeholder=select.options[0].textContent;
  select.replaceChildren(new Option(placeholder,''));
  values.forEach(value=>select.add(new Option(value,value)));
  select.value=values.includes(previous)?previous:'';
}
function renderTable(){
  if(!latest)return;
  const player=$('kind').value==='players', detail=$('layout').value==='detail';
  const metric=$('metric').value, metricName=latest.metrics[metric];
  const table=document.createElement('table'), head=document.createElement('thead'), header=document.createElement('tr');
  const keys=(player?['shots-on-target','yellowcards','fouls','assists','goals']:['goals','first-half-goals','shots-on-target','fouls','yellowcards','corners','assists']).filter(k=>latest.metric_coverage[k]>0);
  const columns=detail?
    [player?'Giocatore':'Squadra','Campionato',metricName+' · rilevato',player?'Per 90′ osservati':'Media osservata',player?'Minuti osservati':'Partite con dato','Presenze / partite',player?'Minuti totali':'Ultimi risultati',player?'Da titolare':'Titolari confermati']:
    [player?'Giocatore':'Squadra',player?'Squadra':'Campionato',...keys.map(k=>latest.metrics[k]),player?'Minuti':'Ultimi risultati','Presenze / partite',player?'Da titolare':'Titolari confermati'];
  columns.forEach(v=>cell(header,'th',v));head.append(header);table.append(head);
  const body=document.createElement('tbody');
  page=Math.min(page,Math.max(0,Math.ceil(latest.rows.length/size)-1));
  for(const row of latest.rows.slice(page*size,(page+1)*size)){
    const tr=document.createElement('tr');
    cell(tr,'td',row.name,player&&detail?row.team:null);
    cell(tr,'td',player&&!detail?row.team:row.league,player&&!detail?row.league:`${row.season} · ${row.provider}`);
    if(detail){
      cell(tr,'td',row.total,`${row.covered}/${row.matches} con dato`);
      cell(tr,'td',player?row.per90:row.per_match,row.covered<row.matches?'Copertura parziale':null);
      cell(tr,'td',player?row.paired_minutes:row.covered);
      cell(tr,'td',row.matches);
      cell(tr,'td',player?row.minutes:row.form.map(v=>v||'—').join(' '));
    }else{
      keys.forEach(k=>cell(tr,'td',row.totals[k],`${row.coverage[k]}/${row.matches} con dato`));
      cell(tr,'td',player?row.minutes:row.form.map(v=>v||'—').join(' '));
      cell(tr,'td',row.matches);
    }
    cell(tr,'td',player?row.starts:row.same_starters==null?null:`${row.same_starters}/11`);
    body.append(tr);
  }
  table.append(body);$('table').replaceChildren(table);
  if(!latest.rows.length){const p=document.createElement('p');p.className='empty';p.textContent=player&&latest.catalog.find(c=>c.name===$('league').value)?.scope==='teams'?'Per questo campionato il feed fornisce solo dati di squadra. Seleziona la vista Squadre.':'Nessuna riga per questi filtri. Prova a ridurre i minuti minimi o cambiare squadra.';$('table').append(p);}
  $('pagination').textContent=`${latest.rows.length? page*size+1:0}–${Math.min((page+1)*size,latest.rows.length)} di ${latest.rows.length}`;
  $('prev').disabled=page===0;$('next').disabled=(page+1)*size>=latest.rows.length;
  const known=latest.rows.filter(r=>r.covered>0).length;
  $('quality').textContent=`Ordine: ${$('sort').selectedOptions[0].textContent} · ${metricName}. ${known}/${latest.rows.length} righe hanno almeno un valore per questa statistica. ${Number($('last_n').value)?'Periodo limitato alle ultime '+$('last_n').value+' presenze/partite caricate.':''}`;
}
async function refresh(){
  const mine=++generation;
  const params=new URLSearchParams(ids.map(id=>[id,$(id).value]));
  $('status').textContent='Caricamento dati locali…';
  $('reload').disabled=true;
  try{
    const response=await fetch('/api/providers/report?'+params,{cache:'no-cache'});
    const data=await response.json();if(mine!==generation)return;
    if(!response.ok)throw new Error(data.error||'Errore caricamento');
    for(const option of $('metric').options){
      const unavailable=($('kind').value==='players'&&option.value==='first-half-goals')||!data.metric_coverage[option.value];
      option.disabled=unavailable;
      option.textContent=data.metrics[option.value]+(unavailable?' · non disponibile':'');
    }
    if($('metric').selectedOptions[0].disabled){
      const first=[...$('metric').options].find(o=>!o.disabled);
      if(first){$('metric').value=first.value;return refresh();}
    }
    latest=data;page=0;
    options('league',data.leagues);options('season',data.seasons);options('team',data.teams);
    $('catalog').replaceChildren();
    for(const entry of data.catalog){
      const card=document.createElement('div');card.className='coverage-card';
      const name=document.createElement('div');name.textContent=`${entry.country} · ${entry.name}`;
      const count=document.createElement('strong');count.textContent=`${entry.matches} partite`;
      const info=document.createElement('small');info.textContent=entry.matches?`${entry.teams} squadre · ${entry.scope==='teams'?'solo squadre':entry.players+' giocatori'} · ${entry.season||'—'}`:`Accessibile · nessuna partita caricata${entry.season?' · '+entry.season:''}`;
      const source=document.createElement('p');source.className='muted';source.textContent=`${entry.provider} · ultima partita: ${entry.latest_match||'—'}`;
      card.append(name,count,info,source);$('catalog').append(card);
    }
    $('sync').textContent=data.sync?`Ultima acquisizione Sportmonks: ${data.sync.start} → ${data.sync.end} · ${data.sync.fixtures} partite · ${data.sync.network_requests} chiamate · ${data.sync.complete?'tutte le pagine ricevute':'acquisizione parziale'}`:'';
    $('status').textContent=`${data.fixtures} partite nel filtro · ${data.rows.length} righe · archivio: ${data.total_teams} squadre / ${data.total_players} giocatori`;
    $('dates').textContent=data.dates.length?`Archivio filtrato: ${data.dates[0]} → ${data.dates.at(-1)} · Dati acquisiti: ${new Date(data.updated).toLocaleString('it-IT')}`:'Nessuna partita conclusa scaricata.';
    $('availability').textContent=data.availability;
    const audits=data.halftime_audit||[], verified=audits.filter(a=>a.status.startsWith('verified')).length;
    const sourceOnly=audits.filter(a=>a.status==='source_only').length, conflicts=audits.filter(a=>a.status==='conflict').length;
    $('half-summary').textContent=`${verified} partite: HT concordante con gli eventi · ${sourceOnly}: fonte CSV, senza eventi · ${conflicts}: conflitti HT · ${audits.filter(a=>a.status==='verified_with_warning').length}: avvisi su altri campi. Controllo sull’archivio filtrato, prima del limite ultime 5/10.`;
    const auditTable=document.createElement('table'), auditHead=document.createElement('tr');
    ['Data / partita','Fonte','Intervallo','Finale','HT dagli eventi','Esito'].forEach(v=>cell(auditHead,'th',v));
    auditTable.append(auditHead);
    const score=v=>v?v.map(display).join('–'):'—';
    const labels={verified:'Concordante',verified_with_warning:'HT concordante · avviso',source_only:'Fonte CSV · senza eventi',unverified:'Non verificabile',conflict:'Conflitto · escluso'};
    for(const audit of audits){const tr=document.createElement('tr');cell(tr,'td',audit.match,audit.date);cell(tr,'td',audit.provider);cell(tr,'td',score(audit.ht));cell(tr,'td',score(audit.ft));cell(tr,'td',score(audit.events_ht));cell(tr,'td',labels[audit.status],audit.issues.join('; '));auditTable.append(tr);}
    $('half-table').replaceChildren(auditTable);
    renderTable();
  }catch(error){if(mine===generation){latest=null;$('status').textContent=error.message;$('table').replaceChildren();$('pagination').textContent='';}}
  finally{if(mine===generation)$('reload').disabled=false;}
}
ids.filter(id=>id!=='search').forEach(id=>$(id).addEventListener('change',()=>{
  if(id==='league'){
    $('team').value='';
    if(latest?.catalog.find(c=>c.name===$('league').value)?.scope==='teams')$('kind').value='teams';
  }
  const player=$('kind').value==='players';
  $('min_minutes').disabled=!player;
  $('sort').querySelector('[value="per90"]').disabled=!player;
  $('sort').querySelector('[value="minutes"]').disabled=!player;
  $('metric').querySelector('[value="first-half-goals"]').disabled=player;
  if(!player&&['per90','minutes'].includes($('sort').value))$('sort').value='total';
  if(player&&$('metric').value==='first-half-goals')$('metric').value='goals';
  refresh();
}));
$('search').addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(refresh,250);});
$('layout').addEventListener('change',renderTable);
$('prev').addEventListener('click',()=>{page--;renderTable();});
$('next').addEventListener('click',()=>{page++;renderTable();});
$('reload').addEventListener('click',refresh);
$('metric').querySelector('[value="first-half-goals"]').disabled=true;
refresh();
