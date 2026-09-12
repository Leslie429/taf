/**
 * Enregistre le service worker qui rend l'application consultable sans réseau.
 *
 * Silencieux en cas d'échec : un navigateur sans service worker, ou une page
 * servie en clair hors `localhost`, doit continuer de fonctionner — il n'y
 * manquera que le mode hors connexion.
 *
 * En développement, on s'abstient : le serveur Vite sert des modules non
 * groupés, qu'un cache d'abord figerait entre deux rechargements à chaud.
 */
export function registerSW(): void {
  if (import.meta.env.DEV) return
  if (!('serviceWorker' in navigator)) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Rien à signaler à l'utilisateur : l'application marche sans.
    })
  })
}
