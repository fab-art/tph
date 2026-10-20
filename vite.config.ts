import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
export default defineConfig({ plugins:[react(),VitePWA({registerType:'autoUpdate',includeAssets:['pwa-icon.svg'],manifest:{name:'TUUZA Pharmacy',short_name:'TUUZA',description:'Pharmacy procurement and inventory management',theme_color:'#073b3a',background_color:'#f5f7f6',display:'standalone',start_url:'/',icons:[{src:'/pwa-icon.svg',sizes:'any',type:'image/svg+xml',purpose:'any maskable'}]},workbox:{globPatterns:['**/*.{js,css,html,svg,json}']}})], server:{port:5173} })