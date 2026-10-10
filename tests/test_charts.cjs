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
