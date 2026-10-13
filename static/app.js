const $=id=>document.getElementById(id), euro=n=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'}).format(n/100);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let csrf='';
let dataset=sessionStorage.getItem('kassensturz-dataset')==='demo'?'demo':'private', pending=0;
$('dataset').value=dataset;
let state={transactions:[],categories:[]}, editing=null, csvText='', currentView='overview';
const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
$('month').value=today().slice(0,7);
async function api(path,data){
  pending++;$('dataset').disabled=true;
  try {
    const r=await fetch('/api/'+path+'?dataset='+encodeURIComponent(dataset),data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
    if(r.status===401){window.location.replace('/login');throw Error('Bitte anmelden.')}
    if(!r.ok){let msg='Anfrage fehlgeschlagen.';try{msg=(await r.json()).error}catch{}throw Error(msg)}
    return await r.json();
  } finally {pending--;$('dataset').disabled=pending>0}
}
$('dataset').onchange=async()=>{
  if(pending||$('editor').open||$('importDialog').open||$('groupDialog').open){$('dataset').value=dataset;notice('Bitte den aktuellen Vorgang zuerst abschließen oder schließen.');return}
  const previous=dataset;dataset=$('dataset').value;document.querySelector('main').inert=true;
  try{await refresh();sessionStorage.setItem('kassensturz-dataset',dataset);editing=null;csvText='';$('search').value='';$('csv').value='';render();notice(dataset==='demo'?'Datensatz: Demo.':'Datensatz: Privat.')}catch(e){dataset=previous;$('dataset').value=dataset;notice(e.message)}finally{document.querySelector('main').inert=false}
};

function notice(s){$('notice').textContent=s}
async function refresh(){state=await api('data');render()}
function options(selected){selected=selected||state.default_category||'Unkategorisiert';return state.categories.map(c=>`<option ${c===selected?'selected':''}>${esc(c)}</option>`).join('')}
function monthTransactions(){return KassensturzReports.monthView(state.transactions,$('month').value,$('costMode').value==='effective')}
function render(){$('export').href='/api/export?dataset='+encodeURIComponent(dataset);$('export').download='kassensturz-'+dataset+'.csv';const query=$('search').value.toLocaleLowerCase();const all=monthTransactions();const filtered=all.filter(t=>JSON.stringify([t.merchant,t.category,t.items,t.group_name,t.payment_method,t.notes,t.members]).toLocaleLowerCase().includes(query));
$('effectiveHint').hidden=$('costMode').value!=='effective'||!['overview','transactions'].includes(currentView);
$('totalLabel').textContent=$('costMode').value==='effective'?'Effektive Ausgaben im Monat':'Ausgaben im Monat';$('totalHint').textContent=$('costMode').value==='effective'?'Gruppen nach Abzug ihrer Beiträge':'Positive Ausgaben vor Gutschriften';
$('total').textContent=euro(all.reduce((n,t)=>n+Math.max(t.amount,0),0));$('credits').textContent=euro(all.reduce((n,t)=>n+(t.kind==='income'?0:Math.max(-t.amount,0)),0));$('incomeTotal').textContent=euro(all.reduce((n,t)=>n+(t.kind==='income'?Math.max(-t.amount,0):0),0));$('uncat').textContent=all.filter(t=>t.items.length?t.items.some(i=>i.category===(state.default_category||'Unkategorisiert')):t.category===(state.default_category||'Unkategorisiert')).length;
const cats=Object.create(null);all.filter(t=>t.kind!=='income').forEach(t=>(t.items.length?t.items:[t]).forEach(i=>{if(i.amount>0)cats[i.category]=(cats[i.category]||0)+i.amount}));const entries=Object.entries(cats).sort((a,b)=>b[1]-a[1]);const max=Math.max(...Object.values(cats),1);
$('chart').innerHTML=entries.length?entries.map(([c,n],i)=>`<div class="categoryrow"><div class="categoryline"><span>${esc(c)}</span><b>${euro(n)}</b></div><div class="bar"><span class="c${i%5}" data-width="${n/max*100}"></span></div></div>`).join(''):'<p class="empty">Keine Ausgaben in diesem Monat.</p>';
// Dynamische Breiten per CSSOM, ohne Inline-Skripte.
document.querySelectorAll('[data-width]').forEach(e=>e.style.width=e.dataset.width+'%');
$('rows').innerHTML=filtered.map(t=>`<tr data-id="${esc(t.id)}" tabindex="0" role="button" aria-label="${esc(t.merchant)} ${t.members?'anzeigen':'bearbeiten'}"><td><div class="merchant">${esc(t.merchant)}</div>${t.notes?`<div class="entry-note">${esc(t.notes.length>140?t.notes.slice(0,140)+'…':t.notes)}</div>`:''}${!t.members&&t.payment_method?`<div class="payment-tag">${esc(t.payment_method)}</div>`:''}${t.group_name?`<div class="group-tag">${t.members?`${t.members.length} Buchungen · effektiv`:esc(t.group_name)}</div>`:''}<div class="mobile-category">${t.items.length?`${t.items.length} Positionen`:esc(t.category)}</div></td><td>${t.date.split('-').reverse().join('.')}</td><td><span class="tag">${t.items.length?`${t.items.length} Positionen · aufgeteilt`:esc(t.category)}</span></td><td class="right">${t.kind==='income'?'＋'+euro(-t.amount):euro(t.amount)}</td></tr>`).join('');
$('empty').hidden=filtered.length>0;$('count').textContent=all.length;$('categories').innerHTML=state.categories.map(c=>`<button type="button" data-category="${esc(c)}" aria-label="${esc(c)} umbenennen">${esc(c)} <span aria-hidden="true">✎</span></button>`).join('');$('categories').querySelectorAll('[data-category]').forEach(button=>button.onclick=()=>renameCategory(button.dataset.category));$('paymentMethods').innerHTML=(state.payment_methods||[]).map(name=>`<span>${esc(name)}</span>`).join('');
renderGraphs();
$('rows').querySelectorAll('tr').forEach(row=>{row.onclick=()=>{const tx=all.find(t=>String(t.id)===row.dataset.id);if(tx.members)openGroup(tx);else openEditor(state.transactions.find(original=>original.id===(tx.source_id??tx.id)))};row.onkeydown=e=>{if(e.key==='Enter')row.click()}})
}
function view(name){currentView=name;document.querySelector('.subline').hidden=['settings','graphs'].includes(name);$('overview').hidden=name!=='overview';$('ledger').hidden=!['overview','transactions'].includes(name);$('settings').hidden=name!=='settings';$('graphs').hidden=name!=='graphs';$('title').textContent={overview:'Übersicht',transactions:'Buchungen',settings:'Einstellungen',graphs:'Diagramme'}[name];document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));$('effectiveHint').hidden=$('costMode').value!=='effective'||!['overview','transactions'].includes(name);if(name==='graphs')renderGraphs()}

