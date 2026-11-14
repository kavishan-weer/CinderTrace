import {useEffect,useMemo,useState} from 'react';
import {ArrowDownToLine,ArrowUpRight} from 'lucide-react';
import {fmt,months,type Month} from './analytics';
import {seasons,timingTrend,seasonCSV,type Season,type TimingMetric} from './seasonality';
import type {ExportContext} from './chartExport';

const metrics:{key:TimingMetric;label:string;note:string}[]=[
 {key:'onset',label:'Onset',note:'10% of annual activity reached'},
 {key:'peak',label:'Peak',note:'Highest-activity month; ties kept'},
 {key:'end',label:'End',note:'90% of annual activity reached'},
 {key:'duration',label:'Duration',note:'Onset through end, inclusive'},
];
const monthLabel=(s:Season,index:number)=>`${months[Number(s.keys[index].slice(5))-1]} ${s.keys[index].slice(0,4)}`;
function timing(s:Season|undefined,key:TimingMetric){
 if(!s||s.status!=='complete')return '—';
 if(key==='duration')return `${s.duration} ${s.duration===1?'month':'months'}`;
 return key==='peak'?(s.peaks.length>3?`${s.peaks.length} tied months`:s.peaks.map(i=>months[Number(s.keys[i].slice(5))-1]).join(' / ')):months[Number(s.keys[s[key]!].slice(5))-1];
}
function trendText(value:number,key:TimingMetric){
 if(Math.abs(value)<.05)return 'No directional shift';
 return `${Math.abs(value).toFixed(1)} mo ${key==='duration'?(value>0?'longer':'shorter'):(value>0?'later':'earlier')}`;
}

