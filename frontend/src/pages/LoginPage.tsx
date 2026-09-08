import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { IconRotation } from '@/components/Icon'
import { useAuth } from '@/hooks/useAuth'

export function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [phone, setPhone] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      if (mode === 'login') {
        await login(phone, password)
      } else {
        await register(phone, fullName, password)
      }
      navigate('/')
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'Connexion au serveur impossible.',
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <header className="block wipe">
        <IconRotation size={30} />
        <h1 style={{ whiteSpace: 'pre-line' }}>
          {mode === 'login' ? 'Votre tontine,\nsur votre téléphone' : 'Créer un compte'}
        </h1>
        <p className="block__muted" style={{ fontSize: 13.5 }}>
          {mode === 'login'
            ? 'Cotisez et recevez par Mobile Money. Chaque tour est tracé.'
            : 'Votre numéro sert d’identifiant — c’est aussi celui qui sera débité.'}
        </p>
      </header>

      <main className="app__main">
        <form onSubmit={handleSubmit} className="form rise">
          <label className="field">
            <span>Numéro de téléphone</span>
            <input
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="+229 01 69 19 50"
              required
            />
          </label>

          {mode === 'register' && (
            <label className="field">
              <span>Nom complet</span>
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                autoComplete="name"
                required
                minLength={2}
              />
            </label>
          )}

          <label className="field">
            <span>Mot de passe</span>
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />
          </label>

          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn--primary" disabled={pending}>
            {pending ? 'Patientez…' : mode === 'login' ? 'Se connecter' : "S'inscrire"}
          </button>
        </form>

        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? 'Pas encore de compte ?' : "J'ai déjà un compte"}
        </button>
      </main>
    </>
  )
}
