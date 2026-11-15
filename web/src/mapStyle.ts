import type {Map, StyleSpecification} from 'mapbox-gl';

export const MAPBOX_TOKEN=import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string|undefined;
export const LOCAL_MAP_STYLE:StyleSpecification={version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#142e2c'}}]};

// Keep Mapbox's streets and place hierarchy, with the observatory's ink-and-sage palette.
export function styleObservatoryMap(map:Map){
 for(const layer of map.getStyle().layers||[]){
  const id=layer.id.toLowerCase();
  if(layer.type==='background')map.setPaintProperty(layer.id,'background-color','#1c3832');
  if(layer.type==='fill'){
   const color=id.includes('water')?'#102b2c':id.includes('park')||id.includes('landuse')?'#244238':id.includes('building')?'#315047':'#203b34';
   map.setPaintProperty(layer.id,'fill-color',color);
  }
  if(layer.type==='line'){
   map.setPaintProperty(layer.id,'line-color',id.includes('water')?'#3c6257':id.includes('boundary')?'#8eaa80':id.includes('road')||id.includes('tunnel')||id.includes('bridge')?'#57705a':'#36584b');
   if(id.includes('road')||id.includes('tunnel')||id.includes('bridge'))map.setPaintProperty(layer.id,'line-opacity',.36);
  }
  if(layer.type==='symbol'&&layer.layout?.['text-field']){
   map.setPaintProperty(layer.id,'text-color',id.includes('water')?'#74978c':'#c2cdb1');
   map.setPaintProperty(layer.id,'text-halo-color','#17332e');
   map.setPaintProperty(layer.id,'text-halo-width',1.5);
   if(id.includes('poi')||id.includes('transit'))map.setLayoutProperty(layer.id,'visibility','none');
  }
 }
}