export default function SeasonInsights({data,start,end,nsw,loading,exportContext}:{data:Month[];start:number;end:number;nsw:boolean;loading:boolean;exportContext:ExportContext}){
 const annual=useMemo(()=>seasons(data,start,end,nsw),[data,start,end,nsw]);
 const [picked,setPicked]=useState<number|null>(null),[era,setEra]=useState<'viirs'|'full'>('viirs');
 const [csv,setCSV]=useState<{url:string;filename:string}|null>(null);
 useEffect(()=>setCSV(null),[data,start,end,nsw,exportContext.area,exportContext.filters,exportContext.snapshot]);
 useEffect(()=>{if(!csv)return;const timer=setTimeout(()=>setCSV(null),600000);return()=>{clearTimeout(timer);URL.revokeObjectURL(csv.url);};},[csv]);
 const complete=annual.filter(s=>s.status==='complete');
 const chosen=annual.find(s=>s.year===picked)||complete.at(-1)||annual.at(-1);
 const minYear=era==='viirs'?2013:start;
 const trends=metrics.map(m=>timingTrend(annual,m.key,minYear));
 const orderedMonths=Array.from({length:12},(_,i)=>months[(i+(nsw?6:0))%12]);
 const ready=chosen?.status==='complete';
 const peakText=ready?chosen.peaks.map(i=>monthLabel(chosen,i)).join(' / '):'';
 const cumulative:number[]=[];let sum=0;
 if(ready)for(const v of chosen.values){sum+=v!;cumulative.push(sum/chosen.total!*100);}
 const path=ready?`M 32 142 ${cumulative.map((v,i)=>`L ${32+(i+1)*54} ${142-v*1.12}`).join(' ')}`:'';

 function exportCSV(){
  const url=URL.createObjectURL(new Blob([seasonCSV(annual,exportContext,nsw)],{type:'text/csv;charset=utf-8'}));
  const filename=`emberline-seasons-${nsw?'jul-jun':'jan-dec'}-${start}-${end}.csv`;
  setCSV({url,filename});const a=document.createElement('a');a.href=url;a.download=filename;a.click();
 }
 return <section className="panel season-panel" id="seasons" aria-labelledby="season-title" aria-busy={loading}>
  <div className="section-top">
   <div><span className="eyebrow">03 / THE RHYTHM OF THE SEASON</span><h2 id="season-title">When it begins.<br/><span>How long it stays.</span></h2></div>
   <div className="season-actions"><span className="season-basis">{nsw?'JUL → JUN · FIRE YEAR':'JAN → DEC · CALENDAR YEAR'}</span><button className="png-button" disabled={loading||!data.length} onClick={exportCSV}><ArrowDownToLine size={13}/> Season CSV</button></div>
  </div>
  <p className="season-context">{exportContext.area} · {exportContext.filters}</p>
  {csv&&<a className="png-ready" href={csv.url} download={csv.filename}>Season CSV ready · Download again ↗</a>}
  <div className="season-summary-heading"><label>EXPLORE A SEASON <select aria-label="Season year" value={chosen?.year??end} disabled={loading} onChange={e=>setPicked(Number(e.target.value))}>{[...annual].reverse().map(s=><option key={s.year} value={s.year}>{s.label}{s.status==='incomplete'?' · incomplete':s.status==='no_activity'?' · no activity':''}</option>)}</select></label><span>{loading?'Loading area history…':`${complete.length} complete, active seasons · ${annual.length-complete.length} excluded`}</span></div>
  <div className="season-metrics">{metrics.map(m=><div key={m.key}><span>{m.label}</span><strong>{loading?'…':timing(chosen,m.key)}</strong><small>{m.note}</small></div>)}</div>
  {chosen&&!loading&&<>
   {ready?<div className="season-profile">
    <div className="season-profile-title"><strong>{chosen.label} <span>· {fmt(chosen.total,1)} cell-days</span></strong><span>Monthly share <i className="season-bar-key"/> Cumulative activity <i className="season-line-key"/></span></div>
    <svg className="season-profile-chart" viewBox="0 0 724 180" role="img" aria-label={`${chosen.label}: onset ${monthLabel(chosen,chosen.onset!)}, peak ${peakText}, end ${monthLabel(chosen,chosen.end!)}, duration ${chosen.duration} months. Bars show each month's share of annual activity; the line shows cumulative activity.`}>
     {[10,90].map(v=><g key={v}><line x1="32" x2="680" y1={142-v*1.12} y2={142-v*1.12} stroke="#91a389" strokeDasharray="3 5"/><text x="686" y={146-v*1.12}>{v}%</text></g>)}
     {chosen.values.map((v,i)=>{const pct=v!/chosen.total!*100;return <g key={i}><title>{monthLabel(chosen,i)}: {fmt(v,1)} cell-days ({pct.toFixed(1)}%){chosen.peaks.includes(i)?' · peak':''}</title><rect x={38+i*54} y={142-pct*1.12} width="40" height={Math.max(0,pct*1.12)} rx="3" fill={chosen.peaks.includes(i)?'#cf6844':i>=chosen.onset!&&i<=chosen.end!?'#759b78':'#c8d4bb'}/><text x={58+i*54} y="164" textAnchor="middle">{orderedMonths[i]}</text></g>;})}
     <path d={path} fill="none" stroke="#344d3c" strokeWidth="2.5" strokeLinejoin="round"/>
     {[chosen.onset!,chosen.end!].map((i,j)=><circle key={j} cx={32+(i+1)*54} cy={142-cumulative[i]*1.12} r="4" fill="#f3f5ec" stroke="#344d3c" strokeWidth="2"/>)}
    </svg>
    <p className="micro">Onset {monthLabel(chosen,chosen.onset!)} · Peak {peakText} · End {monthLabel(chosen,chosen.end!)}. Month-level timing; the shaded window can include quiet intervals between separate burning periods.{chosen.lowData?' This season includes low-data calibration and is excluded from trends.':''}{chosen.onset===0||chosen.end===11?' Activity reaches a fire-year boundary; interpret timing relative to this fixed year.':''}</p>
   </div>:<div className="season-empty" role="status">{chosen.status==='no_activity'?'All 12 months are eligible, with zero activity. There is no measurable season.':`Only ${chosen.eligibleMonths} of 12 months are eligible. A complete season is required; missing or provisional months are never filled with zero.`}</div>}
  </>}
  <div className="season-history">
   <div className="season-history-title"><span className="eyebrow">THE SEASON, YEAR BY YEAR</span><span><i className="season-window-key"/> 10–90% window <b className="season-peak-key">◆</b> Peak month</span></div>
   <div className="season-history-axis"><span>SEASON</span><div>{orderedMonths.map(m=><span key={m}>{m}</span>)}</div><span>MONTHS</span></div>
   <div className="season-history-scroll" tabIndex={0} aria-label="Season history; scroll for earlier years">
    {[...annual].reverse().map(s=><button className={`season-year-row ${chosen?.year===s.year?'selected':''}`} key={s.year} disabled={loading} onClick={()=>setPicked(s.year)} aria-pressed={chosen?.year===s.year} aria-label={`${s.label}: ${s.status==='complete'?`onset ${monthLabel(s,s.onset!)}, peak ${s.peaks.map(i=>monthLabel(s,i)).join(' and ')}, end ${monthLabel(s,s.end!)}, ${s.duration} months${s.lowData?', low-data calibration':''}`:s.status==='incomplete'?`incomplete, ${s.eligibleMonths} of 12 eligible months`:'no activity'}`}>
     <span>{s.label}{s.lowData&&<sup>*</sup>}</span><div className="season-track">{s.status==='complete'?<><i className="season-window" style={{left:`${s.onset!/12*100}%`,width:`${s.duration!/12*100}%`}}/>{s.peaks.map(i=><b className="season-peak" key={i} style={{left:`${(i+.5)/12*100}%`}}>◆</b>)}</>:<span className="season-row-status">{s.status==='incomplete'?`Incomplete · ${s.eligibleMonths}/12`:'No activity'}</span>}</div><span>{s.duration??'—'}</span>
    </button>)}
   </div>
  </div>
  <div className="season-trend-heading"><div><span className="eyebrow">IS THE RHYTHM CHANGING?</span><h3>Timing across the years.</h3></div><div className="segmented" aria-label="Season trend period">{([{id:'viirs',label:'VIIRS era · 2013+'},{id:'full',label:'Full record'}] as const).map(e=><button key={e.id} className={era===e.id?'active':''} aria-pressed={era===e.id} onClick={()=>setEra(e.id)}>{e.label}</button>)}</div></div>
  <p className="micro season-trend-scope">Within the selected {start}–{end} history window{nsw?' (starting fire years)':''}. {era==='viirs'?'VIIRS-era seasons start in 2013 or later, reducing dependence on the MODIS-to-VIIRS transition.':'Full-record trends include calibrated MODIS history and its transfer uncertainty.'}</p>
  <div className="season-trends">{metrics.map((m,i)=>{const t=trends[i];return <article key={m.key}><span>{m.label}</span><strong>{t?trendText(t.slope,m.key):'Insufficient evidence'}</strong><small>{t?'per decade · median pairwise slope':'10 seasons spanning ≥10 years required'}</small>{t?<p>{trendText(t.change,m.key)} in the latest five vs earliest five seasons.<br/><span>{t.early} → {t.late} · n={t.n}</span></p>:<p>{m.key==='peak'?'Tied peaks are excluded; peak timing spanning more than six months has no linear trend.':'Incomplete, zero-activity and low-data years are excluded.'}</p>}</article>;})}</div>
  <details className="season-method"><summary>How to read these season insights <ArrowUpRight size={13}/></summary><p>Onset and end are the first months reaching 10% and 90% of cumulative annual harmonized fire-active cell-days. Peak is the maximum month; equal maxima are all shown. Duration counts calendar months from onset through end, inclusive. These are monthly activity windows, not ignition dates, days of continuous fire, or fire-event counts.</p><p>All 12 months must be eligible, finite and nonnegative, with positive annual activity. Low-data seasons (*) are shown but excluded from trends. Trends use the median of all pairwise slopes (Theil–Sen), in months per decade; the additional comparison uses medians of the earliest and latest five eligible seasons. At least 10 seasons over a span of 10 years are required. A zero slope does not prove stability. No significance test or timing confidence interval is claimed; monthly resolution, sensor transfer, clouds and local allocation can affect results.</p><p>Multiple burning periods can share one 10–90% window, particularly in Sri Lanka. January–December or July–June boundaries can split activity; a peak crossing that boundary has no linear trend here. Non-vegetation selections describe thermal-activity timing rather than a vegetation fire season. Selected areas use regional calibration, with availability inferred from the archive.</p><a href="https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2013JG002518" target="_blank" rel="noreferrer">Cumulative-season method reference ↗</a><p className="micro">Adapted to monthly fire-active cell-days; the paper uses a different activity measure. Snapshot {exportContext.snapshot}.</p></details>
 </section>;
}
