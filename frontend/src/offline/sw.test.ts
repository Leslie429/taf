import { beforeEach, describe, expect, it, vi } from 'vitest'

/* Le service worker vit hors de `src` et hors du bundle : il est chargé ici
 * dans un environnement gréé à la main — un `self`, un Cache Storage et un
 * `fetch` de façade — pour exercer la seule chose qu'on ne peut pas voir en
 * ouvrant l'application : ce qu'elle sert quand le réseau n'est plus là. */

const ORIGINE = 'https://tontine.example'

class FauxCache {
  readonly entrees = new Map<string, Response>()

  private static cle(requete: string | { url: string }): string {
    return typeof requete === 'string' ? requete : requete.url
  }

  match(requete: string | { url: string }): Promise<Response | undefined> {
    return Promise.resolve(this.entrees.get(FauxCache.cle(requete)))
  }

  put(requete: string | { url: string }, reponse: Response): Promise<void> {
    this.entrees.set(FauxCache.cle(requete), reponse)
    return Promise.resolve()
  }

  addAll(urls: string[]): Promise<void> {
    for (const url of urls) this.entrees.set(url, new Response(url))
    return Promise.resolve()
  }
}

type Handler = (event: Record<string, unknown>) => void

let caches_: Map<string, FauxCache>
let handlers: Map<string, Handler>
let fetchMock: ReturnType<typeof vi.fn>

/** Charge le worker dans un environnement neuf et renvoie ses écouteurs. */
async function chargerLeWorker() {
  caches_ = new Map()
  handlers = new Map()
  fetchMock = vi.fn()

  const faussesCaches = {
    open: (nom: string) => {
      const cache = caches_.get(nom) ?? new FauxCache()
      caches_.set(nom, cache)
      return Promise.resolve(cache)
    },
    keys: () => Promise.resolve([...caches_.keys()]),
    delete: (nom: string) => Promise.resolve(caches_.delete(nom)),
  }

  vi.stubGlobal('caches', faussesCaches)
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('self', {
    addEventListener: (type: string, handler: Handler) => handlers.set(type, handler),
    location: new URL(ORIGINE),
    clients: { claim: () => Promise.resolve() },
    skipWaiting: () => Promise.resolve(),
  })

  vi.resetModules()
  await import('../../public/sw.js')
}

/** Déclenche `fetch` sur le worker et renvoie la réponse qu'il a choisi de
 *  servir, ou `null` s'il a laissé passer la requête au navigateur. */
async function interroger(request: {
  url: string
  method?: string
  mode?: string
}): Promise<Response | null> {
  let servie: Promise<Response> | null = null
  handlers.get('fetch')?.({
    request: { method: 'GET', mode: 'no-cors', ...request },
    respondWith: (promesse: Promise<Response>) => {
      servie = promesse
    },
  })
  return servie === null ? null : await servie
}

const navigation = { url: `${ORIGINE}/groupes/abc`, mode: 'navigate' }

describe('service worker', () => {
  beforeEach(async () => {
    await chargerLeWorker()
    // L'installation précache la coque, comme au premier chargement.
    const attentes: Promise<unknown>[] = []
    handlers.get('install')?.({ waitUntil: (p: Promise<unknown>) => attentes.push(p) })
    await Promise.all(attentes)
  })

  it('sert une navigation par le réseau tant qu\'il répond', async () => {
    fetchMock.mockResolvedValue(new Response('page fraîche'))
    const reponse = await interroger(navigation)

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(await reponse?.text()).toBe('page fraîche')
  })

  it('rend la coque en cache quand le réseau ne répond plus', async () => {
    // Un chargement réussi d'abord : c'est lui qui garnit la coque.
    fetchMock.mockResolvedValueOnce(new Response('page fraîche'))
    await interroger(navigation)

    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const reponse = await interroger(navigation)

    expect(await reponse?.text()).toBe('page fraîche')
  })

  it('sert la coque précachée même sans chargement réussi préalable', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const reponse = await interroger(navigation)

    // Le contenu vient du précache d'installation, qui a garni « / ».
    expect(await reponse?.text()).toBe('/')
  })

  it('laisse passer les appels à l\'API, en ligne comme hors ligne', async () => {
    // Ce sont des réponses authentifiées : le Cache Storage n'est pas vidé à
    // la déconnexion, elles n'ont rien à y faire.
    expect(await interroger({ url: `${ORIGINE}/api/v1/groups` })).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('laisse passer ce qui vient d\'une autre origine', async () => {
    expect(await interroger({ url: 'https://fonts.googleapis.com/css2' })).toBeNull()
  })

  it('ne se mêle pas des envois', async () => {
    // Un POST de paiement doit atteindre le serveur ou échouer franchement ;
    // la file s'occupe du reste.
    const servie = await interroger({ url: `${ORIGINE}/api/v1/x`, method: 'POST' })
    expect(servie).toBeNull()
  })

  it('ne redemande pas au réseau un fichier versionné déjà vu', async () => {
    const asset = { url: `${ORIGINE}/assets/index-D02cZdrx.js` }
    fetchMock.mockResolvedValue(new Response('le bundle'))

    expect(await (await interroger(asset))?.text()).toBe('le bundle')
    fetchMock.mockClear()

    // Deuxième demande : le cache répond, le réseau n'est pas sollicité.
    expect(await (await interroger(asset))?.text()).toBe('le bundle')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('ne met pas une erreur en cache', async () => {
    const asset = { url: `${ORIGINE}/assets/absent.js` }
    fetchMock.mockResolvedValue(new Response('introuvable', { status: 404 }))
    await interroger(asset)

    // Sans quoi un 404 passager resterait servi jusqu'au prochain déploiement.
    fetchMock.mockResolvedValue(new Response('enfin là'))
    expect(await (await interroger(asset))?.text()).toBe('enfin là')
  })

  it('efface les caches des versions précédentes à l\'activation', async () => {
    caches_.set('tontine-coque-v0', new FauxCache())
    caches_.set('tontine-statiques-v0', new FauxCache())

    const attentes: Promise<unknown>[] = []
    handlers.get('activate')?.({ waitUntil: (p: Promise<unknown>) => attentes.push(p) })
    await Promise.all(attentes)

    expect([...caches_.keys()]).not.toContain('tontine-coque-v0')
    expect([...caches_.keys()]).toContain('tontine-coque-v1')
  })
})
