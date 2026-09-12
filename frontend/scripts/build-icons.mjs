/* Génère les icônes PNG de la PWA à partir du glyphe de rotation de
 * l'application — le même que `IconRotation` : une tontine tourne.
 *
 * Écrit à la main plutôt que confié à une bibliothèque : il s'agit de trois
 * fichiers produits une fois, et une dépendance de rastérisation pèserait plus
 * lourd que ces quatre-vingts lignes. Le dessin reste ainsi versionné en
 * clair, régénérable par `npm run icons`.
 *
 * Usage : node scripts/build-icons.mjs
 */
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const VERT = [0x14, 0x52, 0x3a] //  --block
const CITRON = [0xc2, 0xee, 0x3e] // --accent

// Le glyphe reprend la rotation de `IconRotation`, redessinée pour la taille
// d'une icône : l'équerre de l'original traverse l'anneau et, une fois réduite
// à 48 pixels, l'ensemble se lit « G ». Ici l'anneau s'ouvre franchement et la
// pointe prolonge le trait, tangente — la rotation reste lisible de loin.
const CENTRE = { x: 12, y: 12 }
const RAYON = 8.5
const TRAIT = 2.3
// Angles à l'écran, croissants dans le sens horaire : l'arc part du bas droit,
// fait trois quarts de tour et s'arrête en haut à droite.
const ARC_DEBUT = 45
const ARC_FIN = 315

const radians = (degres) => (degres * Math.PI) / 180
const surLeCercle = (degres) => ({
  x: CENTRE.x + RAYON * Math.cos(radians(degres)),
  y: CENTRE.y + RAYON * Math.sin(radians(degres)),
})

// La pointe : deux barbes qui rejoignent un sommet posé dans le prolongement
// tangent de l'arc, à l'extrémité haute.
const FLECHE = (() => {
  const bout = surLeCercle(ARC_FIN)
  const tangente = { x: -Math.sin(radians(ARC_FIN)), y: Math.cos(radians(ARC_FIN)) }
  const sommet = { x: bout.x + 1.9 * tangente.x, y: bout.y + 1.9 * tangente.y }
  const barbe = (ecart) => {
    const a = Math.atan2(tangente.y, tangente.x) + radians(ecart)
    return { x: sommet.x - 3.1 * Math.cos(a), y: sommet.y - 3.1 * Math.sin(a) }
  }
  return [
    [barbe(44), sommet],
    [barbe(-44), sommet],
  ]
})()

const distanceAuSegment = (p, a, b) => {
  const vx = b.x - a.x
  const vy = b.y - a.y
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * vx + (p.y - a.y) * vy) / (vx * vx + vy * vy)))
  return Math.hypot(p.x - (a.x + t * vx), p.y - (a.y + t * vy))
}

/** Distance du point au squelette du glyphe, avant épaississement. */
function distanceAuGlyphe(p) {
  const dx = p.x - CENTRE.x
  const dy = p.y - CENTRE.y
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI
  const theta = angle < 0 ? angle + 360 : angle

  let d
  if (theta >= ARC_DEBUT && theta <= ARC_FIN) {
    d = Math.abs(Math.hypot(dx, dy) - RAYON)
  } else {
    // Hors de l'ouverture angulaire : c'est l'extrémité la plus proche qui
    // compte, ce qui donne au trait ses bouts arrondis.
    const bouts = [ARC_DEBUT, ARC_FIN].map(surLeCercle)
    d = Math.min(...bouts.map((b) => Math.hypot(p.x - b.x, p.y - b.y)))
  }
  for (const [a, b] of FLECHE) d = Math.min(d, distanceAuSegment(p, a, b))
  return d
}

/** Rend l'icône en RGB brut. `occupation` : part du côté prise par le glyphe. */
function dessiner(cote, occupation) {
  const echelle = (cote * occupation) / 24
  const origine = (cote - 24 * echelle) / 2
  const SS = 4 // sur-échantillonnage : 16 sondes par pixel, l'anticrénelage
  const pixels = Buffer.alloc(cote * cote * 3)

  for (let y = 0; y < cote; y++) {
    for (let x = 0; x < cote; x++) {
      let dedans = 0
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const p = {
            x: (x + (sx + 0.5) / SS - origine) / echelle,
            y: (y + (sy + 0.5) / SS - origine) / echelle,
          }
          if (distanceAuGlyphe(p) <= TRAIT / 2) dedans++
        }
      }
      const a = dedans / (SS * SS)
      const i = (y * cote + x) * 3
      for (let c = 0; c < 3; c++) pixels[i + c] = Math.round(VERT[c] * (1 - a) + CITRON[c] * a)
    }
  }
  return pixels
}

const TABLE_CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})

function crc32(buf) {
  let c = 0xffffffff
  for (const octet of buf) c = TABLE_CRC[(c ^ octet) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const entete = Buffer.alloc(8)
  entete.writeUInt32BE(data.length, 0)
  entete.write(type, 4, 'ascii')
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(Buffer.concat([entete.subarray(4), data])), 0)
  return Buffer.concat([entete, data, crc])
}

function png(cote, pixels) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(cote, 0)
  ihdr.writeUInt32BE(cote, 4)
  ihdr[8] = 8 // 8 bits par canal
  ihdr[9] = 2 // couleur vraie, sans canal alpha
  // Chaque ligne est précédée de son octet de filtre — 0, aucun filtre.
  const brut = Buffer.alloc(cote * (cote * 3 + 1))
  for (let y = 0; y < cote; y++) {
    pixels.copy(brut, y * (cote * 3 + 1) + 1, y * cote * 3, (y + 1) * cote * 3)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(brut, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const racine = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')

// L'icône masquable est plus timide : Android recadre jusqu'à 20 % du bord,
// et un glyphe cadré au plus juste s'y ferait rogner.
for (const [nom, cote, occupation] of [
  ['icon-192.png', 192, 0.66],
  ['icon-512.png', 512, 0.66],
  ['icon-maskable-512.png', 512, 0.52],
]) {
  const fichier = join(racine, nom)
  writeFileSync(fichier, png(cote, dessiner(cote, occupation)))
  console.log(`${nom} — ${cote}×${cote}`)
}
