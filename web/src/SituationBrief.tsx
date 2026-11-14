import {useEffect,useState} from 'react';
import {FileDown,Check,ArrowUpRight} from 'lucide-react';
import {buildBrief,type BriefInput} from './brief';
import {postJSON} from './selection';
import './brief.css';

export default function SituationBrief({input,disabled}:{input:BriefInput;disabled:boolean}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [ready,setReady]=useState<{url:string;filename:string;label:string}|null>(null);
 const signature=JSON.stringify([input.selected,input.start,input.end,input.nsw,input.context,input.spatial]);
 useEffect(()=>{setReady(null);setError('');},[signature,input.data]);
 useEffect(()=>{if(!ready)return;const timer=setTimeout(()=>setReady(null),600000);return()=>clearTimeout(timer);},[ready]);
 async function generate(){
  setBusy(true);setError('');setReady(null);
  const brief=buildBrief(input);
  try{
   const result=await postJSON<{url:string;filename:string}>('/api/exports/brief',{brief});
   if(!/^\/api\/exports\/[A-Za-z0-9_-]+\.pdf$/.test(result.url))throw new Error('The brief download response was invalid. Try again.');
   setReady({...result,label:`${brief.area} · ${brief.selected_label} · ${brief.filters} · history ${brief.window}`});
   const a=document.createElement('a');a.href=result.url;a.download=result.filename;a.click();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <section className="brief-banner" aria-labelledby="brief-title">
  <div className="brief-icon"><FileDown size={23}/></div>
  <div className="brief-copy"><span className="eyebrow">FROM INSIGHT TO A SHAREABLE BRIEF</span><h3 id="brief-title">Your area. One page. The evidence.</h3><p>Selected month, historical comparison, burning calendar and latest complete season - with findings, sources and uncertainty. Generated locally.</p></div>
  <button className="brief-generate" onClick={generate} disabled={disabled||busy}><FileDown size={15}/>{busy?'Creating your brief…':'Situation Brief PDF'}<ArrowUpRight size={14}/></button>
  {busy&&<p className="brief-feedback" role="status">Preparing the current selection. The download will be labelled with its area, month and filters.</p>}
  {error&&<p className="brief-feedback area-error" role="alert">{error}</p>}
  {ready&&<div className="brief-feedback" role="status"><a href={ready.url} download={ready.filename}><Check size={13}/> One-page PDF ready · Download again ↗</a><small>{ready.label} · link expires in 10 minutes</small></div>}
 </section>;
}
