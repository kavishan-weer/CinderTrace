import {test} from 'node:test';
import assert from 'node:assert/strict';
import {eventWarnings,observedSpan,timelineX,type Candidate} from './events.ts';
test('candidate cautions retain weak support, archive edges and long chains',()=>{
 const warnings=eventWarnings({singleton:true,multi_date_support:false,touches_region_grid_edge:true,touches_archive_time_edge:true,end_in_latest_archive_month:false,long_chain_caution:true,possible_persistent_source:true} as Candidate);
 assert.equal(warnings.length,5);assert.ok(warnings[0].includes('weak'));assert.ok(warnings.some(w=>w.includes('separate burning')));
});
test('observed span remains elapsed time, including a zero-span observation',()=>{
 assert.equal(observedSpan(0),'0 h');assert.equal(observedSpan(.5),'30 min');assert.equal(observedSpan(24),'24.0 h');assert.equal(observedSpan(72),'3.0 days');
});
test('timeline preserves actual elapsed-date gaps and centres a single observed date',()=>{
 assert.equal(timelineX('2020-03-01','2020-02-28','2020-03-02',100),60);
 assert.equal(timelineX('2020-02-28','2020-02-28','2020-02-28',100),50);
});
