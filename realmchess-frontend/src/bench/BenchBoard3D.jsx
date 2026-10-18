// 3D view of the test bench: the 5 layers stacked, with an orbiting camera.
// Drag to rotate, right-drag (or two-finger drag) to pan, scroll to zoom.
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { GLYPHS, LAYERS, keyOf, layerLabel, parsePiece, sameCoord } from './shared'

const GAP = 2.6 // vertical distance between layers
const ACTIVE_OPACITY = 0.85
const INACTIVE_OPACITY = 0.14
const OFF_PLANE_PIECE_OPACITY = 0.5

// Click priority: a legal-move target beats anything on the current plane, which beats the rest
const TARGET = 2
const ON_PLANE = 1
const OTHER = 0

// Backend (x, y, z) → three.js world position. Layers stack upward, white sits nearest the camera.
const toWorld = ([x, y, z], lift = 0) => [x - 3.5, z * GAP + lift, 3.5 - y]

// ---------- textures (drawn once on a canvas, no asset files) ----------

const textureCache = {}

function canvasTexture(key, width, height, draw) {
  if (!textureCache[key]) {
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    draw(canvas.getContext('2d'))
    const texture = new THREE.CanvasTexture(canvas)
    texture.colorSpace = THREE.SRGBColorSpace
    textureCache[key] = texture
  }
  return textureCache[key]
}

function checkerTexture() {
  const texture = canvasTexture('checker', 8, 8, (ctx) => {
    for (let px = 0; px < 8; px++) {
      for (let py = 0; py < 8; py++) {
        // canvas row 0 is the far edge of the board (y = 7)
        ctx.fillStyle = (px + (7 - py)) % 2 === 0 ? '#8f9aae' : '#d9dde6'
        ctx.fillRect(px, py, 1, 1)
      }
    }
  })
  texture.magFilter = THREE.NearestFilter
  return texture
}

function glyphTexture(type, color) {
  return canvasTexture(`${type}-${color}`, 128, 128, (ctx) => {
    ctx.font = '104px "Apple Symbols", "Segoe UI Symbol", "Noto Sans Symbols 2", "DejaVu Sans", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.lineJoin = 'round'
    ctx.lineWidth = 9
    ctx.strokeStyle = color === 'white' ? '#11141b' : '#f2f4f8'
    ctx.strokeText(GLYPHS[type], 64, 70)
    ctx.fillStyle = color === 'white' ? '#ffffff' : '#11141b'
    ctx.fillText(GLYPHS[type], 64, 70)
  })
}

function labelTexture(text) {
  return canvasTexture(`label-${text}`, 512, 96, (ctx) => {
    ctx.font = '600 56px system-ui, -apple-system, sans-serif'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#ffffff'
    ctx.fillText(text, 500, 50)
  })
}

const boardEdges = new THREE.EdgesGeometry(new THREE.PlaneGeometry(8, 8))
const FLAT = [-Math.PI / 2, 0, 0]

// ---------- scene pieces ----------

function Layer({ z, name, active, onClick }) {
  return (
    <group position={[0, z * GAP, 0]}>
      {/* Only the current plane's squares are clickable, so other planes never block a click */}
      <mesh rotation={FLAT} onClick={active ? onClick : undefined} userData={{ rank: ON_PLANE }}>
        <planeGeometry args={[8, 8]} />
        <meshBasicMaterial
          map={checkerTexture()}
          transparent
          opacity={active ? ACTIVE_OPACITY : INACTIVE_OPACITY}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
      <lineSegments geometry={boardEdges} rotation={FLAT}>
        <lineBasicMaterial color={active ? '#f2c200' : '#7b8496'} />
      </lineSegments>
      <sprite position={[-5.7, 0, 4]} scale={[3.2, 0.6, 1]}>
        <spriteMaterial
          map={labelTexture(`${layerLabel(z)}  ${name}`)}
          color={active ? '#f2c200' : '#98a2b3'}
          transparent
          depthWrite={false}
        />
      </sprite>
    </group>
  )
}

