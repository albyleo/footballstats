const $ = id => document.getElementById(id);
let report = null;
function cell(row, tag, value, note) {
  const e=document.createElement(tag);e.textContent=value??'—';if(tag==='th')e.scope='col';
  if(note){const small=document.createElement('small');small.textContent=note;e.append(small);}row.append(e);
}
// Public labels are categories. Original provider identifiers remain in the archive.
const sourceLabel = provider => /sportmonks/i.test(provider) ? 'Sportmonks' : /api.?football/i.test(provider) ? 'API-Football' : 'Archivio integrativo';
const qualityLabel = warning => warning.replace(/Understat/gi,'Archivio integrativo');
function renderAudit() {
  const audits=report?.halftime_audit||[];
  const verified=audits.filter(a=>a.status.startsWith('verified')).length;
  $('half-summary').textContent=`${verified} partite concordanti con gli eventi · ${audits.filter(a=>a.status==='source_only').length} con campi HT senza eventi · ${audits.filter(a=>a.status==='conflict').length} conflitti esclusi · ${audits.filter(a=>a.status==='verified_with_warning').length} avvisi su altri campi.`;
  const table=document.createElement('table'), head=document.createElement('thead'), header=document.createElement('tr');
  ['Data / partita','Fonte','Intervallo','Finale','HT dagli eventi','Esito'].forEach(value=>cell(header,'th',value));head.append(header);table.append(head);
  const body=document.createElement('tbody'), score=v=>v?v.map(n=>n??'—').join('–'):'—';
  const labels={verified:'Concordante',verified_with_warning:'HT concordante · avviso',source_only:'Campi HT · senza eventi',unverified:'Non verificabile',conflict:'Conflitto · escluso'};
  for(const audit of audits){const row=document.createElement('tr');cell(row,'td',audit.match,audit.date);cell(row,'td',sourceLabel(audit.provider));cell(row,'td',score(audit.ht));cell(row,'td',score(audit.ft));cell(row,'td',score(audit.events_ht));cell(row,'td',labels[audit.status],audit.issues.map(qualityLabel).join('; '));body.append(row);}
  table.append(body);$('half-table').replaceChildren(table);
  if(!audits.length){const p=document.createElement('p');p.className='empty';p.textContent='Nessun punteggio HT disponibile per questo campionato.';$('half-table').replaceChildren(p);}
}
// Audit filtering requests another cached local report; it never contacts a feed.
let auditGeneration=0;
async function loadAudit() {
  const mine=++auditGeneration, league=$('audit-league').value;
  $('half-summary').textContent='Caricamento controlli…';$('half-table').replaceChildren();
  try {
    const response=await fetch('/api/providers/report?kind=teams&metric=first-half-goals&league='+encodeURIComponent(league),{cache:'no-cache'});
    if(!response.ok)throw new Error();
    const data=await response.json();if(mine!==auditGeneration)return;
    report=data;renderAudit();
  }catch{if(mine===auditGeneration)$('half-summary').textContent='Controlli non disponibili. Ricarica la pagina per riprovare.';}
}
async function load() {
  try {
    const response=await fetch('/api/providers/report?kind=teams&metric=first-half-goals',{cache:'no-cache'});
    if(!response.ok)throw new Error();const data=await response.json();report=data;
    $('docs-status').textContent=`${data.fixtures} partite distinte · ${data.total_teams} squadre · ${data.total_players} giocatori con minuti nell’archivio.`;
    for(const entry of data.catalog) {
      const card=document.createElement('article');card.className='coverage-card';
      const title=document.createElement('div');title.textContent=`${entry.country} · ${entry.name}`;
      const count=document.createElement('strong');count.textContent=`${entry.matches} partite`;
      const info=document.createElement('small');info.textContent=`${entry.teams} squadre · ${entry.players} giocatori · ${entry.season||'Stagione non disponibile'}`;
      const dates=document.createElement('p');dates.textContent=`${sourceLabel(entry.provider)} · ultima partita: ${entry.latest_match||'—'}`;
      if(entry.player_matches!=null)dates.textContent+=` · presenze individuali su ${entry.player_matches} partite · HT su ${entry.ht_matches}/${entry.matches}`;
      card.append(title,count,info,dates);$('catalog').append(card);
    }
    $('sync').textContent=data.sync?`Acquisizione Sportmonks: ${data.sync.start} → ${data.sync.end}. ${data.sync.fixtures} partite; ${data.sync.complete?'tutte le pagine ricevute':'acquisizione parziale'}.`:'';
    $('data-warnings').textContent=data.warnings?.length?data.warnings.map(qualityLabel).join(' · '):'Nessun avviso registrato nell’archivio corrente.';
    data.leagues.forEach(league=>$('audit-league').add(new Option(league,league)));
    const requested=new URLSearchParams(location.search).get('league');
    if(data.leagues.includes(requested)){$('audit-league').value=requested;await loadAudit();}else renderAudit();
  }catch{$('docs-status').textContent='Copertura non disponibile: ricarica la pagina per riprovare. La metodologia rimane consultabile.';$('half-summary').textContent='Controlli non disponibili.';$('data-warnings').textContent='Stato dei controlli non disponibile.';}
}
$('audit-league').addEventListener('change',loadAudit);
load();