document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>view(b.dataset.view));$('month').onchange=render;$('costMode').onchange=render;$('search').oninput=render;
function openEditor(t=null){editing=t?.id||null;$('expenseForm').reset();$('editTitle').textContent=t?'Buchung bearbeiten':'Neue Buchung';$('transactionKind').value=t?.kind||'expense';$('entryNotes').value=t?.notes||'';updateIncomeForm();$('merchant').value=t?.merchant||'';$('date').value=t?.date||today();$('amount').value=t?((t.kind==='income'?-t.amount:t.amount)/100).toFixed(2):'';$('category').innerHTML=options(t?.category);$('paymentMethod').innerHTML=paymentOptions(t?.payment_method||'');$('groupName').value=t?.group_name||'';$('groupNames').innerHTML=[...new Set(state.transactions.flatMap(tx=>[tx.group_name,...tx.items.map(item=>item.group_name)]).filter(Boolean))].sort().map(name=>`<option value="${esc(name)}"></option>`).join('');$('items').replaceChildren();(t?.items||[]).forEach(i=>addItem({...i,amount:(t.kind==='income'?-i.amount:i.amount)/100}));$('delete').hidden=!t;$('editError').textContent='';$('ocrStatus').textContent='Texterkennung auf dem Server';$('ocrDetails').hidden=true;$('ocrText').textContent='';$('photo').value='';balance();$('editor').showModal()}
function addItem(i={name:'',amount:'',category:null,group_name:null}){const div=document.createElement('div');div.className='item';div.innerHTML=`<input class="itemname" aria-label="Artikelname" placeholder="Artikel" required value="${esc(i.name)}"><input class="itemamount" aria-label="Artikelbetrag" inputmode="decimal" placeholder="0,00" required value="${esc(i.amount)}"><select class="itemcategory" aria-label="Artikelkategorie">${options(i.category)}</select><button type="button" aria-label="Position entfernen">×</button><div class="item-group"><select class="itemgroupmode" aria-label="Gruppenzuordnung der Position"><option value="inherit">Buchungsgruppe übernehmen</option><option value="none">Keine Gruppe</option><option value="own">Eigene Gruppe</option></select><input class="itemgroupname" aria-label="Gruppe der Position" list="groupNames" maxlength="80" placeholder="Gruppenname" value="${esc(i.group_name||'')}"></div>`;const mode=div.querySelector('.itemgroupmode'),groupInput=div.querySelector('.itemgroupname');mode.value=i.group_name==null?'inherit':i.group_name===''?'none':'own';const updateGroup=()=>{groupInput.hidden=mode.value!=='own';groupInput.disabled=mode.value!=='own';groupInput.required=mode.value==='own'};mode.onchange=updateGroup;updateGroup();div.querySelector('button').onclick=()=>{div.remove();balance()};div.querySelector('.itemamount').oninput=balance;$('items').append(div);balance()}
function parseAmount(s){s=s.trim();if(s.includes(','))s=s.replaceAll('.','').replace(',','.');return Math.round(Number(s)*100)}
function balance(){const items=[...document.querySelectorAll('.itemamount')];if(!items.length){$('balance').textContent='';return}const sum=items.reduce((n,e)=>n+parseAmount(e.value),0);const diff=parseAmount($('amount').value)-sum;$('balance').textContent=`Positionen: ${euro(sum)} · ${diff===0?'✓ Betrag stimmt überein':'Noch zu verteilen: '+euro(diff)}`;$('balance').className=diff===0?'':'error'}
$('amount').oninput=balance;$('add').onclick=()=>openEditor();$('addItem').onclick=()=>addItem();$('close').onclick=()=>{if($('save').disabled)return;$('editor').close()};$('editor').addEventListener('cancel',e=>{if($('save').disabled)e.preventDefault()});
const scan=()=>{openEditor();$('photo').click()};$('scanButton').onclick=scan;$('scanNav').onclick=scan;$('emptyImport').onclick=()=>{view('settings');$('csv').click()};
$('expenseForm').onsubmit=async e=>{e.preventDefault();$('editError').textContent='';$('save').disabled=true;try{await api('transaction',{id:editing,kind:$('transactionKind').value,notes:$('entryNotes').value,merchant:$('merchant').value,date:$('date').value,amount:$('amount').value,category:$('category').value,group_name:$('groupName').value,payment_method:$('paymentMethod').value,items:[...document.querySelectorAll('.item')].map(el=>({name:el.querySelector('.itemname').value,amount:el.querySelector('.itemamount').value,category:el.querySelector('.itemcategory').value,group_name:el.querySelector('.itemgroupmode').value==='inherit'?null:el.querySelector('.itemgroupmode').value==='none'?'':el.querySelector('.itemgroupname').value}))});$('editor').close();await refresh();notice('Buchung gespeichert.')}catch(e){$('editError').textContent=e.message}finally{$('save').disabled=false}};
$('delete').onclick=async()=>{if(!confirm('Diese Buchung und ihre Positionen wirklich löschen?'))return;try{await api('delete',{id:editing});$('editor').close();await refresh();notice('Buchung gelöscht.')}catch(e){$('editError').textContent=e.message}};
$('categoryForm').onsubmit=async e=>{e.preventDefault();try{await api('category',{name:$('categoryName').value});$('categoryName').value='';await refresh()}catch(e){notice(e.message)}};
$('photo').onchange=async()=>{const file=$('photo').files[0];if(!file)return;if(file.size>12000000){$('editError').textContent='Bild ist zu groß. Maximal 12 MB.';return}$('photo').disabled=true;$('save').disabled=true;$('ocrStatus').textContent='Text wird auf dem Server erkannt …';$('editError').textContent='';try{const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file)});const r=await api('ocr',{image});$('ocrText').textContent=r.text;$('ocrDetails').hidden=false;r.items.forEach(addItem);$('ocrStatus').textContent=`${r.items.length} mögliche Positionen erkannt. Bitte Namen, Beträge und Kategorien prüfen.`;if(!r.items.length)$('ocrDetails').open=true}catch(e){$('editError').textContent=e.message;$('ocrStatus').textContent='Manuelle Erfassung ist weiterhin möglich.'}finally{$('photo').disabled=false;$('save').disabled=false}};
$('csv').onchange=async()=>{const targetDataset=dataset;const file=$('csv').files[0];if(!file)return;try{const bytes=await file.arrayBuffer();if(dataset!==targetDataset)return;csvText=new TextDecoder('utf-8').decode(bytes);if(csvText.includes('\ufffd'))csvText=new TextDecoder('windows-1252').decode(bytes);const r=await api('import-preview',{text:csvText});for(const [id,regex] of [['dateColumn',/buchungstag|buchungsdatum|datum|date/i],['merchantColumn',/empfänger|auftraggeber|merchant|beschreibung|verwendungszweck/i],['amountColumn',/betrag|amount|umsatz/i]]){$(id).innerHTML=r.headers.map(h=>`<option>${esc(h)}</option>`).join('');const match=r.headers.find(h=>regex.test(h));if(match)$(id).value=match}$('importPayment').innerHTML=paymentOptions();$('importCount').textContent=`${r.count} Buchungen gefunden. Bitte Spalten und Vorzeichen prüfen.`;$('csvPreview').textContent=r.rows.map(row=>JSON.stringify(row,null,2)).join('\n');$('importError').textContent='';$('importDialog').showModal()}catch(e){notice(e.message)}finally{$('csv').value=''}};
$('closeImport').onclick=()=>$('importDialog').close();$('importForm').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const r=await api('import',{text:csvText,date_column:$('dateColumn').value,merchant_column:$('merchantColumn').value,amount_column:$('amountColumn').value,bank_sign:$('bankSign').checked,payment_method:$('importPayment').value});$('importDialog').close();await refresh();view('transactions');notice(`${r.added} Buchungen importiert, ${r.skipped} bereits vorhandene übersprungen. Monat oben ggf. anpassen.`)}catch(e){$('importError').textContent=e.message}finally{button.disabled=false}};
async function boot(){csrf=(await api('session')).csrf;await refresh()}
$('logout').onclick=async()=>{try{await api('logout',{});window.location.replace('/login')}catch(e){notice(e.message)}};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!$('editor').open&&!$('importDialog').open&&!$('groupDialog').open)refresh().catch(e=>notice(e.message))});
boot().catch(e=>notice(e.message));

