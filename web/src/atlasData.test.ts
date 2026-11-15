import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {hydrate,selectObservations,dailyCounts,monthlyCounts,monthRange,readSelection,selectionSearch,dateDay,csvForObservations,type NativeRow} from './atlasData.ts';
const rows=JSON.parse(readFileSync(new URL('../atlas-public/atlas/observations.json',import.meta.url),'utf8')) as NativeRow[];
const points=hydrate(rows);
test('checked observations reconcile across satellites, calendar, timeline and export',()=>{
 assert.equal(points.length,13366);
 assert.deepEqual([0,1,2,3].map(s=>selectObservations(points,[0,364],[s]).length),[198,642,6432,6094]);
 assert.equal(dailyCounts(points,[0,1,2,3]).reduce((a,b)=>a+b,0),13366);
 assert.equal(monthlyCounts(points,[0,364]).reduce((a,m)=>a+m.count,0),13366);
 const csv=csvForObservations(points).trim().split('\r\n');assert.equal(csv.length,13367);
 assert.match(csv[0],/native_confidence,confidence_pct/);
});
test('August and sparse December remain native observed counts',()=>{
 assert.equal(selectObservations(points,monthRange(7),[0,1,2,3]).length,7017);
 const dec=selectObservations(points,monthRange(11),[0,1,2,3]);assert.equal(dec.length,7);
 assert.equal(selectObservations(points,monthRange(11),[0,1]).length,0);
 assert.equal(selectObservations(points,[0,364],[]).length,0);
 const months=monthlyCounts(dec,monthRange(11));assert.equal(months[11].count,7);assert.equal(months[10].inRange,false);
});
test('UTC day endpoints include the whole day and partial calendars reconcile',()=>{
 const day=points[0].day;
 const selected=selectObservations(points,[day,day],[0,1,2,3]);assert.ok(selected.length);
 assert.ok(selected.every(p=>p.day===day));assert.equal(selected.length,dailyCounts(points,[0,1,2,3])[day]);
 const months=monthlyCounts(selected,[day,day]);assert.equal(months.filter(m=>m.inRange).length,1);
 assert.equal(months.reduce((a,m)=>a+m.count,0),selected.length);assert.ok(months.find(m=>m.inRange)?.partial);
});
test('shared links preserve all date and satellite selections including none',()=>{
 for(const sats of [[],[0],[2,3],[0,1,2,3]])assert.deepEqual(readSelection(selectionSearch([212,242],sats)),{range:[212,242],satellites:sats});
 assert.equal(dateDay('2023-02-29'),null);assert.equal(dateDay('2024-01-01'),null);
 assert.equal(dateDay('2023-12-31'),364);assert.deepEqual(readSelection('?from=bad&to=bad').range,[0,364]);
});
test('VIIRS confidence is exported as class with no invented percentage',()=>{
 const p=points.find(p=>p.satellite===2)!;const values=csvForObservations([p]).trim().split('\r\n')[1].split(',');
 assert.equal(values[8],p.confidence);assert.equal(values[9],'');
 assert.throws(()=>hydrate([[0,80,8,0,1,'90',90,0,1,1]]),/outside/);
});
