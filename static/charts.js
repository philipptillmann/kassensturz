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
  function aggregate(transactions,{from,to,category='',metric='expenses'}){
    const months=monthsBetween(from,to),monthly=new Map(months.map(m=>[m,0])),categories=new Map(),merchants=new Map(),series=new Map();
    let expenses=0,credits=0;
    for(const tx of transactions){
      const month=tx.date.slice(0,7);if(!monthly.has(month))continue;
      for(const item of tx.items.length?tx.items:[tx]){
        if(category&&item.category!==category)continue;
        expenses+=Math.max(item.amount,0);credits+=Math.max(-item.amount,0);
        const value=metric==='credits'?Math.max(-item.amount,0):metric==='net'?item.amount:Math.max(item.amount,0);
        monthly.set(month,monthly.get(month)+value);
        categories.set(item.category,(categories.get(item.category)||0)+value);
        merchants.set(tx.merchant,(merchants.get(tx.merchant)||0)+value);
        if(!series.has(item.category))series.set(item.category,new Map(months.map(m=>[m,0])));
        const values=series.get(item.category);values.set(month,values.get(month)+value);
      }
    }
    const ranked=map=>[...map].filter(([,value])=>value!==0).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])||a[0].localeCompare(b[0],'de'));
    const categoryRows=ranked(categories);
    return {months,monthly:[...monthly],categories:categoryRows,merchants:ranked(merchants),series:categoryRows.slice(0,5).map(([name])=>({name,values:[...series.get(name)]})),expenses,credits,net:expenses-credits};
  }
  root.KassensturzReports={monthsBetween,aggregate};
  if(typeof module!=='undefined')module.exports=root.KassensturzReports;
})(typeof window==='undefined'?globalThis:window);
