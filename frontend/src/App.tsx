import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { Layout } from '@/components/Layout'
import { useAuth } from '@/hooks/useAuth'
import { GroupDetailPage } from '@/pages/GroupDetailPage'
import { GroupsPage } from '@/pages/GroupsPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { MembersPage } from '@/pages/MembersPage'
import { PaymentPage } from '@/pages/PaymentPage'
import { LoginPage } from '@/pages/LoginPage'
import { ProfilePage } from '@/pages/ProfilePage'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()

  if (isLoading) return <p className="muted">Chargement…</p>
  if (!user) return <Navigate to="/connexion" replace />
  return <>{children}</>
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/connexion" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <GroupsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/groupes/:groupId/ordre"
          element={
            <RequireAuth>
              <MembersPage />
            </RequireAuth>
          }
        />
        <Route
          path="/groupes/:groupId/cotisations/:contributionId"
          element={
            <RequireAuth>
              <PaymentPage />
            </RequireAuth>
          }
        />
        <Route
          path="/historique"
          element={
            <RequireAuth>
              <HistoryPage />
            </RequireAuth>
          }
        />
        <Route
          path="/profil"
          element={
            <RequireAuth>
              <ProfilePage />
            </RequireAuth>
          }
        />
        <Route
          path="/groupes/:groupId"
          element={
            <RequireAuth>
              <GroupDetailPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
