/* Service worker — la coque de l'application hors connexion.
 *
 * Deux règles, et une abstention.
 *
 * Navigation : réseau d'abord, repli sur l'index en cache. L'application se
 * lance donc sans réseau, et un déploiement se voit dès le premier chargement
 * réussi — l'inverse (cache d'abord) ferait traîner une version périmée.
 *
 * Fichiers versionnés : cache d'abord. Vite met une empreinte dans leur nom,
 * ils sont immuables ; un nouveau déploiement change les noms, pas le contenu
 * d'un fichier déjà servi.
 *
 * L'abstention porte sur l'API. Rien de ce qui vient de /api n'est mis en
 * cache ici : ce sont des réponses authentifiées, et le Cache Storage n'est ni
 * cloisonné par compte ni vidé à la déconnexion. Les données consultables hors
 * connexion passent par le cache applicatif (src/offline/persist.ts), qui,
 * lui, est effacé quand l'utilisateur se déconnecte.
 */
const VERSION = 'v1'
const COQUE = `tontine-coque-${VERSION}`
const STATIQUES = `tontine-statiques-${VERSION}`

// L'index et les icônes suffisent à afficher quelque chose sans réseau ; le
// reste se met en cache au fil des requêtes. Précacher la liste exacte des
// fichiers de Vite imposerait de la régénérer à chaque construction.
const COQUE_FICHIERS = ['/', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(COQUE)
      .then((cache) => cache.addAll(COQUE_FICHIERS))
      // Le nouveau worker prend la main sans attendre la fermeture des onglets.
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((noms) =>
        Promise.all(
          noms
            .filter((nom) => nom.startsWith('tontine-') && nom !== COQUE && nom !== STATIQUES)
            .map((nom) => caches.delete(nom)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

async function coqueOuReseau(request) {
  try {
    const reponse = await fetch(request)
    // La navigation a abouti : on rafraîchit la coque pour la prochaine fois.
    const cache = await caches.open(COQUE)
    await cache.put('/', reponse.clone())
    return reponse
  } catch {
    const cache = await caches.open(COQUE)
    const secours = await cache.match('/')
    if (secours) return secours
    throw new Error('Application indisponible hors connexion.')
  }
}

async function cacheDAbord(request) {
  const cache = await caches.open(STATIQUES)
  const connu = await cache.match(request)
  if (connu) return connu

  const reponse = await fetch(request)
  // Une réponse partielle ou une erreur n'a rien à faire en cache.
  if (reponse.ok && reponse.status === 200) await cache.put(request, reponse.clone())
  return reponse
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  // Tout ce qui n'est pas à nous — l'API, les polices Google — passe au
  // travers : le navigateur s'en occupe mieux que nous.
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return

  if (request.mode === 'navigate') {
    event.respondWith(coqueOuReseau(request))
    return
  }
  event.respondWith(cacheDAbord(request))
})

// La page demande la main après un déploiement : on la lui rend sans recharger.
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') void self.skipWaiting()
})
