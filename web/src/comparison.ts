import {type Row} from './analytics.ts';
export type RegionHistory={id:string;name:string;grid_area_km2:number;cell_count:number;snapshot:string;rows:Row[]};
export function normalizedMonth(region:RegionHistory,month:string,cats:string[],confs:number[]){
 const slices=region.rows.filter(r=>r.month===month&&cats.includes(r.cat)&&confs.includes(r.conf));
 const result={id:region.id,name:region.name,area:region.grid_area_km2,snapshot:region.snapshot,total:null as number|null,rate:null as number|null,lowData:slices.some(r=>r.low_data),status:'unavailable'};
 if(!cats.length||!confs.length)return {...result,status:'empty_filters'};
 if(!Number.isFinite(region.grid_area_km2)||region.grid_area_km2<=0)return {...result,status:'invalid_area'};
 const keys=new Set(slices.map(r=>`${r.cat}/${r.conf}`));
 if(slices.length!==cats.length*confs.length||keys.size!==slices.length)return {...result,status:'unsupported_slices'};
 if(slices.some(r=>r.period_status==='provisional'))return {...result,status:'provisional'};
 if(slices.some(r=>!r.comparison_eligible||r.harmonized===null||!Number.isFinite(r.harmonized)||r.harmonized<0))return result;
 const total=slices.reduce((n,r)=>n+r.harmonized!,0);
 return {...result,total,rate:total/region.grid_area_km2*1000,status:'comparable'};
}
