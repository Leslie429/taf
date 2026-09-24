#!/usr/bin/env node
// Vérifie que la démonstration en ligne s'affiche réellement, et pas seulement
// qu'elle répond.
//
// Le 2026-09-24, la production renvoyait HTTP 200 sur une page blanche : React
// entrait dans une boucle de rendu (erreur n° 185) et démontait l'application.
// Un contrôle HTTP ne pouvait pas le voir. Celui-ci ouvre la page dans un vrai
// Chrome, se connecte avec le compte de démonstration (identifiants publics,
// voir le README) et exige que l'écran d'accueil de la tontine apparaisse, sans
// aucune exception JavaScript ni erreur console.
//
//   node scripts/verifier-production.mjs [URL]
//
// Sans dépendance : Node 22 fournit WebSocket, Chrome le protocole DevTools.
// Chrome est cherché dans $CHROME, puis sous ses noms usuels.

import { spawn, spawnSync } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const URL_DEMO = process.argv[2] ?? 'https://tontine-web-7208.onrender.com'
const TELEPHONE = '+22901691004'
const MOT_DE_PASSE = 'demo1234'
const GROUPE = 'Tontine des marchandes de Dantokpa'
// L'API gratuite de Render dort après 15 min ; son réveil a été mesuré à 44 s.
const REVEIL_MAX_MS = 120_000
const PORT = 9333

const attendre = (ms) => new Promise((r) => setTimeout(r, ms))

function trouverChrome() {
  if (process.env.CHROME) return process.env.CHROME
  for (const nom of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    if (spawnSync('which', [nom]).status === 0) return nom
  }
  throw new Error('Chrome introuvable : définir $CHROME.')
}

async function ouvrirChrome() {
  const processus = spawn(
    trouverChrome(),
    [
      '--headless=new',
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${mkdtempSync(join(tmpdir(), 'verif-'))}`,
      '--no-first-run',
      '--window-size=412,915',
      'about:blank',
    ],
    { stdio: 'ignore' },
  )
  let cible
  for (let i = 0; i < 75 && !cible; i++) {
    await attendre(200)
    try {
      const cibles = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()
      cible = cibles.find((t) => t.type === 'page')
    } catch {
      // Chrome n'écoute pas encore.
    }
  }
  if (!cible) throw new Error("Chrome n'a pas démarré.")

  const ws = new WebSocket(cible.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r))
  let compteur = 0
  const enAttente = new Map()
  const erreurs = []
  ws.addEventListener('message', (evenement) => {
    const m = JSON.parse(evenement.data)
    if (m.id && enAttente.has(m.id)) {
      enAttente.get(m.id)(m)
      enAttente.delete(m.id)
    }
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails
      erreurs.push(`exception : ${d.exception?.description ?? d.text}`)
    }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      erreurs.push(`console : ${m.params.args.map((a) => a.value ?? a.description).join(' ')}`)
    }
  })
  const cdp = (method, params = {}) =>
    new Promise((r) => {
      const id = ++compteur
      enAttente.set(id, r)
      ws.send(JSON.stringify({ id, method, params }))
    })
  await cdp('Page.enable')
  await cdp('Runtime.enable')

  return {
    erreurs,
    cdp,
    async evaluer(expression) {
      const r = await cdp('Runtime.evaluate', { expression, returnByValue: true })
      return r.result?.result?.value
    },
    fermer() {
      ws.close()
      processus.kill()
    },
  }
}

// Attend qu'une condition évaluée dans la page devienne vraie.
async function attendreQue(page, expression, delaiMs) {
  const fin = Date.now() + delaiMs
  while (Date.now() < fin) {
    if (await page.evaluer(expression)) return true
    await attendre(500)
  }
  return false
}

const TEXTE_RACINE = "document.getElementById('root')?.innerText.trim() ?? ''"

async function saisir(page, selecteur, texte) {
  await page.evaluer(`document.querySelector(${JSON.stringify(selecteur)}).focus()`)
  await page.cdp('Input.insertText', { text: texte })
}

async function verifier() {
  const page = await ouvrirChrome()
  const echecs = []
  const etape = (ok, libelle) => {
    console.log(`${ok ? '✔' : '✘'} ${libelle}`)
    if (!ok) echecs.push(libelle)
    return ok
  }

  try {
    await page.cdp('Page.navigate', { url: `${URL_DEMO}/connexion` })
    const connexionRendue = await attendreQue(
      page,
      `${TEXTE_RACINE}.includes('Se connecter')`,
      30_000,
    )
    if (etape(connexionRendue, "l'écran de connexion s'affiche")) {
      await saisir(page, 'input[type=tel]', TELEPHONE)
      await saisir(page, 'input[type=password]', MOT_DE_PASSE)
      await page.evaluer("document.querySelector('form button[type=submit]').click()")
      etape(
        await attendreQue(page, `${TEXTE_RACINE}.includes(${JSON.stringify(GROUPE)})`, REVEIL_MAX_MS),
        'le compte de démonstration ouvre sa tontine',
      )
    }
    const texte = await page.evaluer(TEXTE_RACINE)
    etape(texte.length > 0, `la racine n'est pas vide (${texte.length} caractères)`)
    etape(page.erreurs.length === 0, `aucune erreur JavaScript (${page.erreurs.length})`)
    for (const erreur of page.erreurs) console.log(`  ${erreur.split('\n')[0]}`)
  } finally {
    page.fermer()
  }

  if (echecs.length > 0) {
    console.error(`\nÉchec du contrôle de ${URL_DEMO} : ${echecs.join(' ; ')}`)
    process.exit(1)
  }
  console.log(`\n${URL_DEMO} s'affiche et fonctionne.`)
}

await verifier()
