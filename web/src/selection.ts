export type Position=[number,number];
export type Area={kind:'polygon'|'circle';geometry:{type:'Polygon';coordinates:Position[][]};label:string};
export type AreaResult={rows:import('./analytics').Row[];cell_ids:string[];cell_count:number;grid_area_km2:number};
export function polygonArea(points:Position[]):Area{
 if(points.length<3)throw new Error('Add at least three points to enclose an area.');
 if(points.length>500)throw new Error('Use at most 500 points.');
 if(points.some(p=>p.length!==2||!p.every(Number.isFinite)||Math.abs(p[0])>180||Math.abs(p[1])>85))throw new Error('Use valid longitude and latitude coordinates.');
 const ring:Position[]=[...points];
 if(ring[0][0]!==ring.at(-1)![0]||ring[0][1]!==ring.at(-1)![1])ring.push([...ring[0]]);
 const orient=(a:Position,b:Position,c:Position)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
 const on=(a:Position,b:Position,p:Position)=>Math.abs(orient(a,b,p))<1e-10&&p[0]>=Math.min(a[0],b[0])-1e-10&&p[0]<=Math.max(a[0],b[0])+1e-10&&p[1]>=Math.min(a[1],b[1])-1e-10&&p[1]<=Math.max(a[1],b[1])+1e-10;
 for(let i=0;i<ring.length-1;i++)for(let j=i+1;j<ring.length-1;j++){
  if(j===i+1||(i===0&&j===ring.length-2))continue;
  const [a,b,c,d]=[ring[i],ring[i+1],ring[j],ring[j+1]];
  if((orient(a,b,c)*orient(a,b,d)<0&&orient(c,d,a)*orient(c,d,b)<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b))throw new Error('The boundary crosses itself. Undo a point or redraw the polygon.');
 }
 const twiceArea=ring.slice(0,-1).reduce((sum,p,i)=>sum+p[0]*ring[i+1][1]-ring[i+1][0]*p[1],0);
 if(Math.abs(twiceArea)<1e-10)throw new Error('These points do not enclose an area.');
 return {kind:'polygon',geometry:{type:'Polygon',coordinates:[ring]},label:'Custom polygon'};
}
export function coordinateArea(lat:number,lon:number,radius:number):Area{
 if(![lat,lon,radius].every(Number.isFinite)||Math.abs(lat)>85||Math.abs(lon)>180||radius<.5||radius>250)throw new Error('Use latitude −85 to 85, longitude −180 to 180, and a radius of 0.5–250 km.');
 const r=Math.PI/180,phi=lat*r,lambda=lon*r,angle=radius/6371.0088;
 const points:Position[]=Array.from({length:64},(_,i)=>{const bearing=2*Math.PI*i/64;const p=Math.asin(Math.sin(phi)*Math.cos(angle)+Math.cos(phi)*Math.sin(angle)*Math.cos(bearing));const l=lambda+Math.atan2(Math.sin(bearing)*Math.sin(angle)*Math.cos(phi),Math.cos(angle)-Math.sin(phi)*Math.sin(p));return [((l/r+540)%360)-180,p/r];});
 const area=polygonArea(points);
 return {...area,kind:'circle',label:`${lat.toFixed(3)}, ${lon.toFixed(3)} · ${radius} km radius`};
}
export async function postJSON<T>(path:string,body:unknown,signal?:AbortSignal):Promise<T>{
 let response:Response;
 try{response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});}catch(error){if((error as Error).name==='AbortError')throw error;throw new Error('Local area analysis is unavailable. Restart the local app and retry.');}
 let result;try{result=await response.json();}catch(error){if((error as Error).name==='AbortError')throw error;throw new Error('Local area analysis is unavailable. Restart the local app and retry.');}
 if(!response.ok)throw new Error(result.error||'This area could not be processed. Try another selection.');
 return result;
}