function graphMonth(value){return new Intl.DateTimeFormat('de-DE',{month:'short',year:'2-digit'}).format(new Date(value+'-01T12:00:00'))}
function graphRange(){
  if($('graphRange').value==='custom')return;
  const current=today().slice(0,7),dates=state.transactions.map(t=>t.date.slice(0,7)).sort();
  const last=dates.length&&dates[dates.length-1]>current?dates[dates.length-1]:current;
  let first;
  if($('graphRange').value==='all')first=dates[0]||current;
  else{const [year,month]=last.split('-').map(Number),index=year*12+month-Number($('graphRange').value);first=`${Math.floor(index/12)}-${String(index%12+1).padStart(2,'0')}`}
  $('graphFrom').value=first;$('graphTo').value=last;
}
function graphTable(rows,label='Monat'){
  return `<details class="graph-data"><summary>Werte anzeigen</summary><div class="tablewrap"><table><thead><tr><th>${esc(label)}</th><th class="right">Betrag</th></tr></thead><tbody>${rows.map(([name,value])=>`<tr><td>${esc(name)}</td><td class="right">${euro(value)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function graphBars(rows){
  if(!rows.length)return '<p class="empty">Keine Werte im gewählten Zeitraum.</p>';
  const max=Math.max(...rows.map(([,value])=>Math.abs(value)),1);
  return rows.map(([name,value])=>`<div class="categoryrow"><div class="categoryline"><span>${esc(name)}</span><b>${euro(value)}</b></div><div class="bar"><span class="${value<0?'negative':''}" data-width="${Math.abs(value)/max*100}"></span></div></div>`).join('');
}
function graphSVG(rows,series=null){
  const values=series?series.flatMap(s=>s.values.map(([,value])=>value)):rows.map(([,value])=>value);
  if(!values.some(value=>value!==0))return '<p class="empty">Keine Werte im gewählten Zeitraum.</p>';
  const width=Math.max(320,Math.min(720,$('monthlyGraph').clientWidth||720)),height=290,left=90,right=16,top=20,bottom=50,plotWidth=width-left-right,plotHeight=height-top-bottom;
  let min=Math.min(0,...values),max=Math.max(0,...values);if(max===min)max=min+1;
  const y=value=>top+(max-value)/(max-min)*plotHeight,step=plotWidth/rows.length,x=i=>left+step*(i+.5);
  let svg=`<svg class="report-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${series?'Kategorien im Verlauf':'Monatlicher Verlauf'}"><title>${series?'Kategorien im Verlauf':'Monatlicher Verlauf'}</title>`;
  for(let i=0;i<=4;i++){const value=min+(max-min)*i/4,pos=y(value);svg+=`<line class="graph-gridline" x1="${left}" x2="${width-right}" y1="${pos}" y2="${pos}"/><text class="graph-axis" x="${left-10}" y="${pos+4}" text-anchor="end">${esc(euro(Math.round(value)))}</text>`}
  svg+=`<line class="graph-zero" x1="${left}" x2="${width-right}" y1="${y(0)}" y2="${y(0)}"/>`;
  rows.forEach(([month,value],i)=>{
    if(i%Math.ceil(rows.length/(width<480?4:8))===0)svg+=`<text class="graph-axis" x="${x(i)}" y="${height-18}" text-anchor="middle">${esc(graphMonth(month))}</text>`;
    if(!series){const barWidth=Math.max(1,step*.65);svg+=`<rect class="graph-column ${value<0?'negative':''}" x="${x(i)-barWidth/2}" y="${Math.min(y(value),y(0))}" width="${barWidth}" height="${Math.abs(y(value)-y(0))}" tabindex="0" role="img" aria-label="${esc(graphMonth(month)+': '+euro(value))}"><title>${esc(graphMonth(month)+': '+euro(value))}</title></rect>`}
  });
  if(series)series.forEach((s,j)=>{svg+=`<polyline class="graph-line graph-color-${j}" points="${s.values.map(([,v],i)=>`${x(i)},${y(v)}`).join(' ')}"/>`;s.values.forEach(([month,value],i)=>{svg+=`<circle class="graph-dot graph-color-${j}" cx="${x(i)}" cy="${y(value)}" r="4" tabindex="0" role="img" aria-label="${esc(s.name+' · '+graphMonth(month)+': '+euro(value))}"><title>${esc(s.name+' · '+graphMonth(month)+': '+euro(value))}</title></circle>`})});
  return svg+'</svg>';
}
function renderGraphs(){
  const selected=$('graphCategory').value;
  $('graphCategory').innerHTML='<option value="">Alle Kategorien</option>'+state.categories.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
  $('graphCategory').value=state.categories.includes(selected)?selected:'';
  if($('graphRange').value!=='custom')graphRange();
  const report=KassensturzReports.aggregate(state.transactions,{from:$('graphFrom').value,to:$('graphTo').value,category:$('graphCategory').value,metric:$('graphMetric').value});
  $('graphError').textContent=report.months.length?'':'Bitte einen gültigen Zeitraum von höchstens 20 Jahren wählen.';
  $('graphExpenses').textContent=euro(report.expenses);$('graphCredits').textContent=euro(report.credits);$('graphIncome').textContent=euro(report.income);$('graphNet').textContent=euro(report.net);
  $('monthlyGraph').innerHTML=graphSVG(report.monthly)+graphTable(report.monthly.map(([month,value])=>[graphMonth(month),value]));
  $('categoryGraph').innerHTML=graphBars(report.categories);
  $('merchantGraph').innerHTML=graphBars(report.merchants.slice(0,10));
  $('trendGraph').innerHTML=graphSVG(report.monthly,report.series)+(report.series.length?`<div class="graph-legend">${report.series.map((s,i)=>`<span class="graph-color-${i}">${esc(s.name)}</span>`).join('')}</div><details class="graph-data"><summary>Werte anzeigen</summary>${report.series.map(s=>`<h3>${esc(s.name)}</h3>${graphTable(s.values.map(([month,value])=>[graphMonth(month),value]))}`).join('')}</details>`:'');
  const graphView=$('graphView').value;document.querySelectorAll('[data-graph]').forEach(panel=>panel.hidden=graphView!=='all'&&panel.dataset.graph!==graphView);
  document.querySelectorAll('#graphs [data-width]').forEach(el=>el.style.width=el.dataset.width+'%');
}
for(const id of ['graphRange','graphCategory','graphMetric','graphView'])$(id).onchange=renderGraphs;
for(const id of ['graphFrom','graphTo'])$(id).onchange=()=>{$('graphRange').value='custom';renderGraphs()};

let graphResize;window.addEventListener('resize',()=>{clearTimeout(graphResize);graphResize=setTimeout(()=>{if(currentView==='graphs')renderGraphs()},150)});

function openGroup(group){
  $('groupTitle').textContent=group.group_name;
  const purchases=group.members.reduce((sum,tx)=>sum+Math.max(tx.amount,0),0),contributions=group.members.reduce((sum,tx)=>sum+Math.max(-tx.amount,0),0);
  $('groupSummary').textContent=`Ausgaben: ${euro(purchases)} · Beiträge: ${euro(contributions)} · Effektiv: ${euro(group.amount)}`;
  $('groupScope').textContent=($('month').value?'Buchungen im gewählten Monat. ':'Alle Buchungen. ')+'Kategorie der ersten Ausgabe: '+group.category;
  $('groupRows').innerHTML=group.members.map(tx=>`<tr data-id="${tx.source_id??tx.id}" tabindex="0" role="button" aria-label="${esc(tx.merchant)} bearbeiten"><td>${esc(tx.merchant)}${tx.notes?`<div class="entry-note">${esc(tx.notes.length>140?tx.notes.slice(0,140)+'…':tx.notes)}</div>`:''}${tx.payment_method?`<div class="payment-tag">${esc(tx.payment_method)}</div>`:''}</td><td>${tx.date.split('-').reverse().join('.')}</td><td class="right">${euro(tx.amount)}</td></tr>`).join('');
  $('groupRows').querySelectorAll('tr').forEach(row=>{row.onclick=()=>{$('groupDialog').close();openEditor(state.transactions.find(tx=>tx.id===Number(row.dataset.id)))};row.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();row.click()}}});
  $('groupDialog').showModal();
}
$('closeGroup').onclick=()=>$('groupDialog').close();

