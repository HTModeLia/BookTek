import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// fs.allow : le serveur de développement lit aussi ../CHANGELOG.md (importé dans À propos)
export default defineConfig({ plugins: [react()], base: './', server: { fs: { allow: ['..'] } } })
