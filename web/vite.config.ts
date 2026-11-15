import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {existsSync,readdirSync,writeFileSync,readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
export default defineConfig(({command})=>{
  if(command==='build'&&!existsSync(new URL('./site-public/ready/manifest.json',import.meta.url))) {
    throw new Error('Ready dataset missing. Run .venv/bin/python -m pipeline.export_ready_site from the repository root.');
  }
  return {plugins:[react(),{name:'cindertrace-field-mode',closeBundle(){const dir=new URL('./dist/',import.meta.url),assets=readdirSync(new URL('assets/',dir)).filter(f=>/\.(js|css|woff2)$/.test(f)).map(f=>'/assets/'+f),version=createHash('sha256').update(assets.join('|')).digest('hex').slice(0,12);writeFileSync(new URL('offline-assets.json',dir),JSON.stringify(['/','/index.html',...assets]));const worker=new URL('sw.js',dir);writeFileSync(worker,readFileSync(worker,'utf8').replace('__CINDERTRACE_BUILD__',version));}}],publicDir:'site-public',build:{chunkSizeWarningLimit:1600}};
});
