// Development only. Public users run the checked-in compiler without npm.
import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.join(root,'city_generator/road_runtime');fs.mkdirSync(out,{recursive:true});
const files=['authoringV2.ts','authoring.ts','geometry.ts','model.ts'];
const compiler=process.env.CITY_TSC??path.join(root,'road_authoring/node_modules/.bin/tsc');
execFileSync(compiler,['--ignoreConfig','--module','commonjs','--target','es2022','--skipLibCheck','--outDir',out,...files.map(f=>path.join(root,'road_authoring/src',f))],{stdio:'inherit'});
fs.writeFileSync(path.join(out,'package.json'),JSON.stringify({type:'commonjs'}));
fs.writeFileSync(path.join(out,'sources.json'),JSON.stringify(Object.fromEntries(files.map(f=>[f,createHash('sha256').update(fs.readFileSync(path.join(root,'road_authoring/src',f))).digest('hex')])),null,2));