function Piece({ coord, piece, rank, onPlane, onClick }) {
  const opacity = onPlane ? 1 : OFF_PLANE_PIECE_OPACITY
  return (
    <group position={toWorld(coord)}>
      <mesh position={[0, 0.05, 0]}>
        <cylinderGeometry args={[0.34, 0.34, 0.1, 24]} />
        <meshBasicMaterial color={piece.color === 'white' ? '#f2f4f8' : '#2a2f3a'} transparent opacity={opacity} />
      </mesh>
      <sprite position={[0, 0.58, 0]} scale={[0.95, 0.95, 1]} onClick={onClick} userData={{ rank }}>
        <spriteMaterial map={glyphTexture(piece.type, piece.color)} alphaTest={0.2} transparent opacity={opacity} />
      </sprite>
    </group>
  )
}

function Rock({ coord }) {
  return (
    <mesh position={toWorld(coord, 0.3)}>
      <dodecahedronGeometry args={[0.38]} />
      <meshStandardMaterial color="#6b5a4a" flatShading />
    </mesh>
  )
}

// Markers ignore depth so they stay visible through every board and piece
function Ring({ coord, color }) {
  return (
    <mesh position={toWorld(coord, 0.04)} rotation={FLAT} renderOrder={10}>
      <torusGeometry args={[0.43, 0.055, 8, 40]} />
      <meshBasicMaterial color={color} depthTest={false} transparent />
    </mesh>
  )
}

function MoveDot({ coord, onClick }) {
  return (
    <mesh position={toWorld(coord, 0.25)} renderOrder={10} onClick={onClick} userData={{ rank: TARGET }}>
      <sphereGeometry args={[0.2, 20, 20]} />
      <meshBasicMaterial color="#19c264" depthTest={false} transparent opacity={0.95} />
    </mesh>
  )
}

// ---------- the board ----------

function Board3D({ board, selected, legalMoves, activeLayer, onSquareClick }) {
  const isLegal = (coord) => legalMoves.some((move) => sameCoord(move, coord))

  const rankOf = (coord) => (isLegal(coord) ? TARGET : coord[2] === activeLayer ? ON_PLANE : OTHER)

  // The highest-ranked thing under the cursor gets the click, even when something else is in front of it
  const clickOn = (coord, rank) => (e) => {
    if (e.delta > 4) return // that was a camera drag, not a click
    if (e.intersections.some((hit) => (hit.object.userData.rank ?? OTHER) > rank)) return
    e.stopPropagation()
    onSquareClick(coord)
  }

  const clickOnLayer = (z) => (e) => {
    const x = Math.min(7, Math.max(0, Math.floor(e.point.x + 4)))
    const y = Math.min(7, Math.max(0, Math.floor(4 - e.point.z)))
    clickOn([x, y, z], ON_PLANE)(e)
  }

  const occupied = Object.entries(board).map(([key, value]) => ({
    key,
    coord: JSON.parse(key),
    piece: parsePiece(value),
  }))

  return (
    <div className="scene">
      <Canvas camera={{ position: [13, 9, 18], fov: 40 }}>
        <ambientLight intensity={1.6} />
        <directionalLight position={[6, 12, 8]} intensity={2} />
        <OrbitControls makeDefault enableDamping maxDistance={60} minDistance={4} />

        {LAYERS.map(({ z, name }) => (
          <Layer key={z} z={z} name={name} active={z === activeLayer} onClick={clickOnLayer(z)} />
        ))}

        {occupied.map(({ key, coord, piece }) =>
          piece.type === 'Rock' ? (
            <Rock key={key} coord={coord} />
          ) : (
            <Piece
              key={key}
              coord={coord}
              piece={piece}
              rank={rankOf(coord)}
              onPlane={coord[2] === activeLayer}
              onClick={clickOn(coord, rankOf(coord))}
            />
          ),
        )}

        {selected && <Ring coord={selected} color="#f2c200" />}
        {legalMoves.map((move) =>
          board[keyOf(move)] ? (
            <Ring key={keyOf(move)} coord={move} color="#ff3b3b" />
          ) : (
            <MoveDot key={keyOf(move)} coord={move} onClick={clickOn(move, TARGET)} />
          ),
        )}
      </Canvas>
    </div>
  )
}

export default Board3D
