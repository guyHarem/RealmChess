// Dev tool: renders the 3D pieces, the move ball and the rock into one transparent sprite sheet,
// seen from the same angle the design artboards draw the board from (30° up, 45° around).
import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { createMoveBall, createPiece, createRock } from '../src/pieces3d.js'

const CELL_W = 192 // one sprite, 4x the 48 x 66 size it is shown at
const CELL_H = 264
const SUPERSAMPLE = 2
const VIEW_W = 0.848 // world units across one sprite
const VIEW_H = (VIEW_W * CELL_H) / CELL_W
const TYPES = ['Pawn', 'Rook', 'Knight', 'Bishop', 'Queen', 'King']

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
renderer.setPixelRatio(1)
renderer.setSize(CELL_W * SUPERSAMPLE, CELL_H * SUPERSAMPLE)
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 0.92
renderer.setClearColor(0x000000, 0)

const scene = new THREE.Scene()
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture
scene.environmentIntensity = 0.45

const key = new THREE.DirectionalLight(0xffffff, 2.2)
key.position.set(-0.5, 4, 3.5)
scene.add(key)
const rim = new THREE.DirectionalLight(0xcfe0ff, 1.4)
rim.position.set(3, 2.5, -3)
scene.add(rim)

const camera = new THREE.OrthographicCamera(-VIEW_W / 2, VIEW_W / 2, VIEW_H / 2, -VIEW_H / 2, 0.1, 50)
const elevation = Math.PI / 6
const target = new THREE.Vector3(0, 0.454, 0)
camera.position
  .set(Math.cos(elevation) * Math.SQRT1_2, Math.sin(elevation), Math.cos(elevation) * Math.SQRT1_2)
  .multiplyScalar(10)
  .add(target)
camera.lookAt(target)

// Soft contact shadow so the models sit on the floor
function shadow(radius, opacity) {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')
  const gradient = ctx.createRadialGradient(64, 64, 8, 64, 64, 64)
  gradient.addColorStop(0, `rgba(0,0,0,${opacity})`)
  gradient.addColorStop(0.6, `rgba(0,0,0,${opacity * 0.55})`)
  gradient.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 128, 128)
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(radius * 2, radius * 2),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.position.set(0.05, 0.002, 0.03)
  return mesh
}

const atlas = document.createElement('canvas')
atlas.width = CELL_W * 7
atlas.height = CELL_H * 2
const ctx = atlas.getContext('2d')
ctx.imageSmoothingQuality = 'high'

function draw(object, shadowRadius, shadowOpacity, col, row) {
  const group = new THREE.Group()
  group.add(object, shadow(shadowRadius, shadowOpacity))
  scene.add(group)
  renderer.render(scene, camera)
  ctx.drawImage(renderer.domElement, col * CELL_W, row * CELL_H, CELL_W, CELL_H)
  scene.remove(group)
}

TYPES.forEach((type, col) => {
  for (const [row, color] of [[0, 'white'], [1, 'black']]) {
    const piece = createPiece(type, color)
    // Sprites only: turn the knights side-on to the camera so the head reads at a glance
    if (type === 'Knight') piece.rotation.y = -Math.PI / 4
    draw(piece, 0.4, 0.5, col, row)
  }
})
draw(createMoveBall(), 0.3, 0.25, 6, 0)
draw(createRock(), 0.42, 0.5, 6, 1)

document.body.appendChild(atlas)
atlas.style.width = `${atlas.width / 2}px`
const status = document.getElementById('status')
status.textContent = 'rendered'
window.__atlas = atlas

// Optional: ?save=http://localhost:5055 posts the PNG to a local file saver
const saveTo = new URLSearchParams(location.search).get('save')
if (saveTo) {
  fetch(`${saveTo}/save?name=pieces-atlas.png`, { method: 'POST', mode: 'no-cors', body: atlas.toDataURL('image/png') })
    .then(() => (status.textContent = 'rendered and saved'))
    .catch((error) => (status.textContent = `rendered, save failed: ${error}`))
}
