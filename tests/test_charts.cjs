const assert=require('node:assert/strict');
const {aggregate,monthsBetween}=require('../static/charts.js');
const tx=[
 {date:'2026-01-04',merchant:'Versandhandel',amount:10000,category:'Shopping',items:[{amount:6000,category:'Fahrrad'},{amount:4000,category:'Küche'}]},
 {date:'2026-01-05',merchant:'Versandhandel',amount:-2000,category:'Fahrrad',items:[]},
 {date:'2026-03-01',merchant:'Markt',amount:3000,category:'Lebensmittel',items:[]},
 {date:'2025-12-31',merchant:'Außerhalb',amount:90000,category:'Wohnen',items:[]}
];
const options={from:'2026-01',to:'2026-03'};
let r=aggregate(tx,options);
assert.deepEqual(r.monthly,[['2026-01',10000],['2026-02',0],['2026-03',3000]]);
assert.equal(r.expenses,13000);assert.equal(r.credits,2000);assert.equal(r.net,11000);
assert.deepEqual(r.categories,[['Fahrrad',6000],['Küche',4000],['Lebensmittel',3000]]);
assert.equal(r.categories.reduce((sum,[,n])=>sum+n,0),r.expenses);
r=aggregate(tx,{...options,metric:'net'});assert.equal(r.monthly[0][1],8000);
assert.equal(r.categories.find(([name])=>name==='Fahrrad')[1],4000);
r=aggregate(tx,{...options,metric:'credits'});assert.equal(r.monthly[0][1],2000);assert.equal(r.merchants[0][1],2000);
r=aggregate(tx,{...options,category:'Fahrrad'});assert.equal(r.expenses,6000);assert.equal(r.credits,2000);assert.equal(r.series.length,1);
assert.deepEqual(monthsBetween('2025-12','2026-02'),['2025-12','2026-01','2026-02']);
for(const [from,to] of [['2026-02','2026-01'],['2026-13','2027-01'],['2000-01','2026-01'],['','']])assert.equal(monthsBetween(from,to).length,0);
assert.deepEqual(aggregate([] ,options).monthly,[['2026-01',0],['2026-02',0],['2026-03',0]]);
assert.equal(aggregate([{date:'2026-01-01',merchant:'__proto__',amount:100,category:'__proto__',items:[]}],options).categories[0][1],100);
console.log('Chart checks passed: splits, refunds, filters, empty months, year boundaries, and invalid ranges.');
const {monthView}=require('../static/charts.js');
const gift=[
 {id:1,date:'2026-10-01',merchant:'Amazon',amount:12000,category:'Shopping',group_name:'Gift',items:[{amount:12000,category:'Shopping'}]},
 {id:2,date:'2026-10-02',merchant:'Cash',amount:-3000,category:'Unkategorisiert',group_name:'Gift',items:[]},
 {id:3,date:'2026-10-03',merchant:'PayPal',amount:-4000,category:'Unkategorisiert',group_name:'Gift',items:[]},
 {id:4,date:'2026-11-01',merchant:'Later contribution',amount:-1000,category:'Unkategorisiert',group_name:'Gift',items:[]},
 {id:5,date:'2026-10-05',merchant:'Groceries',amount:2500,category:'Lebensmittel',group_name:'',items:[]}
];
const snapshot=JSON.stringify(gift);
assert.equal(monthView(gift,'2026-10',false).length,4);
let grouped=monthView(gift,'2026-10',true);assert.equal(grouped.length,2);
let group=grouped.find(t=>t.members);assert.equal(group.amount,5000);assert.equal(group.members.length,3);assert.equal(group.category,'Shopping');assert.equal(group.merchant,'Gift');
assert.equal(grouped.reduce((n,t)=>n+Math.max(t.amount,0),0),7500);
assert.equal(monthView(gift,'2026-11',true)[0].amount,-1000);assert.equal(monthView(gift,'2026-11',true)[0].category,'Shopping');
assert.equal(monthView(gift,'',true).find(t=>t.members).amount,4000);
assert.equal(monthView(gift,'2025-01',true).length,0);
assert.equal(JSON.stringify(gift),snapshot);
assert.equal(monthView(gift.map(t=>({...t,group_name:t.group_name==='Gift'?'__proto__':''})),'2026-10',true).find(t=>t.members).amount,5000);
assert.equal(monthView([{...gift[0],amount:3000,items:[]},gift[1]],'2026-10',true)[0].amount,0);
assert.equal(monthView([{...gift[0],amount:1000,items:[]},gift[1]],'2026-10',true)[0].amount,-2000);
console.log('Group checks passed: purchase/contributions, monthly boundaries, category anchoring, zero/negative groups, and original data preserved.');
const mixed=[
 {id:10,date:'2026-10-01',merchant:'Amazon',amount:15000,category:'Shopping',group_name:'',items:[
  {id:1,name:'Gift',amount:9000,category:'Shopping',group_name:'Shared gift'},
  {id:2,name:'Bike light',amount:3500,category:'Fahrrad',group_name:''},
  {id:3,name:'Kitchen',amount:2500,category:'Küche',group_name:null}]},
 {id:11,date:'2026-10-02',merchant:'Cash',amount:-2000,category:'Shopping',group_name:'Shared gift',items:[]},
 {id:12,date:'2026-10-03',merchant:'PayPal',amount:-3000,category:'Shopping',group_name:'Shared gift',items:[]}
];
const mixedSnapshot=JSON.stringify(mixed);let effective=monthView(mixed,'2026-10',true);
assert.equal(effective.length,3);assert.equal(effective.find(t=>t.members).amount,4000);
assert.equal(effective.find(t=>t.members).members[0].source_id,10);
assert.equal(effective.filter(t=>!t.members).reduce((n,t)=>n+t.amount,0),6000);
assert.equal(effective.reduce((n,t)=>n+t.amount,0),10000);
assert.equal(monthView(mixed,'2026-10',false)[0].amount,15000);assert.equal(JSON.stringify(mixed),mixedSnapshot);
const both={...mixed[0],group_name:'Whole receipt',items:mixed[0].items.map((i,index)=>({...i,group_name:index===0?'Gift':index===1?'Bike':''}))};
effective=monthView([both],'2026-10',true);assert.equal(effective.filter(t=>t.members).length,2);
assert.equal(effective.reduce((n,t)=>n+t.amount,0),15000);
const noGroups={...mixed[0],group_name:'Whole receipt',items:mixed[0].items.map(i=>({...i,group_name:''}))};
assert.equal(monthView([noGroups],'2026-10',true).length,1);assert.equal(monthView([noGroups],'2026-10',true)[0].members,undefined);
const inherit={...mixed[0],group_name:'Whole receipt',items:mixed[0].items.map(i=>({...i,group_name:null}))};
assert.equal(monthView([inherit],'2026-10',true)[0].amount,15000);assert.equal(monthView([inherit],'2026-10',true)[0].members.length,1);
console.log('Receipt group checks passed: partial grouping, multiple groups, inheritance, explicit opt-out, and no double counting.');
