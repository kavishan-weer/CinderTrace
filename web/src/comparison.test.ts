import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizedMonth,type RegionHistory} from './comparison.ts';
import type {Row} from './analytics.ts';
const row=(conf=2,value:number|null=20):Row=>({month:'2025-01',cat:'veg',conf,modis_raw:10,viirs_snpp_raw:value,harmonized:value,lo:value,hi:value,source:'viirs_observed',period_status:'inferred_available',comparison_eligible:true,low_data:false});
const region=(rows:Row[]=[row()],area=2000):RegionHistory=>({id:'lk',name:'Sri Lanka',grid_area_km2:area,cell_count:50,snapshot:'2026-11-13',rows});
test('normalization uses actual grid denominator and matches the same month/filter',()=>{
 const r=region([row(),row(3,10),{...row(),month:'2024-01',harmonized:900}]);
 assert.equal(normalizedMonth(r,'2025-01',['veg'],[2,3]).rate,15);
 assert.equal(normalizedMonth(r,'2025-01',['veg'],[3]).rate,5);
 assert.equal(normalizedMonth(region([row()],4000),'2025-01',['veg'],[2]).rate,5);
});
test('true zero remains comparable; missing/provisional months are not zero',()=>{
 assert.equal(normalizedMonth(region([row(2,0)]),'2025-01',['veg'],[2]).rate,0);
 for(const patch of [{harmonized:null},{comparison_eligible:false},{period_status:'provisional'},{harmonized:NaN}]){
  const r=normalizedMonth(region([{...row(),...patch}]),'2025-01',['veg'],[2]);assert.equal(r.rate,null);assert.notEqual(r.status,'comparable');
 }
});
test('unsupported or duplicate slices cannot create a partial misleading comparison',()=>{
 assert.equal(normalizedMonth(region(),'2025-01',['veg'],[2,3]).status,'unsupported_slices');
 assert.equal(normalizedMonth(region([row(),row()]),'2025-01',['veg'],[2,3]).rate,null);
 assert.equal(normalizedMonth(region(),'2025-01',['veg','offshore'],[2]).rate,null);
});
test('invalid areas, empty filters, and sparse calibration are explicit',()=>{
 assert.equal(normalizedMonth(region([],0),'2025-01',['veg'],[2]).status,'invalid_area');
 assert.equal(normalizedMonth(region(),'2025-01',[],[2]).status,'empty_filters');
 assert.equal(normalizedMonth(region([{...row(),low_data:true}]),'2025-01',['veg'],[2]).lowData,true);
});
