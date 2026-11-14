import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildBrief,type BriefInput} from './brief.ts';
import type {Month} from './analytics.ts';
const month=(key:string,value:number|null,provisional=false):Month=>({month:key,value,modis:value,viirs:value,lo:value,hi:value,eligible:!provisional&&value!==null,provisional,lowData:false});
const input=(data:Month[],selected='2025-09'):BriefInput=>({data,selected,start:2000,end:2026,nsw:false,context:{area:'Sri Lanka / selected area',filters:'Vegetation / Nominal + High',snapshot:'2026-11-13',window:'2000-2026'},spatial:'48 H3 centres / local calibration'});
test('brief comparisons match the app and use all prior same-month history',()=>{
 const data=Array.from({length:7},(_,i)=>month(`${2019+i}-09`,(i+1)*10));
 const b=buildBrief({...input(data),start:2025,end:2025});
 assert.equal(b.cards[0].value,'70');assert.equal(b.cards[1].value,'35');assert.equal(b.cards[2].value,'100 / 100');
 assert.ok(b.findings[0].includes('6 prior'));assert.equal(b.calendar.length,1);assert.ok(b.coverage.includes('independently'));
});
test('provisional and missing months never receive a historical percentile',()=>{
 const history=Array.from({length:10},(_,i)=>month(`${2010+i}-09`,10));
 const provisional=buildBrief(input([...history,month('2025-09',2,true)]));
 assert.equal(provisional.status,'Provisional month');assert.equal(provisional.cards[2].value,'Unavailable');assert.ok(provisional.findings[0].includes('No full-month'));
 const missing=buildBrief(input([...history,month('2025-09',null)]));
 assert.equal(missing.cards[0].value,'Unavailable');assert.ok(missing.findings[0].includes('not interpreted as zero'));
});
test('zero historical median avoids an invented percentage increase',()=>{
 const b=buildBrief(input([...Array.from({length:6},(_,i)=>month(`${2019+i}-09`,0)),month('2025-09',2)]));
 assert.ok(b.findings[0].includes('percentage change is undefined'));assert.ok(!b.findings[0].includes('Infinity'));
});
test('NSW season profile and calendar preserve the closing calendar year',()=>{
 const data=Array.from({length:24},(_,i)=>month(`${2019+Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}`,i===11?100:1));
 const b=buildBrief({...input(data,'2019-12'),start:2019,end:2019,nsw:true});
 assert.equal(b.profile?.label,'2019/20');assert.equal(b.profile?.keys[11],'2020-06');assert.equal(b.calendar[0].months[11].month,'2020-06');assert.ok(b.findings[1].includes('Dec 2019'));
});
test('transfer ranges and sparse/no-grid limitations remain explicit',()=>{
 const b=buildBrief(input([{...month('2025-09',4),lo:2,hi:8,lowData:true}]));
 assert.ok(b.limits[0].includes('2-8'));assert.ok(b.limits.some(s=>s.includes('Low-data')));assert.equal(b.profile,null);
 const empty=buildBrief(input([month('2025-09',null)]));assert.equal(empty.profile,null);assert.ok(empty.limits[0].includes('not quantified'));
});
test('calendar is bounded to eight years and includes future/missing months as null',()=>{
 const b=buildBrief(input([month('2025-09',1)]));
 assert.equal(b.calendar.length,8);assert.equal(b.calendar.at(-1)?.label,'2026');assert.equal(b.calendar.at(-1)?.months[11].value,null);
});
