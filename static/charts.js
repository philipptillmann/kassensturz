/* Cent-based reporting, shared by the browser and Node checks. */
(function(root){
  function monthsBetween(from,to){
    if(!/^\d{4}-\d{2}$/.test(from)||!/^\d{4}-\d{2}$/.test(to)||from>to)return [];
    const [fy,fm]=from.split('-').map(Number),[ty,tm]=to.split('-').map(Number);
    if(fm<1||fm>12||tm<1||tm>12)return [];
    const start=fy*12+fm-1,end=ty*12+tm-1;
    if(end-start>239)return [];
    return Array.from({length:end-start+1},(_,i)=>`${Math.floor((start+i)/12)}-${String((start+i)%12+1).padStart(2,'0')}`);
  }
  function monthView(transactions,month,effective=false){
    const selected=transactions.filter(tx=>!month||tx.date.startsWith(month));
    if(!effective)return selected;
    const parts=tx=>tx.items.length&&tx.items.some(item=>item.group_name!=null)?tx.items.map((item,index)=>({...tx,id:'item:'+tx.id+':'+(item.id??index),source_id:tx.id,part_index:index,item_name:item.name,merchant:tx.merchant+' · '+item.name,amount:item.amount,category:item.category,group_name:item.group_name==null?tx.group_name:item.group_name,items:[]})):[{...tx,source_id:tx.id}];
    const allParts=transactions.filter(tx=>tx.kind!=='income').flatMap(parts),selectedParts=selected.flatMap(tx=>{
      // Unsplit and ungrouped receipts remain one original row.
      if(tx.kind==='income')return [tx];
      const entries=parts(tx);return entries.some(part=>part.group_name)?entries:[{...tx,group_name:''}];
    });
    const anchors=new Map();
    [...allParts].sort((a,b)=>a.date.localeCompare(b.date)||a.source_id-b.source_id||(a.part_index??0)-(b.part_index??0)).forEach(tx=>{
      if(tx.group_name&&(!anchors.has(tx.group_name)||anchors.get(tx.group_name).amount<=0&&tx.amount>0))anchors.set(tx.group_name,tx);
    });
    const groups=new Map(),rows=[];
    for(const tx of selectedParts){
      if(tx.kind==='income'||!tx.group_name){rows.push(tx);continue}
      if(!groups.has(tx.group_name)){
        const anchor=anchors.get(tx.group_name),group={id:'group:'+tx.group_name,group_name:tx.group_name,merchant:tx.group_name,date:tx.date,amount:0,category:anchor.category,items:[],members:[]};
        groups.set(tx.group_name,group);rows.push(group);
      }
      const group=groups.get(tx.group_name);group.amount+=tx.amount;group.members.push(tx);if(tx.date<group.date)group.date=tx.date;
    }
    return rows.sort((a,b)=>b.date.localeCompare(a.date)||String(b.id).localeCompare(String(a.id)));
  }
  function aggregate(transactions,{from,to,category='',metric='expenses'}){
    const months=monthsBetween(from,to),monthly=new Map(months.map(m=>[m,0])),categories=new Map(),merchants=new Map(),series=new Map();
    let expenses=0,credits=0,income=0;
    for(const tx of transactions){
      const month=tx.date.slice(0,7);if(!monthly.has(month))continue;
      for(const item of tx.items.length?tx.items:[tx]){
        if(category&&item.category!==category)continue;
        if(tx.kind==='income')income+=Math.max(-item.amount,0);else{expenses+=Math.max(item.amount,0);credits+=Math.max(-item.amount,0);}
        const value=metric==='income'?(tx.kind==='income'?Math.max(-item.amount,0):0):tx.kind==='income'?0:metric==='credits'?Math.max(-item.amount,0):metric==='net'?item.amount:Math.max(item.amount,0);
        monthly.set(month,monthly.get(month)+value);
        categories.set(item.category,(categories.get(item.category)||0)+value);
        merchants.set(tx.merchant,(merchants.get(tx.merchant)||0)+value);
        if(!series.has(item.category))series.set(item.category,new Map(months.map(m=>[m,0])));
        const values=series.get(item.category);values.set(month,values.get(month)+value);
      }
    }
    const ranked=map=>[...map].filter(([,value])=>value!==0).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])||a[0].localeCompare(b[0],'de'));
    const categoryRows=ranked(categories);
    return {months,monthly:[...monthly],categories:categoryRows,merchants:ranked(merchants),series:categoryRows.slice(0,5).map(([name])=>({name,values:[...series.get(name)]})),expenses,credits,income,net:expenses-credits};
  }
  root.KassensturzReports={monthsBetween,aggregate,monthView};
  if(typeof module!=='undefined')module.exports=root.KassensturzReports;
})(typeof window==='undefined'?globalThis:window);