function paymentOptions(selected=''){return '<option value="">Nicht angegeben</option>'+(state.payment_methods||[]).map(name=>`<option value="${esc(name)}" ${name===selected?'selected':''}>${esc(name)}</option>`).join('')}
async function renameCategory(oldName){const name=prompt('Neuer Kategoriename:',oldName);if(name===null||name.trim()===oldName)return;try{await api('category-rename',{old_name:oldName,name});await refresh();notice('Kategorie und gespeicherte Zuordnungen aktualisiert.')}catch(e){notice(e.message)}}
$('paymentForm').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await api('payment-method',{name:$('paymentName').value});$('paymentName').value='';await refresh();notice('Zahlungsmittel hinzugefügt.')}catch(e){notice(e.message)}finally{button.disabled=false}};

function updateIncomeForm(){const income=$('transactionKind').value==='income';$('amountHint').textContent=income?'Einnahmen als positiven Betrag eingeben.':'Ausgaben positiv, Erstattungen und Kostenbeiträge negativ eingeben.'}
$('transactionKind').onchange=()=>{if($('transactionKind').value==='income'){if($('amount').value)$('amount').value=(Math.abs(parseAmount($('amount').value))/100).toFixed(2);document.querySelectorAll('.itemamount').forEach(input=>{if(input.value)input.value=(Math.abs(parseAmount(input.value))/100).toFixed(2)})}updateIncomeForm();balance()};
