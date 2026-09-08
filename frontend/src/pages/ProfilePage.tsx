import { IconMoon, IconSun } from '@/components/Icon'
import { useAuth } from '@/hooks/useAuth'
import { useTheme } from '@/hooks/useTheme'
import type { ThemePreference } from '@/hooks/useTheme'

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'light', label: 'Clair' },
  { value: 'dark', label: 'Sombre' },
  { value: 'system', label: 'Téléphone' },
]

export function ProfilePage() {
  const { user, logout } = useAuth()
  const { preference, choose } = useTheme()

  return (
    <>
      <header className="block wipe">
        <div className="label--accent">Mon compte</div>
        <h1>{user?.full_name}</h1>
        <div className="block__muted" style={{ fontSize: 13.5 }}>
          {user?.phone}
        </div>
      </header>

      <main className="app__main">
        <section className="stack rise">
          <div className="label">Apparence</div>
          <div className="card card--soft" style={{ gap: 11 }}>
            <div className="row" style={{ gap: 8 }}>
              {preference === 'dark' ? <IconMoon size={18} /> : <IconSun size={18} />}
              <span className="muted">
                Le thème clair est le défaut. « Téléphone » suit le réglage de l'appareil.
              </span>
            </div>
            <div className="stats">
              {OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="btn"
                  aria-pressed={preference === option.value}
                  onClick={() => choose(option.value)}
                  style={
                    preference === option.value
                      ? {
                          background: 'var(--accent)',
                          borderColor: 'var(--accent)',
                          color: 'var(--on-accent)',
                        }
                      : undefined
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="stack rise" style={{ animationDelay: '.08s' }}>
          <div className="label">Session</div>
          <button
            type="button"
            className="btn"
            style={{ width: '100%', color: 'var(--urgent)' }}
            onClick={logout}
          >
            Se déconnecter
          </button>
        </section>
      </main>
    </>
  )
}
