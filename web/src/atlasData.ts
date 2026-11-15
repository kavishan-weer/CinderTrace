export const SATELLITES=['Terra','Aqua','Suomi-NPP','NOAA-20'] as const;
export const SATELLITE_COLORS=['#f3b65c','#74b7ce','#ed7855','#c3a0d4'];
export const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
export const YEAR_START=Date.UTC(2023,0,1)/1000;
export const DAYS=365;
export type Range=readonly [number,number];
export type NativeRow=[number,number,number,number,number|null,string,number|null,number|null,number|null,number|null];
export type Observation={id:number;timestamp:number;day:number;lon:number;lat:number;satellite:number;frp:number|null;confidence:string;confidencePct:number|null;type:number|null;scan:number|null;track:number|null};
export type AtlasManifest={title:string;year:number;satellites:string[];row_count:number;run_id:string;bundle_sha256:string;source_url:string;source_snapshot:Record<string,string>;quality:string;observing_coverage:string;harmonization_applied:boolean;bounds:number[]};
export function hydrate(rows:NativeRow[]):Observation[]{
 return rows.map((r,id)=>{
  if(r.length!==10||!Number.isInteger(r[0])||!Number.isFinite(r[1])||!Number.isFinite(r[2])||!Number.isInteger(r[3])||r[3]<0||r[3]>3)throw new Error('The observation file does not match the checked pilot format.');
  const day=Math.floor((r[0]-YEAR_START)/86400);if(day<0||day>=DAYS)throw new Error('Observation lies outside the 2023 pilot.');
  return {id,timestamp:r[0],day,lon:r[1],lat:r[2],satellite:r[3],frp:r[4],confidence:r[5],confidencePct:r[6],type:r[7],scan:r[8],track:r[9]};
 });
}
export function selectObservations(rows:Observation[],range:Range,satellites:readonly number[]):Observation[]{const enabled=new Set(satellites);return rows.filter(p=>enabled.has(p.satellite)&&p.day>=range[0]&&p.day<=range[1]);}
export function dailyCounts(rows:Observation[],satellites:readonly number[]):number[]{const enabled=new Set(satellites);const counts=Array<number>(DAYS).fill(0);for(const p of rows)if(enabled.has(p.satellite))counts[p.day]++;return counts;}
export function monthRange(month:number):Range{return [Math.floor((Date.UTC(2023,month,1)/1000-YEAR_START)/86400),Math.floor((Date.UTC(2023,month+1,1)/1000-YEAR_START)/86400)-1];}
export function monthlyCounts(selected:Observation[],range:Range){const counts=Array<number>(12).fill(0);for(const p of selected)counts[new Date(p.timestamp*1000).getUTCMonth()]++;return counts.map((count,month)=>({month,count,inRange:monthRange(month)[0]<=range[1]&&monthRange(month)[1]>=range[0],partial:range[0]>monthRange(month)[0]||range[1]<monthRange(month)[1]}));}
export function dayISO(day:number){return new Date((YEAR_START+day*86400)*1000).toISOString().slice(0,10);}
export function dateDay(value:string):number|null{if(!/^2023-\d{2}-\d{2}$/.test(value))return null;const t=Date.parse(value+'T00:00:00Z');if(!Number.isFinite(t))return null;const day=Math.round((t/1000-YEAR_START)/86400);return day>=0&&day<DAYS&&dayISO(day)===value?day:null;}
export function formatDay(day:number,short=false){return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:short?'short':'long',timeZone:'UTC'}).format(new Date((YEAR_START+day*86400)*1000));}
export function normalizeRange(start:number,end:number):Range{const a=Math.max(0,Math.min(DAYS-1,Math.round(start))),b=Math.max(0,Math.min(DAYS-1,Math.round(end)));return [Math.min(a,b),Math.max(a,b)];}
export function readSelection(search:string):{range:Range;satellites:number[]}{const params=new URLSearchParams(search);const a=dateDay(params.get('from')||''),b=dateDay(params.get('to')||'');const encoded=params.get('sat');const satellites=encoded===null?[0,1,2,3]:[...new Set(encoded.split(',').filter(v=>/^[0-3]$/.test(v)).map(Number))];return {range:a!==null&&b!==null?normalizeRange(a,b):[0,364],satellites};}
export function selectionSearch(range:Range,satellites:readonly number[]){return '?'+new URLSearchParams({from:dayISO(range[0]),to:dayISO(range[1]),sat:[...satellites].sort().join(',')}).toString();}
export function csvForObservations(rows:Observation[]):string{
 const escape=(value:unknown)=>{const s=value===null||value===undefined?'':String(value);return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
 return [['observation_id','acquisition_utc','satellite','sensor','quality','longitude','latitude','frp_mw','native_confidence','confidence_pct','published_type','scan_native','track_native'],...rows.map(p=>[p.id,new Date(p.timestamp*1000).toISOString(),SATELLITES[p.satellite],p.satellite<2?'MODIS':p.satellite===2?'VIIRS_SNPP':'VIIRS_NOAA20','sp',p.lon,p.lat,p.frp,p.confidence,p.confidencePct,p.type,p.scan,p.track])].map(row=>row.map(escape).join(',')).join('\r\n')+'\r\n';
}
export function downloadCSV(rows:Observation[],range:Range){const blob=new Blob([csvForObservations(rows)],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`cindertrace_lk_${dayISO(range[0])}_${dayISO(range[1])}_observed.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);}
