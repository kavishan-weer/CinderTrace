import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {existsSync} from 'node:fs';
export default defineConfig(({command})=>{
  if(command==='build'&&!existsSync(new URL('./public/data/manifest.json',import.meta.url))) {
    throw new Error('Web archive missing. From the repository root, run .venv/bin/python -m pipeline.export_web before building.');
  }
  return {plugins:[react()],server:{proxy:{'/api':{target:process.env.EMBERLINE_API_TARGET||'http://127.0.0.1:8787',changeOrigin:false}}},preview:{proxy:{'/api':{target:process.env.EMBERLINE_API_TARGET||'http://127.0.0.1:8787',changeOrigin:false}}},build:{chunkSizeWarningLimit:1600}};
});
