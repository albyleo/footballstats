const $=id=>document.getElementById(id);
const fields=['kind','league','season','entity','compare','metric','venue','last_n','basis','threshold'];
const fmt=v=>v==null?'—':typeof v==='number'?v.toLocaleString('it-IT',{maximumFractionDigits:2}):String(v);
const date=v=>v?v.slice(0,10).split('-').reverse().join('.'):'—';
const ratioKeys=['xg-per-shot','on-target-share','xga-per-shot'];
let data=null, generation=0, pending, timer;
function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=fmt(text);if(className)node.className=className;return node;}
function options(id,items,value,empty=false){const select=$(id);select.replaceChildren();if(empty)select.add(new Option('Nessun confronto',''));for(const item of items)select.add(new Option(item.label,item.value));select.value=value;}
function kpi(label,value,note){const node=el('div',null,'kpi');node.append(el('span',label),el('strong',fmt(value)),el('small',note));return node;}
function table(headers,rows){const t=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');for(const h of headers){const th=el('th',h);th.scope='col';tr.append(th);}head.append(tr);for(const row of rows){const line=el('tr');for(const v of row){const c=el('td',fmt(v));c.dataset.excel=JSON.stringify(v??null);line.append(c);}body.append(line);}t.append(head,body);return t;}
function coverage(s){return `${s.covered}/${s.matches} con dato`;}
function alignBasis(){const unsupported=$('kind').value==='teams'||ratioKeys.includes($('metric').value);$('basis').options[1].disabled=unsupported;if(unsupported)$('basis').value='match';}
function svg(tag,attrs,text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=text;return n;}
function chart(profile){
  const points=profile.series,valid=points.flatMap(p=>[p.value,p.ma5,p.ma10]).filter(v=>v!=null);
  $('chart').replaceChildren();if(!valid.length){$('chart').append(el('p','Nessun valore disponibile per disegnare il grafico.','notice'));return;}
  const W=960,H=300,L=64,R=28,T=20,B=42;
  const low=Math.min(0,...valid),high=Math.max(...valid,low+1),x=i=>L+i*(W-L-R)/Math.max(1,points.length-1),y=v=>T+(high-v)*(H-T-B)/(high-low);
  const plot=svg('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${data.metrics[data.filters.metric]} partita per partita di ${profile.name}. Valori e medie disponibili nella tabella sottostante.`});
  for(let i=0;i<5;i++){const v=low+(high-low)*i/4;plot.append(svg('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),stroke:'#303b28'}),svg('text',{x:L-10,y:y(v)+4,'text-anchor':'end'},fmt(v)));}
  const ticks=[...new Set([0,Math.floor((points.length-1)/2),points.length-1])];
  for(const i of ticks)plot.append(svg('text',{x:x(i),y:H-12,'text-anchor':i===0?'start':i===points.length-1?'end':'middle'},date(points[i].date)));
  for(const [key,color] of [['value','#c7f54e'],['ma5','#83ccf5'],['ma10','#efbf79']]){
    let d='',connected=false;points.forEach((p,i)=>{if(p[key]==null){connected=false;return;}d+=`${connected?'L':'M'}${x(i)},${y(p[key])} `;connected=true;});
    plot.append(svg('path',{d,fill:'none',stroke:color,'stroke-width':key==='value'?2:3}));
    if(key!=='value')points.forEach((p,i)=>{if(p[key]!=null){const dot=svg('circle',{cx:x(i),cy:y(p[key]),r:3,fill:color});dot.append(svg('title',{},`${date(p.date)} · ${key==='ma5'?'Media 5':'Media 10'} · ${fmt(p[key])}`));plot.append(dot);}});
  }
  points.forEach((p,i)=>{if(p.value==null)return;const dot=svg('circle',{cx:x(i),cy:y(p.value),r:4,fill:'#c7f54e'});dot.append(svg('title',{},`${date(p.date)} · ${p.opponent||'Avversario non disponibile'} · ${fmt(p.value)}`));plot.append(dot);});
  $('chart').append(plot);
}
function matchRows(profile){return profile.series.map(p=>[date(p.date),p.opponent||'—',p.venue==='home'?'Casa':p.venue==='away'?'Trasferta':'—',p.minutes,p.value,p.ma5,p.ma10]);}
const matchHeaders=['Data','Avversario','Campo','Minuti','Valore','Media mobile 5','Media mobile 10'];
function nextFixture(p){const n=p.next_fixture;return n?`${n.opponent} · ${date(n.date)} · ${n.venue==='home'?'Casa':'Trasferta'}`:'Non disponibile nel calendario salvato';}
function comparisonRows(a,b){const fields=[['Media',s=>s.mean],['Mediana',s=>s.median],['Copertura',coverage],['Deviazione standard',s=>s.stddev],['Minimo',s=>s.minimum],['Massimo',s=>s.maximum],['Frequenza ≥ soglia',s=>`${s.successes}/${s.covered}`]];return [...(data.filters.kind==='teams'?[['Prossimo avversario (campionato)',nextFixture(a),nextFixture(b)]]:[]),...fields.map(([label,get])=>[label,get(a.summary),get(b.summary)])];}
function render(){
  const f=data.filters,a=data.primary,b=data.comparison;
  options('league',data.leagues.map(x=>({label:x,value:x})),f.league);
  options('season',data.seasons.map(x=>({label:x,value:x})),f.season);
  const entities=data.entities.map(x=>({value:x.id,label:f.kind==='players'?`${x.name} · ${x.team}`:x.name}));
  options('entity',entities,f.entity);options('compare',entities,f.compare,true);
  options('metric',Object.entries(data.metrics).map(([value,label])=>({value,label})),f.metric);alignBasis();
  $('content').hidden=!a;$('export').disabled=!a;
  if(!a){$('status').textContent='Nessuna osservazione disponibile per questa selezione.';return;}
  const s=a.summary,unit=ratioKeys.includes(f.metric)?'rapporto aggregato':f.basis==='per90'?'per 90′':'per partita/presenza';
  $('scope').textContent=f.kind==='teams'?'SQUADRA':'GIOCATORE';$('title').textContent=a.name;
  $('subtitle').textContent=`${a.team} · ${a.league} · ${a.season} · ${data.metrics[f.metric]} (${unit})`;
  $('next-fixture').hidden=f.kind!=='teams';$('next-fixture').textContent='Prossimo avversario (campionato): '+nextFixture(a);
  $('freshness').textContent=`Ultima partita in archivio: ${date(a.latest)}`;
  $('status').textContent=`${coverage(s)} · dati salvati · nessuna chiamata ai feed`;
  $('kpis').replaceChildren(kpi('Periodo selezionato',s.mean,coverage(s)),kpi('Stagione / campo selezionato',a.season_summary.mean,coverage(a.season_summary)),kpi('Ultime 5 caricate',a.last5.mean,coverage(a.last5)),kpi('Ultime 10 caricate',a.last10.mean,coverage(a.last10)));
  MyComboMatchup.render($('matchup'),data.matchup,f);
  $('chart-note').textContent=`${a.series.length} partite/presenze caricate · ${$('venue').selectedOptions[0].textContent} · ${unit}`;chart(a);
  $('splits').replaceChildren(...[['home','Casa'],['away','Trasferta']].map(([key,label])=>kpi(label,a.splits[key].mean,coverage(a.splits[key]))));
  $('unknown').textContent=a.unknown_venue?`${a.unknown_venue} osservazioni senza campo noto: escluse dai confronti casa/trasferta.`:'Campo casa/trasferta disponibile per tutte le osservazioni della scheda.';
  $('quality').replaceChildren();for(const [key,item] of Object.entries(a.quality)){const row=el('div',null,'quality-row'),label=el('div',data.metrics[key]);label.append(el('small',`${item.covered}/${s.matches} partite abbinate`));row.append(label,el('strong',fmt(item.value)+(key==='on-target-share'&&item.value!=null?'%':'')));$('quality').append(row);}
  $('comparison').replaceChildren(b?table(['Indicatore',a.name,b.name],comparisonRows(a,b)):el('p','Scegli un secondo profilo nel filtro “Confronta con”.','muted'));
  const frequency=s.frequency==null?'—':`${fmt(s.frequency*100)}%`;
  $('distribution').replaceChildren(kpi(`Valore ≥ ${fmt(f.threshold)}`,frequency,`${s.successes} su ${s.covered} osservazioni valide`),kpi('Mediana',s.median,unit),kpi('Deviazione standard',s.stddev,s.covered<5?'Campione ridotto: meno di 5 osservazioni':'Dispersione nel campione'),kpi('Intervallo osservato',`${fmt(s.minimum)} – ${fmt(s.maximum)}`,coverage(s)));
  $('matches').replaceChildren(table(matchHeaders,matchRows(a)));
  $('warnings').hidden=!data.warnings.length;$('warnings').textContent=data.warnings.join(' · ');
  const params=new URLSearchParams();for(const [k,v] of Object.entries(f))if(v!==''&&v!=null)params.set(k,String(v));history.replaceState(null,'','/premium?'+params);
}
async function refresh(reset=''){
  if(reset==='kind'||reset==='league'){$('season').value='';$('entity').value='';$('compare').value='';}
  if(reset==='season'){$('entity').value='';$('compare').value='';}
  if(reset==='kind')$('metric').value='xg';alignBasis();
  const mine=++generation;pending?.abort();pending=new AbortController();
  $('status').textContent='Calcolo delle analisi…';$('export').disabled=true;$('content').hidden=true;
  const params=new URLSearchParams();for(const id of fields)params.set(id,$(id).value);
  try{const response=await fetch('/api/premium/report?'+params,{signal:pending.signal,cache:'no-cache'});if(!response.ok){const message=await response.json();throw new Error(message.error||'Analisi non disponibili.');}const result=await response.json();if(mine!==generation)return;data=result;render();}
  catch(error){if(mine===generation&&error.name!=='AbortError'){$('status').textContent=error.message||'Archivio non disponibile. Riprova.';data=null;}}
}
for(const id of fields){$(id).addEventListener(id==='threshold'?'input':'change',()=>{clearTimeout(timer);timer=setTimeout(()=>refresh(id),id==='threshold'?400:0);});}
$('reload').addEventListener('click',()=>refresh());
$('export').addEventListener('click',()=>{if(!data?.primary)return;const a=data.primary,f=data.filters;const rows=[['Premium · anteprima gratuita'],[a.name,a.league,a.season],['Metrica',data.metrics[f.metric]],['Campo',f.venue,'Ultime N',f.last_n,'Base',f.basis,'Soglia ≥',f.threshold],['Ultima partita',a.latest],['Prossimo avversario (campionato)',f.kind==='teams'?nextFixture(a):'—'],['Media','Mediana','Copertura','Frequenza'],[a.summary.mean,a.summary.median,coverage(a.summary),a.summary.frequency],['Stagione',a.season_summary.mean,coverage(a.season_summary)],['Casa / stagione',a.splits.home.mean,coverage(a.splits.home)],['Trasferta / stagione',a.splits.away.mean,coverage(a.splits.away)],...Object.entries(a.quality).map(([k,v])=>[data.metrics[k],v.value,v.covered]),[],...matchRows(a)];rows.splice(rows.length-a.series.length,0,matchHeaders);if(data.comparison){rows.push([],['Confronto',a.name,data.comparison.name],...comparisonRows(a,data.comparison),[],['Partite del confronto'],matchHeaders,...matchRows(data.comparison));}rows.push(...MyComboMatchup.exportRows(data.matchup));exportTable($('export'),table(['MyCombo srl / Analytics'],rows),'mycombo-premium-analisi');});
const initial=new URLSearchParams(location.search);for(const id of fields){const v=initial.get(id);if(v!=null&&v.length<=128){if(['league','season','entity','compare','metric'].includes(id))$(id).add(new Option(v,v));$(id).value=v;}}
refresh();

