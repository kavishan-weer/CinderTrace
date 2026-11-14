import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
const root=fileURLToPath(new URL('../../',import.meta.url));
const preview=process.argv.includes('--preview');
const args=process.argv.slice(2).filter(arg=>arg!=='--preview');
const python=process.env.EMBERLINE_PYTHON||`${root}.venv/bin/python`;
const api=spawn(python,['-u','-m','pipeline.local_api'],{cwd:root,stdio:['ignore','pipe','inherit']});
let vite,closing=false;
function stop(code=0){if(closing)return;closing=true;vite?.kill('SIGTERM');api.kill('SIGTERM');process.exitCode=code;}
api.on('error',()=>{console.error('Could not start local analytics. Check the repository Python environment.');stop(1);});
api.on('exit',code=>{if(!closing)stop(code||1);});
const lines=createInterface({input:api.stdout});
lines.once('line',line=>{const {api_url}=JSON.parse(line);console.log('Local area analytics ready. No data leaves this computer.');vite=spawn(process.execPath,['node_modules/vite/bin/vite.js',...(preview?['preview']:[]),'--host','127.0.0.1',...args],{cwd:fileURLToPath(new URL('../',import.meta.url)),stdio:'inherit',env:{...process.env,EMBERLINE_API_TARGET:api_url}});vite.on('exit',code=>stop(code||0));});
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
