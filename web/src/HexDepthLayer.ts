import {MercatorCoordinate,type CustomLayerInterface,type Map} from 'mapbox-gl';
import * as THREE from 'three';
import {gsap} from 'gsap';

// One mesh shares Mapbox's WebGL context; no second canvas or permanent animation loop.
export class HexDepthLayer implements CustomLayerInterface {
 readonly id='detections-depth';readonly type='custom' as const;readonly renderingMode='3d' as const;
 private map?:Map;private renderer?:THREE.WebGLRenderer;private camera=new THREE.Camera();private scene=new THREE.Scene();
 private geometry=new THREE.BufferGeometry();private material=new THREE.MeshBasicMaterial({vertexColors:true,transparent:true,opacity:.9,side:THREE.DoubleSide});
 private faces:{cell:number;count:number}[]=[];private baseColors=new Float32Array();private selectedCell:number|null=null;private outline?:THREE.LineSegments;private outlineMaterial=new THREE.LineBasicMaterial({color:'#ffe5b3',depthTest:false,transparent:true,opacity:1});private projectionReady=false;
 private mesh=new THREE.Mesh(this.geometry,this.material);private origin:MercatorCoordinate;
 constructor(center:[number,number]){this.origin=MercatorCoordinate.fromLngLat(center);this.mesh.frustumCulled=false;this.scene.add(this.mesh);this.scene.visible=false;}
 onAdd(map:Map,gl:WebGLRenderingContext|WebGL2RenderingContext){this.map=map;this.renderer=new THREE.WebGLRenderer({canvas:map.getCanvas(),context:gl as WebGL2RenderingContext,antialias:true});this.renderer.autoClear=false;}
 setData(data:GeoJSON.FeatureCollection){
  const positions:number[]=[],colors:number[]=[];this.faces=[];
  const vertex=(p:number[],z:number,color:THREE.Color,shade:number)=>{const v=MercatorCoordinate.fromLngLat([p[0],p[1]],z);positions.push((v.x-this.origin.x)*1e6,(v.y-this.origin.y)*1e6,v.z*1e6);colors.push(color.r*shade,color.g*shade,color.b*shade);};
  for(const f of data.features){if(f.geometry.type!=='Polygon')continue;const ring=f.geometry.coordinates[0].slice(0,-1),center=ring.reduce((a,p)=>[a[0]+p[0]/ring.length,a[1]+p[1]/ring.length],[0,0]);
   const height=250+Math.min(3,Math.log10(Math.max(1,Number(f.properties?.count))))*3600,color=new THREE.Color(String(f.properties?.color));
   for(let i=0;i<ring.length;i++){const a=ring[i],b=ring[(i+1)%ring.length];this.faces.push(...Array.from({length:3},()=>({cell:Number(f.properties?.cell),count:Number(f.properties?.count)})));vertex(center,height,color,1);vertex(a,height,color,1);vertex(b,height,color,1);for(const [p,z] of [[a,0],[b,0],[b,height],[a,0],[b,height],[a,height]] as [number[],number][])vertex(p,z,color,.55+(i%3)*.08);}
  }
  const next=new THREE.BufferGeometry();next.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));next.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));this.geometry.dispose();this.geometry=next;this.mesh.geometry=next;this.baseColors=new Float32Array(colors);this.setSelected(this.selectedCell);
  if(this.scene.visible)this.reveal();this.map?.triggerRepaint();
 }
 setSelected(cell:number|null){this.selectedCell=cell;const color=this.geometry.getAttribute('color');if(!color)return;color.array.set(this.baseColors);const selected:number[]=[];const highlight=new THREE.Color('#ffd190');for(let i=0;i<this.faces.length;i++)if(this.faces[i].cell===cell){for(let vertex=i*3;vertex<i*3+3;vertex++){color.setXYZ(vertex,highlight.r,highlight.g,highlight.b);const positions=this.geometry.getAttribute('position');selected.push(positions.getX(vertex),positions.getY(vertex),positions.getZ(vertex));}}color.needsUpdate=true;
 if(this.outline){this.mesh.remove(this.outline);this.outline.geometry.dispose();this.outline=undefined;}if(selected.length){const shape=new THREE.BufferGeometry();shape.setAttribute('position',new THREE.Float32BufferAttribute(selected,3));const edges=new THREE.EdgesGeometry(shape);shape.dispose();this.outline=new THREE.LineSegments(edges,this.outlineMaterial);this.outline.renderOrder=1;this.outline.frustumCulled=false;this.mesh.add(this.outline);}this.map?.triggerRepaint();}
 private reveal(){gsap.killTweensOf(this.mesh.scale);this.mesh.scale.z=.03;gsap.to(this.mesh.scale,{z:1,duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:1.1,ease:'power3.out',onUpdate:()=>this.map?.triggerRepaint()});}
 setVisible(visible:boolean){this.scene.visible=visible;if(visible)this.reveal();else gsap.killTweensOf(this.mesh.scale);this.map?.triggerRepaint();}
 pick(x:number,y:number){if(!this.scene.visible||!this.projectionReady||!this.map)return null;const canvas=this.map.getCanvas(),ndc=new THREE.Vector2(x/canvas.clientWidth*2-1,1-y/canvas.clientHeight*2),inverse=this.camera.projectionMatrix.clone().invert(),near=new THREE.Vector3(ndc.x,ndc.y,-1).applyMatrix4(inverse),far=new THREE.Vector3(ndc.x,ndc.y,1).applyMatrix4(inverse),ray=new THREE.Raycaster(near,far.sub(near).normalize());this.mesh.updateWorldMatrix(true,false);const hit=ray.intersectObject(this.mesh,false)[0];return hit?.faceIndex==null?null:this.faces[hit.faceIndex]??null;}
 render(_gl:WebGLRenderingContext|WebGL2RenderingContext,matrix:number[]){if(!this.renderer||!this.scene.visible)return;const transform=new THREE.Matrix4().makeTranslation(this.origin.x,this.origin.y,0).scale(new THREE.Vector3(1e-6,1e-6,1e-6));this.camera.projectionMatrix=new THREE.Matrix4().fromArray(matrix).multiply(transform);this.projectionReady=true;this.renderer.resetState();this.renderer.render(this.scene,this.camera);this.renderer.resetState();}
 onRemove(){gsap.killTweensOf(this.mesh.scale);this.geometry.dispose();this.material.dispose();this.outline?.geometry.dispose();this.outlineMaterial.dispose();this.renderer?.dispose();this.map=undefined;}
}
