import {test} from 'node:test';import assert from 'node:assert/strict';import {climatology,anomalyColor,mapFraction,aggregate,historical,sumKnown,getJSON,type Row} from './analytics.ts';
const row=(month:string,value:number|null,eligible=true):Row=>({month,cat:'veg',conf:2,modis_raw:3,viirs_snpp_raw:value,harmonized:value,lo:value,hi:value,source:'viirs_observed',period_status:eligible?'inferred_available':'provisional',comparison_eligible:eligible,low_data:false});
test('null activity is not silently summed into zero',()=>{assert.equal(sumKnown([1,null]),null);assert.equal(sumKnown([0,0]),0);assert.equal(sumKnown([]),null);});
test('filters control all monthly aggregates',()=>{const rows=[row('2020-01',2),{...row('2020-01',8),cat:'static'}];assert.equal(aggregate(rows,['veg'],[2])[0].value,2);assert.equal(aggregate(rows,['veg','static'],[2])[0].value,10);assert.deepEqual(aggregate(rows,['veg'],[3]),[]);});
test('incomplete selection remains ineligible',()=>{const rows=[row('2020-01',2),{...row('2020-01',null,false),conf:3}];const [m]=aggregate(rows,['veg'],[2,3]);assert.equal(m.value,null);assert.equal(m.eligible,false);assert.equal(m.provisional,true);});
test('history excludes target and provisional years, requires five prior years',()=>{const rows=Array.from({length:7},(_,i)=>row(`${2018+i}-01`,i+1,i!==6));const data=aggregate(rows,['veg'],[2]);assert.equal(historical(data,'2022-01'),null);assert.equal(historical(data,'2023-01')?.median,3);assert.equal(historical(data,'2023-01')?.percentile,100);assert.equal(historical(data,'2024-01'),null);});

test('cancelled archive response is not reported as a load failure',async()=>{const original=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>{throw new DOMException('cancelled','AbortError');}} as unknown as Response);try{await assert.rejects(getJSON('/archive'),{name:'AbortError'});}finally{globalThis.fetch=original;}});

test('retrospective climatology includes early years and excludes the selected year',()=>{
 const data=aggregate(Array.from({length:8},(_,i)=>row(`${2001+i}-01`,i+1)),['veg'],[2]);
 const c=climatology(data,'2001-01');assert.equal(c?.n,7);assert.equal(c?.median,5);
 assert.equal(historical(data,'2001-01'),null);
 const changed=data.map(d=>d.month==='2001-01'?{...d,value:999}:d);
 assert.equal(climatology(changed,'2001-01')?.median,5);
});
test('anomaly palette and map scaling have stable physical references',()=>{
 assert.equal(anomalyColor(1),'rgb(245,242,232)');assert.notEqual(anomalyColor(.5),anomalyColor(2));
 assert.equal(anomalyColor(10),anomalyColor(4));assert.equal(anomalyColor(null),'#d9ddd2');
 assert.equal(mapFraction(0),0);assert.equal(mapFraction(31),1);assert.ok(mapFraction(1)<.3);
});

test('absent or duplicate filter combinations cannot produce a partial total',()=>{
 const one=row('2020-01',5);
 assert.equal(aggregate([one],['veg'],[2,3])[0].value,null);
 assert.equal(aggregate([one,one],['veg'],[2,3])[0].eligible,false);
 assert.equal(aggregate([one,{...one,conf:3,harmonized:0}],['veg'],[2,3])[0].value,5);
});
