import { NavLink, Outlet } from 'react-router-dom'

import { IconHistory, IconPerson, IconRotation } from '@/components/Icon'
import { OfflineBar } from '@/components/OfflineBar'
import { useAuth } from '@/hooks/useAuth'
import { useQueueFlush } from '@/offline/useOffline'

export function Layout() {
  const { user } = useAuth()
  // Monté une seule fois pour toute l'application : c'est ici que la file se
  // vide quand le réseau revient.
  useQueueFlush()

  return (
    <div className={`app${user ? ' app--with-nav' : ''}`}>
      <OfflineBar />
      <Outlet />
      {user && (
        <nav className="nav" aria-label="Navigation principale">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav__item${isActive ? ' nav__item--active' : ''}`}
          >
            <IconRotation />
            <span>TONTINES</span>
          </NavLink>
          <NavLink
            to="/historique"
            className={({ isActive }) => `nav__item${isActive ? ' nav__item--active' : ''}`}
          >
            <IconHistory />
            <span>HISTORIQUE</span>
          </NavLink>
          <NavLink
            to="/profil"
            className={({ isActive }) => `nav__item${isActive ? ' nav__item--active' : ''}`}
          >
            <IconPerson />
            <span>PROFIL</span>
          </NavLink>
        </nav>
      )}
    </div>
  )
}
