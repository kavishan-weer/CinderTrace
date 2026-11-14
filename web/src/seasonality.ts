import type {Month} from './analytics.ts';

export type Season = {
 year:number; label:string; keys:string[]; values:(number|null)[];
 status:'complete'|'incomplete'|'no_activity'; eligibleMonths:number; lowData:boolean;
 total:number|null; onset:number|null; end:number|null; peaks:number[]; duration:number|null;
};
export type TimingMetric='onset'|'peak'|'end'|'duration';
export type TimingTrend={n:number;first:number;last:number;slope:number;change:number;early:string;late:string};

export function seasons(data:Month[],start:number,end:number,nsw:boolean):Season[]{
 const lookup=new Map(data.map(d=>[d.month,d]));
 return Array.from({length:Math.max(0,end-start+1)},(_,i)=>{
  const year=start+i,offset=nsw?6:0;
  const keys=Array.from({length:12},(_,j)=>`${year+Math.floor((j+offset)/12)}-${String((j+offset)%12+1).padStart(2,'0')}`);
  const rows=keys.map(k=>lookup.get(k));
  const valid=(r:Month|undefined)=>!!r&&r.eligible&&!r.provisional&&r.value!==null&&Number.isFinite(r.value)&&r.value>=0;
  const values=rows.map(r=>valid(r)?r!.value:null),eligibleMonths=rows.filter(valid).length;
  const base={year,label:nsw?`${year}/${String(year+1).slice(-2)}`:String(year),keys,values,eligibleMonths,lowData:rows.some(r=>r?.lowData),total:null,onset:null,end:null,peaks:[],duration:null};
  if(eligibleMonths!==12)return {...base,status:'incomplete' as const};
  const total=values.reduce<number>((sum,v)=>sum+v!,0);
  if(total===0)return {...base,total,status:'no_activity' as const};
  let cumulative=0,onset=-1,finish=-1;
  for(let j=0;j<12;j++){cumulative+=values[j]!;if(onset<0&&cumulative>=total*.1)onset=j;if(finish<0&&cumulative>=total*.9)finish=j;}
  const max=Math.max(...values as number[]),peaks=values.flatMap((v,j)=>v===max?[j]:[]);
  return {...base,total,status:'complete' as const,onset,end:finish,peaks,duration:finish-onset+1};
 });
}

function median(values:number[]){const sorted=[...values].sort((a,b)=>a-b),mid=Math.floor(sorted.length/2);return sorted.length%2?sorted[mid]:(sorted[mid-1]+sorted[mid])/2;}
export function timingTrend(data:Season[],metric:TimingMetric,minYear:number):TimingTrend|null{
 const points=data.filter(s=>s.status==='complete'&&!s.lowData&&s.year>=minYear&&(metric!=='peak'||s.peaks.length===1)).map(s=>({year:s.year,label:s.label,value:metric==='peak'?s.peaks[0]:s[metric]!})).sort((a,b)=>a.year-b.year);
 if(points.length<10||points.at(-1)!.year-points[0].year<10)return null;
 // A peak that straddles the fire-year boundary has no meaningful linear slope.
 if(metric==='peak'&&Math.max(...points.map(p=>p.value))-Math.min(...points.map(p=>p.value))>6)return null;
 const slopes:number[]=[];
 for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++)slopes.push((points[j].value-points[i].value)/(points[j].year-points[i].year));
 const early=points.slice(0,5),late=points.slice(-5);
 return {n:points.length,first:points[0].year,last:points.at(-1)!.year,slope:median(slopes)*10,change:median(late.map(p=>p.value))-median(early.map(p=>p.value)),early:`${early[0].label}–${early.at(-1)!.label}`,late:`${late[0].label}–${late.at(-1)!.label}`};
}

export function seasonCSV(data:Season[],context:{area:string;filters:string;snapshot:string},nsw:boolean):string{
 const columns=['area','filters','snapshot','season','year_basis','status','eligible_months','low_data','onset_month_10pct','peak_months','end_month_90pct','duration_months_inclusive','annual_harmonized_cell_days','method'];
 const quote=(v:unknown)=>`"${String(v??'').replaceAll('"','""')}"`;
 return [columns,...data.map(s=>[context.area,context.filters,context.snapshot,s.label,nsw?'July–June':'January–December',s.status,s.eligibleMonths,s.lowData,s.onset===null?'':s.keys[s.onset],s.peaks.map(i=>s.keys[i]).join(';'),s.end===null?'':s.keys[s.end],s.duration,s.total,'Cumulative monthly activity 10%–90%; peak = maximum month; no daily interpolation'])].map(row=>row.map(quote).join(',')).join('\n');
}
