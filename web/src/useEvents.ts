import {useEffect,useState} from 'react';
import {postJSON,type Area} from './selection';
import type {EventResult,EventDetail} from './events';
export function useEvents(region:string,month:string,sub:string,area:Area|null){
 const [active,setActive]=useState(false),[satellite,setSatellite]=useState('Suomi-NPP'),[singletons,setSingletons]=useState(false);
 const [result,setResult]=useState<EventResult|null>(null),[selectedId,setSelectedId]=useState<string|null>(null),[detail,setDetail]=useState<EventDetail|null>(null);
 const [day,setDay]=useState('all'),[busy,setBusy]=useState(false),[detailBusy,setDetailBusy]=useState(false),[error,setError]=useState(''),[detailError,setDetailError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{if(!active){setResult(null);setDetail(null);setSelectedId(null);return;}const ac=new AbortController();setBusy(true);setError('');setResult(null);setDetail(null);setSelectedId(null);setDay('all');
 postJSON<EventResult>('/api/events/query',{region,month,satellite,include_singletons:singletons,sub:!area&&sub!=='all'?Number(sub):null,polygon:area?.geometry||null},ac.signal).then(r=>{if(!ac.signal.aborted){setResult(r);setBusy(false);}}).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setBusy(false);}});return()=>ac.abort();},[active,region,month,sub,area,satellite,singletons,retry]);
 useEffect(()=>{if(!active||!selectedId){setDetail(null);setDetailBusy(false);setDetailError('');return;}const ac=new AbortController();setDetail(null);setDetailBusy(true);setDetailError('');
 postJSON<EventDetail>('/api/events/detail',{region,satellite,event_id:selectedId,day},ac.signal).then(r=>{if(!ac.signal.aborted){setDetail(r);setDetailBusy(false);}}).catch(e=>{if(e.name!=='AbortError'){setDetailError(e.message);setDetailBusy(false);}});return()=>ac.abort();},[active,selectedId,region,satellite,day,retry]);
 function select(id:string){setDay('all');setSelectedId(id);}
 return {active,setActive,satellite,setSatellite,singletons,setSingletons,result,selectedId,select,detail,day,setDay,busy,detailBusy,error,detailError,retry:()=>setRetry(r=>r+1)};
}
export type EventsState=ReturnType<typeof useEvents>;
