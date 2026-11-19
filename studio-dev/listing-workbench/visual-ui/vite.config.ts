import {defineConfig} from 'vite';
export default defineConfig({define:{'process.env.NODE_ENV':JSON.stringify('production')},base:'/visual-app/',build:{lib:{entry:'main.tsx',formats:['iife'],name:'JunfeiVisualBundle',fileName:()=> 'studio.js'},cssCodeSplit:false,rollupOptions:{output:{inlineDynamicImports:true}}}});
