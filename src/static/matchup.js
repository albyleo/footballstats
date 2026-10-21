/* Saved observations for the upcoming fixture; historical frequencies only. */
window.MyComboMatchup = (() => {
  const fmt = value => value == null ? '—' : Number(value).toLocaleString('it-IT', {maximumFractionDigits:2});
  const date = value => value ? value.slice(0,10).split('-').reverse().join('.') : '—';
  const percent = value => value == null ? '—' : `${(value*100).toLocaleString('it-IT',{maximumFractionDigits:1})}%`;
  const coverage = value => `${value.covered}/${value.matches} con dato`;
  const delta = value => value == null ? '—' : `${value>0?'+':''}${fmt(value)}`;
  const checkedAt = value => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleString('it-IT', {dateStyle:'short',timeStyle:'short',timeZone:'Europe/Rome'})+' (Italia)' : '—';
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function rate(item) {
    const element = node('div',null,'matchup-rate');
    element.append(node('strong',fmt(item.mean)), node('small',coverage(item)));
    element.append(node('small',`Campionato: ${fmt(item.baseline.mean)} · ${coverage(item.baseline)}`));
    element.append(node('span',`Differenza: ${delta(item.difference)}`,'matchup-delta'));
    return element;
  }
  function direction(value) {
    const card = node('section',null,`matchup-direction ${value.side}`);
    card.append(node('p',value.side==='home'?'ATTACCO CASA / DIFESA OSPITI':'ATTACCO OSPITI / DIFESA CASA','eyebrow'));
    card.append(node('h3',`${value.attacker} / ${value.defender}`));
    const headings = node('div',null,'matchup-metric matchup-headings');
    headings.append(node('span','Media / partita'),node('span','Prodotti'),node('span','Concessi dall’avversario'));
    card.append(headings);
    for (const metric of value.metrics) {
      const row = node('div',null,'matchup-metric');
      row.append(node('span',metric.label,'matchup-metric-name'),rate(metric.attack),rate(metric.conceded));
      card.append(row);
    }
    return card;
  }
  function frequency(profile) {
    const f = profile.goal_frequencies, card = node('section',null,`matchup-frequency ${profile.venue}`);
    card.append(node('h3',`${profile.name} · ${profile.sample_label}`));
    card.append(node('p',`Gol segnati · ${coverage(f)}`,'muted'));
    if (!f.covered) {
      card.append(node('p','Gol non disponibili per questo campione.','matchup-empty'));
      return card;
    }
    const chart = node('div',null,'matchup-bars');
    chart.setAttribute('role','list');chart.setAttribute('aria-label',`Frequenze storiche dei gol di ${profile.name}`);
    for (const bin of f.bins) {
      const item = node('div',null,'matchup-bin');item.setAttribute('role','listitem');
      item.setAttribute('aria-label',`${bin.label} gol: ${bin.count} su ${f.covered} partite, ${percent(bin.frequency)}`);
      const track = node('div',null,'matchup-bar-track'), bar = node('div',null,'matchup-bar');
      track.setAttribute('aria-hidden','true');bar.style.height=`${bin.frequency*100}%`;track.append(bar);
      item.append(node('strong',percent(bin.frequency)),track,node('span',`${bin.label} gol`),node('small',`${bin.count}/${f.covered}`));
      chart.append(item);
    }
    card.append(chart);
    return card;
  }
  function fact(label, value, note) {
    const row=node('div',null,'matchup-fact');
    row.append(node('span',label),node('strong',value));
    if(note)row.append(node('small',note));
    return row;
  }
  function contextCard(profile) {
    const card=node('section',null,`matchup-context-card ${profile.venue}`);
    card.append(node('h3',`${profile.name} · ${profile.sample_label}`));
    for(const m of profile.quality)card.append(fact(m.label,fmt(m.mean)+(m.mean==null?'':m.unit),`${coverage(m)} · rapporto su partite abbinate`));
    for(const m of profile.context_metrics)card.append(fact(m.label+' / partita',fmt(m.mean),`${coverage(m)} · campionato ${fmt(m.baseline.mean)} (${coverage(m.baseline)}) · scarto ${delta(m.difference)}`));
    for(const [key,label] of [['clean_sheets','Partite senza subire gol'],['scoreless','Partite senza segnare']]) {
      const item=profile[key];card.append(fact(label,item.covered?`${item.count}/${item.covered}`:'—',coverage(item)));
    }
    return card;
  }
  function squadCard(profile) {
    const card=node('section',null,`matchup-squad ${profile.venue}`), form=profile.recent_form, a=profile.availability;
    card.append(node('h3',profile.name),node('p','Ultime 5 partite caricate · casa + trasferta','muted'));
    const results=node('div',null,'matchup-results');results.setAttribute('aria-label','Risultati dal meno al più recente');
    for(const m of form.matches){const chip=node('span',m.result||'—',`matchup-result result-${m.result||'unknown'}`);chip.title=`${date(m.date)} · ${m.opponent||'Avversario non disponibile'} · ${fmt(m.goals)}–${fmt(m.conceded)}`;results.append(chip);}
    card.append(results,fact('Punti / partita',fmt(form.points_per_match),`${form.covered}/${form.matches.length} risultati completi · V vittoria, P pareggio, S sconfitta`));
    card.append(fact('Gol fatti / subiti per partita',`${fmt(form.goals.mean)} / ${fmt(form.conceded.mean)}`,`Gol fatti: ${coverage(form.goals)} · subiti: ${coverage(form.conceded)}`));
    card.append(fact('Partite caricate negli ultimi 14 giorni',fmt(profile.activity.matches_last_14_days),'Solo campionato: coppe e nazionali escluse. Non misura la fatica.'));
    card.append(fact('Distanza dall’ultima gara caricata',profile.activity.days_to_fixture==null?'—':`${profile.activity.days_to_fixture} giorni`,`${date(profile.activity.last_match)} → prossima partita. Non sono giorni di riposo verificati.`));
    const lineup=profile.lineup;
    card.append(fact('Continuità della formazione',lineup?.latest_common==null?'—':`${lineup.latest_common}/11 nell’ultima`,lineup?`Base stagionale: ${lineup.sample}/${lineup.season_matches} formazioni complete · ultima gara ${date(lineup.latest_date)}`:'Formazioni non disponibili.'));
    const heading=node('div',null,'matchup-roster-heading');
    heading.append(node('h4','Disponibilità della rosa'),node('span',({missing:'NON DISPONIBILE',stale:'DA RICONFERMARE',reported:'SEGNALAZIONI RECENTI',none_reported:'NESSUNA SEGNALAZIONE'})[a.status]||'NON DISPONIBILE',`matchup-status status-${a.status}`));
    card.append(heading,node('p',a.message,'matchup-context'));
    if(a.checked_at)card.append(node('p',`${a.source} · rilevata ${checkedAt(a.checked_at)} · riferita a questo incontro`,'matchup-source'));
    if(a.absences.length) {
      const list=node('ul',null,'matchup-absences');
      for(const p of a.absences){const item=node('li');item.append(node('strong',p.name),node('span',`${({injury:'Infortunio',suspension:'Squalifica',unavailable:'Indisponibilità'})[p.category]||'Indisponibilità'} · ${p.reason}`));
        if(p.in_reference)item.append(node('small','Presente nella base titolare stagionale'));
        if(p.expected_end)item.append(node('small',`Fine periodo indicata dal feed: ${date(p.expected_end)} · rientro non confermato`));
        list.append(item);}
      card.append(list);
    }
    if(a.reference_absent!=null)card.append(node('p',`${a.reference_absent}/11 giocatori della base segnalati indisponibili. Gli altri non sono automaticamente confermati disponibili.`,'matchup-context'));
    if(lineup?.reference.length){const detail=node('details',null,'matchup-reference');detail.append(node('summary','Base titolare stagionale'));
      const list=node('ul');lineup.reference.forEach(p=>list.append(node('li',`${p.name} · ${p.starts} partenze da titolare`)));detail.append(list);
      if(lineup.tie)detail.append(node('p','Parità di titolarità al limite della base: non è un undici ufficiale.'));
      card.append(detail);}
    card.append(node('p','La condizione fisica non è misurata: rendimento, continuità e segnalazioni sulle assenze sono indicatori distinti.','matchup-context'));
    return card;
  }
  function render(container, report, filters) {
    container.replaceChildren();container.hidden=filters.kind!=='teams'||!report;
    if (container.hidden || !report) return;
    container.append(node('p','PROSSIMO INCONTRO / CONFRONTO STATISTICO','eyebrow'));
    if (report.status==='unavailable') {
      container.append(node('h2','Prossimo avversario'),node('p',report.reason,'muted'));
      return;
    }
    const header = node('div',null,'matchup-heading');
    header.append(node('h2',`${report.home.name} — ${report.away.name}`),node('span','DATI OSSERVATI','pill'));
    container.append(header,node('p',`${date(report.date)} · ${report.league} · ${report.season}`,'muted'));
    const nav=node('nav',null,'matchup-nav');nav.setAttribute('aria-label','Sezioni del confronto');
    for(const [id,label] of [['matchup-duels','Attacco e difesa'],['matchup-indicators','Altri indicatori'],['matchup-roster','Rendimento e rosa'],['matchup-goals','Gol storici']]){const link=node('a',label);link.href='#'+id;nav.append(link);}container.append(nav);
    const period = report.last_n ? `Ultime ${report.last_n} partite del campione selezionato` : 'Intera stagione caricata del campione selezionato';
    container.append(node('p',`${period}. Si usano le gare di campionato contro tutti gli avversari, non soltanto gli scontri diretti. Sotto 5 gare nello stesso campo si includono casa e trasferta. Questa sezione è indipendente dai filtri Statistica, Campo e Normalizzazione.`,'matchup-context'));
    const samples = node('div',null,'matchup-samples');
    for (const side of ['home','away']) {
      const p = report[side], card = node('div',null,`matchup-sample ${side}`);
      card.append(node('span',side==='home'?'CASA':'OSPITI','eyebrow'),node('h3',p.name));
      card.append(node('p',`${p.matches} partite · ${p.sample_label} · ${p.season_venue_matches} stagionali nel campo del prossimo incontro`));
      card.append(node('small',p.latest?`${date(p.first)} → ${date(p.latest)}`:'Nessuna partita caricata per questo campione'));
      if (p.entity) {
        const link = node('a','Apri scheda squadra ↗');
        link.href='/premium?'+new URLSearchParams({kind:'teams',league:report.league,season:report.season,
          entity:p.entity,metric:filters.metric,last_n:String(report.last_n),venue:'all',basis:'match'});
        card.append(link);
      }
      samples.append(card);
    }
    container.append(samples);
    if (report.notes.length) container.append(node('p',report.notes.join(' '),'matchup-note'));
    const comparisons = node('div',null,'matchup-directions');comparisons.id='matchup-duels';
    report.directions.forEach(d=>comparisons.append(direction(d)));container.append(comparisons);
    container.append(node('h3','Qualità, disciplina e risultati','matchup-section-title'),node('p','Stesso campione indicato per ciascuna squadra nel confronto. I rapporti usano solo partite con entrambi i dati.','matchup-context'));
    const context=node('div',null,'matchup-context-grid');context.id='matchup-indicators';context.append(contextCard(report.home),contextCard(report.away));container.append(context);
    container.append(node('h3','Rendimento recente e disponibilità','matchup-section-title'),node('p','Rendimento: ultime 5 gare di campionato, indipendenti dal filtro Periodo. Rosa: segnalazioni del feed per il prossimo incontro, da riconfermare dopo 48 ore.','matchup-context'));
    const squads=node('div',null,'matchup-squads');squads.id='matchup-roster';squads.append(squadCard(report.home),squadCard(report.away));container.append(squads);
    container.append(node('h3','Come si sono distribuiti i gol','matchup-section-title'));
    container.append(node('p','Frequenze delle partite già disputate, non probabilità del prossimo incontro. I dati mancanti non diventano zeri.','matchup-context'));
    const frequencies = node('div',null,'matchup-frequencies');frequencies.id='matchup-goals';
    frequencies.append(frequency(report.home),frequency(report.away));container.append(frequencies);
    const methodology = node('details',null,'matchup-method');
    methodology.append(node('summary','Campione e metodo di lettura'));
    methodology.append(node('p',`Si usano osservazioni anteriori al ${date(report.cutoff_exclusive)} (UTC). Le partite dello stesso giorno sono escluse perché il calendario non fornisce un orario verificato. Le medie del campionato usano tutta la stagione precedente al limite, nello stesso ambito del campione: campo specifico oppure casa + trasferta.`));
    methodology.append(node('p','“Differenza” è la media della squadra meno quella del campionato nello stesso ambito del campione: è uno scarto descrittivo, non una misura di vantaggio predittivo. Non corregge la difficoltà degli avversari, infortuni o formazioni. Un campione piccolo o incompleto può cambiare molto dopo una singola partita.'));
    methodology.append(node('p',`Calendario acquisito: ${date(report.schedule_updated)}. Il confronto usa l’archivio salvato e non scarica dati durante la navigazione.`));
    container.append(methodology);
  }
  function exportRows(report) {
    if (!report) return [];
    if (report.status==='unavailable') return [[],['Prossimo incontro',report.reason]];
    const rows = [[],['Prossimo incontro / confronto descrittivo'],[report.home.name,report.away.name,report.date,report.league,report.season],
      ['Osservazioni anteriori a (UTC)',report.cutoff_exclusive],['Ultime N nel campione (0 = stagione)',report.last_n],
      ['Calendario acquisito',report.schedule_updated||null],['Note',report.notes.join(' ')],
      ['Differenze storiche; nessuna probabilità prevista. Nessuna correzione per difficoltà degli avversari.']];
    for (const d of report.directions) {
      rows.push([],[`${d.attacker} / ${d.defender}`],['Metrica','Prodotti / partita','Copertura attacco','Media campionato attacco','Scarto attacco',
        'Concessi avversario / partita','Copertura difesa','Media campionato difesa','Scarto difesa']);
      for (const m of d.metrics) rows.push([m.label,m.attack.mean,coverage(m.attack),m.attack.baseline.mean,m.attack.difference,
        m.conceded.mean,coverage(m.conceded),m.conceded.baseline.mean,m.conceded.difference]);
    }
    for (const side of ['home','away']) {
      const p=report[side],f=p.goal_frequencies;
      rows.push([],[p.name,'Altri indicatori',p.sample_label],['Indicatore','Valore','Copertura','Unità']);
      p.quality.forEach(m=>rows.push([m.label,m.mean,coverage(m),m.unit]));
      p.context_metrics.forEach(m=>rows.push([m.label,m.mean,coverage(m),'per partita','Media campionato',m.baseline.mean,'Copertura campionato',coverage(m.baseline)]));
      for(const [key,label] of [['clean_sheets','Senza subire gol'],['scoreless','Senza segnare']])rows.push([label,p[key].covered?p[key].count:null,coverage(p[key])]);
      rows.push([],['Rendimento recente: ultime 5, casa + trasferta'],['Punti / partita',p.recent_form.points_per_match,'Risultati completi',p.recent_form.covered],['Data','Avversario','Risultato','Gol fatti','Gol subiti']);
      p.recent_form.matches.forEach(m=>rows.push([m.date,m.opponent,m.result,m.goals,m.conceded]));
      rows.push(['Partite caricate negli ultimi 14 giorni',p.activity.matches_last_14_days],['Distanza ultima gara caricata / prossima partita (giorni)',p.activity.days_to_fixture],['Solo campionato, non giorni di riposo verificati. Condizione fisica non misurata.']);
      const a=p.availability;
      rows.push([],['Disponibilità rosa',a.status,a.message],['Fonte',a.source,'Rilevata (UTC)',a.checked_at],['Base segnalata indisponibile',a.reference_absent,'Dimensione base',a.reference_size],['Giocatore','Categoria','Motivo','Nella base stagionale','Fine periodo indicata (non garantita)']);
      a.absences.forEach(x=>rows.push([x.name,x.category,x.reason,x.in_reference?'Sì':'No',x.expected_end]));
      if(p.lineup)rows.push(['Continuità ultima formazione',p.lineup.latest_common,'Formazioni complete',p.lineup.sample,'Partite stagione',p.lineup.season_matches],['Base stagionale','Titolarità'],...p.lineup.reference.map(x=>[x.name,x.starts]));
      rows.push([],[p.name,p.sample_label,p.first,p.latest],['Frequenze storiche dei gol',coverage(f)],['Gol','Partite','Frequenza storica (0–1)']);
      f.bins.forEach(b=>rows.push([b.label,b.count,b.frequency]));
    }
    return rows;
  }
  return {render,exportRows};
})();
