import { useCallback, useEffect, useState } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'tontine.theme'

function read(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // Navigation privée ou stockage bloqué : le défaut suffit.
  }
  return 'system'
}

function apply(preference: ThemePreference): void {
  const root = document.documentElement
  if (preference === 'system') {
    root.removeAttribute('data-theme')
  } else {
    root.setAttribute('data-theme', preference)
  }
}

/** Le clair est le défaut du produit ; « system » laisse le téléphone décider,
 *  et le réglage manuel l'emporte dans les deux sens. */
export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(read)

  useEffect(() => {
    apply(preference)
  }, [preference])

  const choose = useCallback((next: ThemePreference) => {
    setPreference(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Le réglage ne survivra pas au rechargement, l'écran reste correct.
    }
  }, [])

  return { preference, choose }
}
