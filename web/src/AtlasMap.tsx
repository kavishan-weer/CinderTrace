import {useEffect,useMemo,useRef,useState} from 'react';
import maplibregl from 'maplibre-gl';
import {Crosshair,Minus,Plus,Map as MapIcon} from 'lucide-react';
import {SATELLITES,SATELLITE_COLORS,type Observation} from './atlasData';
import 'maplibre-gl/dist/maplibre-gl.css';

type Props={points:Observation[];boundary:GeoJSON.FeatureCollection;onSelect:(id:number|null)=>void;selected:number|null};
const style:maplibregl.StyleSpecification={version:8,sources:{basemap:{type:'raster',tiles:[import.meta.env.VITE_ATLAS_TILE_URL||'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'}},layers:[{id:'background',type:'background',paint:{'background-color':'#142426'}},{id:'basemap',type:'raster',source:'basemap',paint:{'raster-opacity':.23,'raster-saturation':-1,'raster-brightness-max':.62}}]};
const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export default function AtlasMap({points,boundary,onSelect,selected}:Props){
 const host=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null);const callback=useRef(onSelect);callback.current=onSelect;
 const live=useRef(points);live.current=points;const [ready,setReady]=useState(false),[fallback,setFallback]=useState(false),[basemapError,setBasemapError]=useState(false),[hover,setHover]=useState<{x:number;y:number;text:string}|null>(null),[overviewZoom,setOverviewZoom]=useState(1);
 const data=useMemo<GeoJSON.FeatureCollection>(()=>({type:'FeatureCollection',features:points.map(p=>({type:'Feature',id:p.id,geometry:{type:'Point',coordinates:[p.lon,p.lat]},properties:{id:p.id,satellite:p.satellite}}))}),[points]);
 useEffect(()=>{
  if(!host.current)return;
  let m:maplibregl.Map;
  try{m=new maplibregl.Map({container:host.current,style,center:[80.75,7.85],zoom:6,minZoom:3,maxZoom:16,attributionControl:{compact:false},renderWorldCopies:false,dragRotate:false,pitchWithRotate:false,touchPitch:false});}catch{setFallback(true);return;}
  map.current=m;
  m.on('load',()=>{
   m.fitBounds([[79.3,5.65],[82.15,10.05]],{padding:{top:55,bottom:45,left:65,right:65},duration:0});
   m.addSource('atlas-boundary',{type:'geojson',data:boundary});
   m.addLayer({id:'atlas-land',type:'fill',source:'atlas-boundary',paint:{'fill-color':'#28483e','fill-opacity':.43}});
   m.addLayer({id:'atlas-outline',type:'line',source:'atlas-boundary',paint:{'line-color':'#91ad95','line-width':1.2,'line-opacity':.6}});
   m.addSource('atlas-observations',{type:'geojson',data,cluster:true,clusterMaxZoom:8,clusterRadius:28});
   m.addLayer({id:'atlas-clusters',type:'circle',source:'atlas-observations',filter:['has','point_count'],paint:{'circle-color':'#e0a37b','circle-radius':['interpolate',['linear'],['get','point_count'],1,8,20,13,100,19,1000,28],'circle-opacity':.83,'circle-stroke-color':'#f2c9a1','circle-stroke-width':1}});
   m.addLayer({id:'atlas-points',type:'circle',source:'atlas-observations',filter:['!', ['has','point_count']],paint:{'circle-color':['match',['get','satellite'],0,SATELLITE_COLORS[0],1,SATELLITE_COLORS[1],2,SATELLITE_COLORS[2],SATELLITE_COLORS[3]],'circle-radius':['interpolate',['linear'],['zoom'],4,2.3,8,3.1,12,5.8],'circle-opacity':.88,'circle-stroke-color':'#162d2d','circle-stroke-width':.65}});
   m.addLayer({id:'atlas-selected',type:'circle',source:'atlas-observations',filter:['==',['get','id'],-1],paint:{'circle-color':'#fff7e7','circle-radius':8,'circle-opacity':.15,'circle-stroke-color':'#fff3d5','circle-stroke-width':2}});
   setReady(true);
  });
  m.on('error',e=>{if(e.error?.message?.toLowerCase().includes('webgl'))setFallback(true);else setBasemapError(true);});
  m.on('click',async e=>{
   if(!m.getLayer('atlas-points'))return;
   const features=m.queryRenderedFeatures(e.point,{layers:['atlas-points','atlas-clusters']});const feature=features[0];
   if(!feature){callback.current(null);return;}
   if(feature.properties?.cluster){
    const source=m.getSource('atlas-observations') as maplibregl.GeoJSONSource;
    try{const zoom=await source.getClusterExpansionZoom(Number(feature.properties.cluster_id));const coords=(feature.geometry as GeoJSON.Point).coordinates;m.easeTo({center:[coords[0],coords[1]],zoom:Math.max(zoom,m.getZoom()+.7),duration:reduced()?0:650});}catch{setBasemapError(true);}
   }else callback.current(Number(feature.properties?.id));
  });
  m.on('mousemove',e=>{
   if(!m.getLayer('atlas-points'))return;
   const f=m.queryRenderedFeatures(e.point,{layers:['atlas-points','atlas-clusters']})[0];m.getCanvas().style.cursor=f?'pointer':'';
   if(!f){setHover(null);return;}
   const p=live.current.find(p=>p.id===Number(f.properties?.id));
   setHover({x:e.point.x,y:e.point.y,text:f.properties?.cluster?`${Number(f.properties.point_count).toLocaleString()} detections · click to zoom`:p?`${SATELLITES[p.satellite]} · ${new Date(p.timestamp*1000).toISOString().slice(0,16).replace('T',' ')} UTC`:'Detection'});
  });
  m.on('mouseout',()=>setHover(null));
  return()=>{setReady(false);map.current=null;m.remove();};
 // Dataset geometry is fixed for this pilot. Subsequent point selections update its source.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 useEffect(()=>{if(ready)(map.current?.getSource('atlas-observations') as maplibregl.GeoJSONSource)?.setData(data);setHover(null);},[data,ready]);
 useEffect(()=>{if(!ready)return;const m=map.current;m?.setFilter('atlas-selected',['==',['get','id'],selected??-1]);const p=live.current.find(p=>p.id===selected);if(p&&m)m.easeTo({center:[p.lon,p.lat],zoom:Math.max(10,m.getZoom()),duration:reduced()?0:600});},[selected,ready]);
 const fit=()=>{map.current?.fitBounds([[79.3,5.65],[82.15,10.05]],{padding:60,duration:reduced()?0:700});setOverviewZoom(1);};
 const svgPath=useMemo(()=>{const xy=(c:number[])=>`${(c[0]-79.1)/3.3*720},${(10.25-c[1])/4.9*660}`;return boundary.features.map(f=>{const g=f.geometry;if(g.type==='MultiPolygon')return g.coordinates.map(p=>p.map(r=>'M'+r.map(xy).join('L')+'Z').join('')).join('');if(g.type==='Polygon')return g.coordinates.map(r=>'M'+r.map(xy).join('L')+'Z').join('');return '';}).join('');},[boundary]);
 return <div className="atlas-map" aria-label="Satellite detection map of Sri Lanka">
  <div ref={host} className="atlas-map-host" style={{visibility:fallback?'hidden':undefined}}/>
  {fallback&&<svg className="atlas-map-fallback" viewBox="0 0 720 660" role="img" aria-label={`Geographic overview of ${points.length} selected detections`}><defs><pattern id="atlas-grid" width="72" height="66" patternUnits="userSpaceOnUse"><path d="M72 0H0V66" fill="none" stroke="#344b4b" strokeWidth=".5"/></pattern></defs><rect width="720" height="660" fill="url(#atlas-grid)"/><g transform={`translate(360 330) scale(${overviewZoom}) translate(-360 -330)`}><path d={svgPath} fill="#29443b" fillRule="evenodd" stroke="#8aa18e" strokeWidth="1"/>{points.map(p=><circle key={p.id} cx={(p.lon-79.1)/3.3*720} cy={(10.25-p.lat)/4.9*660} r={selected===p.id?5:1.7} fill={SATELLITE_COLORS[p.satellite]} fillOpacity=".7" onClick={()=>onSelect(p.id)}><title>{SATELLITES[p.satellite]} · {new Date(p.timestamp*1000).toISOString()}</title></circle>)}</g><text x="50" y="600" fill="#819b94" fontSize="12" letterSpacing="3">INDIAN OCEAN</text></svg>}
  <div className="atlas-map-heading"><span className="atlas-map-tag"><MapIcon size={13}/> SRI LANKA <span>2023 PILOT</span></span><span className="atlas-map-scope">Counts cover the full study area</span></div>
  <div className="atlas-map-tools"><button onClick={()=>{map.current?.zoomIn({duration:reduced()?0:250});setOverviewZoom(z=>Math.min(5,z*1.3));}} aria-label="Zoom in"><Plus size={17}/></button><button onClick={()=>{map.current?.zoomOut({duration:reduced()?0:250});setOverviewZoom(z=>Math.max(1,z/1.3));}} aria-label="Zoom out"><Minus size={17}/></button><button onClick={fit} aria-label="Fit Sri Lanka"><Crosshair size={17}/></button></div>
  {hover&&!fallback&&<div className="atlas-map-tooltip" style={{left:Math.min(hover.x+14,(host.current?.clientWidth||600)-250),top:hover.y+16}}>{hover.text}</div>}
  {(fallback||basemapError)&&<div className="atlas-map-notice" role="status">{fallback?'Geographic overview · WebGL unavailable':'Basemap connection limited · observations remain available'}</div>}
  {!points.length&&<div className="atlas-map-empty"><span>NO RECORDED DETECTIONS</span><p>Try another date window or satellite selection.</p></div>}
  <div className="atlas-map-key"><i/> Clusters count observations <span>Zoom in for individual pixels</span></div>
 </div>;
}
