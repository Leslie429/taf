/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/* Le service worker est servi tel quel depuis `public/`, hors du bundle et
 * hors du typage : il n'exporte rien, il ne fait que s'abonner à ses
 * événements au chargement. Seul son test l'importe. */
declare module '*/public/sw.js'
