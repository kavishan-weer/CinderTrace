import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const preview=process.argv.includes('--preview');
const args=process.argv.slice(2).filter(arg=>arg!=='--preview');
const vite=spawn(process.execPath,['node_modules/vite/bin/vite.js',...(preview?['preview']:[]),'--host','127.0.0.1',...args],{cwd:fileURLToPath(new URL('../',import.meta.url)),stdio:'inherit'});
vite.on('exit',code=>{process.exitCode=code||0;});
process.on('SIGINT',()=>vite.kill('SIGINT'));
process.on('SIGTERM',()=>vite.kill('SIGTERM'));
