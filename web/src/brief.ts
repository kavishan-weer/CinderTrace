import {historical,months,type Month} from './analytics.ts';
import {seasons,timingTrend} from './seasonality.ts';

type Context={area:string;filters:string;window:string;snapshot:string};
export type BriefInput={data:Month[];selected:string;start:number;end:number;nsw:boolean;context:Context;spatial:string};
const number=(value:number)=>new Intl.NumberFormat('en',{maximumFractionDigits:1}).format(value);
const label=(key:string)=>`${months[Number(key.slice(5))-1]} ${key.slice(0,4)}`;
export function buildBrief({data,selected,start,end,nsw,context,spatial}:BriefInput){
 const target=data.find(d=>d.month===selected),history=historical(data,selected);
 const annual=seasons(data,start,end,nsw),season=annual.filter(s=>s.status==='complete').at(-1)??null;
 const durationTrend=timingTrend(annual,'duration',2013);
 const valid=target?.value!==null&&target?.value!==undefined&&Number.isFinite(target.value);
 const value=valid?target!.value!:null;
 const findings:string[]=[];
 if(value===null)findings.push(`${label(selected)} has no supported activity estimate. Missing values are not interpreted as zero.`);
 else if(target!.provisional)findings.push(`${label(selected)} records ${number(value)} cell-days in a provisional archive month. No full-month comparison or extrapolation is made.`);
 else if(history){
  const delta=value-history.median;
  findings.push(`${label(selected)} is at percentile ${Math.round(history.percentile)}/100 against ${history.n} prior eligible matching months: ${number(Math.abs(delta))} cell-days ${delta>0?'above':delta<0?'below':'from'} the historical median.${history.median===0?' The baseline median is zero; a percentage change is undefined.':''}`);
 }else findings.push(`${label(selected)} records ${number(value)} cell-days. A historical comparison is unavailable: the month must be eligible and have at least five prior eligible matching months.`);
 if(season){
  const peaks=season.peaks.length>3?`${season.peaks.length} tied peak months`:season.peaks.map(i=>label(season.keys[i])).join(' / ');
  findings.push(`Latest complete active season in the window: ${season.label}. Onset ${label(season.keys[season.onset!])}, peak ${peaks}, end ${label(season.keys[season.end!])}; ${season.duration} months inclusive.${season.lowData?' Low-data calibration; excluded from trends.':''}`);
 }else findings.push('No complete active season is available in the selected history window. Season timing requires 12 eligible months and positive annual activity.');
 if(durationTrend){
  const slope=durationTrend.slope;
  findings.push(Math.abs(slope)<.05?`The VIIRS-era duration trend has no directional shift at monthly resolution (${durationTrend.n} eligible seasons, ${durationTrend.first}-${durationTrend.last}). This does not prove stability.`:`VIIRS-era season duration changes by ${number(Math.abs(slope))} months ${slope>0?'longer':'shorter'} per decade (${durationTrend.n} seasons, ${durationTrend.first}-${durationTrend.last}; median pairwise slope). No significance claim is made.`);
 }else findings.push('A VIIRS-era duration trend is unavailable: at least 10 complete, active, non-low-data seasons spanning 10 years are required within the selected window.');
 const transfer=valid&&target!.lo!==null&&target!.hi!==null&&Number.isFinite(target!.lo)&&Number.isFinite(target!.hi)&&target!.lo!==target!.hi
  ?`Selected-month transfer range: ${number(target!.lo)}-${number(target!.hi)} cell-days. This is a model-transfer range, not a total measurement confidence interval.`
  :'Selected-month transfer uncertainty is not quantified here. Equal or absent bounds do not establish zero uncertainty.';
 const calendar=annual.slice(-8).map(s=>({label:s.label,months:s.keys.map(key=>{
  const d=data.find(m=>m.month===key);return {month:key,value:d?.value??null,provisional:d?.provisional??false,eligible:d?.eligible??false};
 })}));
 const inWindow=data.filter(d=>Number(d.month.slice(0,4))>=start&&Number(d.month.slice(0,4))<=end);
 const lowData=target?.lowData||season?.lowData||inWindow.some(d=>d.lowData);
 return {
  version:1,area:context.area,filters:context.filters,snapshot:context.snapshot,window:`${start}-${end}`,spatial,selected,selected_label:label(selected),
  generated_utc:new Date().toISOString(),year_basis:nsw?'July-June (starting fire years)':'January-December',
  status:target?.provisional?'Provisional month':target?.eligible&&valid?'Comparable archive month':'Comparison unavailable',
  cards:[{label:'Harmonized activity',value:value===null?'Unavailable':number(value),note:'VIIRS-equivalent cell-days'},{label:'Historical median',value:history?number(history.median):'Unavailable',note:history?`${history.n} prior matching months`:'Needs 5 eligible prior years'},{label:'Historical percentile',value:history?`${Math.round(history.percentile)} / 100`:'Unavailable',note:'Relative to prior same-month history'}],
  findings,calendar,profile:season?{label:season.label,keys:season.keys,values:season.values,onset:season.onset,end:season.end,peaks:season.peaks,duration:season.duration,total:season.total,low_data:season.lowData}:null,
  limits:[transfer,
   'Availability is inferred from regional archive activity, not verified satellite overpasses or cloud-free coverage. Provisional and missing months cannot establish low fire risk.',
   'H3 cell-centre selection and regional calibration apply. Local transfer accuracy and uncertainty have not been independently validated. Source classes and confidence levels are heuristic conventions.',
   'Season onset/end use cumulative 10%/90% activity; duration is an inclusive monthly window, which may contain quiet intervals. Fire-active cell-days are not individual fires, burned area or a forecast.',
   ...(lowData?['Low-data calibration is present in this selection; interpret timing and activity with additional caution.']:[]),
  ],
  coverage:`Calendar shows the latest ${calendar.length} starting years in ${start}-${end}; ${yearBasis(nsw)}. Selected-month comparisons use all available prior matching months, independently of that window.${Number(selected.slice(0,4))<start||Number(selected.slice(0,4))>end?' The selected month is outside the chart history window.':''}`,
  sources:'NASA FIRMS via firms-catalog / Source Cooperative; geoBoundaries. firms.modaps.eosdis.nasa.gov / geoboundaries.org. Archive snapshot, not a live warning service.',
 };
}
function yearBasis(nsw:boolean){return nsw?'July-June fire years':'calendar years';}
export type Brief=ReturnType<typeof buildBrief>;
