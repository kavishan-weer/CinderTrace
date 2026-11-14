import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {Month} from './analytics.ts';
import {seasons,timingTrend,seasonCSV} from './seasonality.ts';
const make=(year:number,values:number[]):Month[]=>values.map((value,i)=>({month:`${year}-${String(i+1).padStart(2,'0')}`,value,modis:value,viirs:value,lo:value,hi:value,eligible:true,provisional:false,lowData:false}));
test('cumulative thresholds, tied peaks, and inclusive month duration are explicit',()=>{
 const [s]=seasons(make(2020,[0,0,10,30,30,20,10,0,0,0,0,0]),2020,2020,false);
 assert.equal(s.onset,2);assert.deepEqual(s.peaks,[3,4]);assert.equal(s.end,5);assert.equal(s.duration,4);assert.equal(s.total,100);
});
test('all activity in one month is a one-month season',()=>{
 const [s]=seasons(make(2020,[0,0,0,0,0,0,0,1,0,0,0,0]),2020,2020,false);
 assert.equal(s.onset,7);assert.equal(s.end,7);assert.equal(s.duration,1);
});
test('NSW uses both calendar years without truncating the closing half',()=>{
 const data=[...make(2019,[0,0,0,0,0,0,0,0,0,10,20,30]),...make(2020,[20,10,10,0,0,0,0,0,0,0,0,0])];
 const [s]=seasons(data,2019,2019,true);
 assert.equal(s.label,'2019/20');assert.equal(s.keys[0],'2019-07');assert.equal(s.keys[11],'2020-06');assert.equal(s.onset,3);assert.equal(s.end,7);assert.equal(s.duration,5);
});
test('absent, null, ineligible, negative, nonfinite and provisional months invalidate the whole year',()=>{
 const full=make(2020,Array(12).fill(1));
 const cases=[full.slice(1),full.map((r,i)=>i===3?{...r,value:null}:r),full.map((r,i)=>i===3?{...r,eligible:false}:r),full.map((r,i)=>i===3?{...r,provisional:true}:r),full.map((r,i)=>i===3?{...r,value:-1}:r),full.map((r,i)=>i===3?{...r,value:NaN}:r)];
 for(const rows of cases){const [s]=seasons(rows,2020,2020,false);assert.equal(s.status,'incomplete');assert.equal(s.onset,null);assert.equal(s.total,null);assert.equal(s.eligibleMonths,11);}
});
test('zero-activity years have no invented onset or peak',()=>{
 const [s]=seasons(make(2020,Array(12).fill(0)),2020,2020,false);assert.equal(s.status,'no_activity');assert.equal(s.total,0);assert.deepEqual(s.peaks,[]);assert.equal(s.duration,null);
});
test('Sen slope uses actual year separation, is robust to an outlier, and compares disjoint five-season medians',()=>{
 const data=Array.from({length:12},(_,i)=>seasons(make(2000+i*2,Array.from({length:12},(_,j)=>j===Math.min(i,11)?1:0)),2000+i*2,2000+i*2,false)[0]);
 const trend=timingTrend(data,'onset',2000)!;
 assert.equal(trend.slope,5);assert.equal(trend.n,12);assert.equal(trend.change,7);
 data[5]={...data[5],onset:0};assert.equal(timingTrend(data,'onset',2000)!.slope,5);
 assert.equal(timingTrend(data,'onset',2010),null);
});
test('trends require ten valid seasons over at least ten years and exclude sparse calibration',()=>{
 const data=Array.from({length:11},(_,i)=>seasons(make(2000+i,Array(12).fill(1)),2000+i,2000+i,false)[0]);
 assert.equal(timingTrend(data.slice(0,10),'duration',0),null);
 assert.equal(timingTrend(data,'duration',0)?.slope,0);
 data[0].lowData=true;assert.equal(timingTrend(data,'duration',0),null);
});
test('peak trends suppress circular wrap and exclude ties',()=>{
 const data=Array.from({length:12},(_,i)=>seasons(make(2000+i,Array.from({length:12},(_,j)=>j===(i%2?11:0)?1:0)),2000+i,2000+i,false)[0]);
 assert.equal(timingTrend(data,'peak',0),null);
 for(const s of data)s.peaks=[5,6];assert.equal(timingTrend(data,'peak',0),null);
});
test('CSV retains excluded years, month precision, selection provenance and quoting',()=>{
 const rows=seasons(make(2020,Array(12).fill(1)),2019,2020,false),csv=seasonCSV(rows,{area:'A "district", CA',filters:'Vegetation',snapshot:'2026-11-04'},false);
 assert.ok(csv.includes('"A ""district"", CA"'));assert.ok(csv.includes('"incomplete"'));assert.ok(csv.includes('"2020-02"'));assert.ok(csv.includes('no daily interpolation'));
});
