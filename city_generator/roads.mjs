// Headless adapter: the GUI and agents execute the exact same compiler.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(import.meta.url);
const cache=path.join(root,'city_generator/road_runtime');
try {
 const signatures=JSON.parse(fs.readFileSync(path.join(cache,'sources.json')));
 for(const [name,hash] of Object.entries(signatures)) {
  if(createHash('sha256').update(fs.readFileSync(path.join(root,'road_authoring/src',name))).digest('hex')!==hash)throw new Error('Road source changed: run node city_generator/compile_roads.mjs');
 }
 const api=require(path.join(cache,'authoringV2.js'));
 const {DEFAULT_STYLE}=require(path.join(cache,'authoring.js'));
 const input=JSON.parse(fs.readFileSync(0,'utf8'));
 let doc;
 if(input.document) doc=structuredClone(input.document);
 else {
  doc=structuredClone(api.EMPTY_EDITOR_V2); doc.scene={time_of_day:input.time_of_day??'day'};
  for(const road of input.roads??[]) {
   const style={...DEFAULT_STYLE,...road.style};
   const result=api.addRoad(doc,road.points,style);
   if(!result.validation.valid)throw new Error(result.validation.errors.join('\n'));
   doc=result.document;
   if(road.id){if(doc.roads.slice(0,-1).some(r=>r.id===road.id))throw new Error('Duplicate road ID');doc.roads.at(-1).id=road.id;}
  }
  for(const item of input.junctions??[]) {
   const matches=Object.values(doc.keyPoints).filter(p=>p.kind==='junction'&&Math.hypot(p.position[0]-item.at[0],p.position[1]-item.at[1])<.05);
   if(matches.length!==1)throw new Error('Junction selector must resolve once: '+JSON.stringify(item.at));
   doc.junctions[matches[0].id]={...doc.junctions[matches[0].id],...item.style};
  }
  doc.components=input.components??[];
 }
 for(const target of input.driveways??[]) {
  const result=api.addDrivewayCutout(doc,target);
  if(!result.validation.valid)throw new Error(result.validation.errors.join('\n'));
  doc=result.document;
 }
 const styleKeys=new Set(Object.keys(DEFAULT_STYLE));
 for(const road of doc.roads) {
  for(const key of Object.keys(road.style))if(!styleKeys.has(key))throw new Error(road.id+': unknown style '+key);
  for(const key of ['bicycle_lane','curb_parking_prohibition','tactile_paving','street_lights'])if(typeof road.style[key]!=='boolean')throw new Error(road.id+': '+key+' must be boolean');
  if(!Number.isFinite(road.style.speed_limit)||road.style.speed_limit<=0)throw new Error(road.id+': invalid speed_limit');
  if(!['none','both'].includes(road.style.sidewalks))throw new Error(road.id+': invalid sidewalks');
  if(!['median','none','orange_solid','white_solid','white_dashed'].includes(road.style.center_treatment))throw new Error(road.id+': invalid center_treatment');
  if(!['narrow','wide'].includes(road.style.median_width))throw new Error(road.id+': invalid median_width');
 }
 for(const point of Object.values(doc.keyPoints))if(point.position.length!==2||!point.position.every(Number.isFinite))throw new Error('Coordinates must be finite pairs');
 const result=api.validateEditorV2(doc);
 if(!result.valid)throw new Error(result.errors.join('\n'));
 const network=api.compileEditorV2(doc);

 process.stdout.write(JSON.stringify({valid:true,document:doc,network}));
} catch(error) {process.stdout.write(JSON.stringify({valid:false,errors:[String(error.message)]}));process.exitCode=1;}
