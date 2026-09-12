import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from '@/App'
import { ApiError } from '@/api/client'
import { AuthProvider } from '@/hooks/useAuth'
import { hydrateFromStorage, persistQueryCache } from '@/offline/persist'
import { registerSW } from '@/offline/registerSW'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Inutile de réessayer une requête refusée : le résultat sera le même.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 2,
      // Le cache hydraté doit rester affichable hors connexion : sans cela une
      // requête qui échoue au démarrage remplacerait les données par une
      // erreur, et l'écran serait vide au moment où il sert le plus.
      gcTime: 7 * 24 * 60 * 60 * 1000,
    },
  },
})

// Le cache de la dernière visite est rendu avant le premier rendu : sans
// réseau, l'application s'ouvre sur des données plutôt que sur un sablier.
hydrateFromStorage(queryClient)
persistQueryCache(queryClient)
registerSW()

const container = document.getElementById('root')
if (!container) throw new Error('Élément #root introuvable.')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
