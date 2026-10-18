// The 3D board: a block of cube-shaped cells, one coloured slab per layer.
// Drag to orbit, right-drag to pan, scroll to zoom.
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { boardItems, isDarkSquare, keyOf, layerOf, sameCoord } from '../lib/chess.js'
import { createMoveBall, createPiece, createRock } from '../pieces3d.js'

const FLAT = [-Math.PI / 2, 0, 0]
const SPREAD_GAP = 1.15 // extra space between layers when they are spread apart

// Click priority: a legal-move target beats anything on the current layer, which beats the rest
const TARGET = 2
const ON_LAYER = 1
const OTHER = 0

function rankOf(object) {
  for (let node = object; node; node = node.parent) {
    if (node.userData.rank !== undefined) return node.userData.rank
  }
  return OTHER
}

// ---------- geometry and textures, built once per board size ----------

const cache = new Map()
function cached(key, build) {
  if (!cache.has(key)) cache.set(key, build())
  return cache.get(key)
}

function checkerTexture(layer, size) {
  return cached(`checker-${layer.z}-${size}`, () => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const ctx = canvas.getContext('2d')
    for (let px = 0; px < size; px++) {
      for (let py = 0; py < size; py++) {
        // canvas row 0 is the far edge of the board (the highest rank)
        ctx.fillStyle = isDarkSquare(px, size - 1 - py, layer.z) ? layer.dark : layer.light
        ctx.fillRect(px, py, 1, 1)
      }
    }
    const texture = new THREE.CanvasTexture(canvas)
    texture.colorSpace = THREE.SRGBColorSpace
    texture.magFilter = THREE.NearestFilter
    return texture
  })
}

// Cell edges on the four outer faces of one layer slab (a size x 1 x size box)
function slabGrid(size) {
  return cached(`slab-${size}`, () => {
    const h = size / 2
    const points = []
    const corners = [[-h, -h], [h, -h], [h, h], [-h, h]]
    corners.forEach(([x1, z1], i) => {
      const [x2, z2] = corners[(i + 1) % 4]
      points.push(x1, 0, z1, x2, 0, z2, x1, 1, z1, x2, 1, z2)
      for (let step = 0; step < size; step++) {
        const t = step / size
        const x = x1 + (x2 - x1) * t
        const z = z1 + (z2 - z1) * t
        points.push(x, 0, z, x, 1, z)
      }
    })
    return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
  })
}

// Cell edges across the lid of the block
function lidGrid(size) {
  return cached(`lid-${size}`, () => {
    const h = size / 2
    const points = []
    for (let i = 0; i <= size; i++) {
      points.push(-h + i, 0, -h, -h + i, 0, h, -h, 0, -h + i, h, 0, -h + i)
    }
    return new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
  })
}

// ---------- scene parts ----------

function Studio() {
  const { gl, scene, invalidate } = useThree()
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl)
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    // The scene is three.js state, not React state: setting its environment here is the intended API
    // oxlint-disable-next-line react/immutability
    Object.assign(scene, { environment, environmentIntensity: 0.5 })
    invalidate()
    return () => {
      Object.assign(scene, { environment: null })
      environment.dispose()
      pmrem.dispose()
    }
  }, [gl, scene, invalidate])
  return (
    <>
      <ambientLight intensity={0.55} />
      <directionalLight position={[-3, 12, 8]} intensity={2.1} />
      <directionalLight position={[8, 6, -8]} intensity={0.9} color="#cfe0ff" />
    </>
  )
}

function Slab({ layer, y, size, active, isTop, onFloorClick }) {
  const h = size / 2
  const wallOpacity = active ? 0.24 : 0.1
  const walls = [
    { position: [0, 0.5, h], rotation: [0, 0, 0], color: layer.dark },
    { position: [0, 0.5, -h], rotation: [0, Math.PI, 0], color: layer.dark },
    { position: [h, 0.5, 0], rotation: [0, Math.PI / 2, 0], color: layer.side },
    { position: [-h, 0.5, 0], rotation: [0, -Math.PI / 2, 0], color: layer.side },
  ]
  return (
    <group position={[0, y, 0]}>
      {/* Only the current layer's floor takes clicks, so other layers never block one */}
      <mesh rotation={FLAT} onClick={active ? onFloorClick : undefined} userData={{ rank: ON_LAYER }}>
        <planeGeometry args={[size, size]} />
        <meshBasicMaterial
          map={checkerTexture(layer, size)}
          transparent
          opacity={active ? 0.94 : 0.3}
          side={THREE.DoubleSide}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      {walls.map((wall, i) => (
        <mesh key={i} position={wall.position} rotation={wall.rotation}>
          <planeGeometry args={[size, 1]} />
          <meshBasicMaterial
            color={wall.color}
            transparent
            opacity={wallOpacity}
            side={THREE.DoubleSide}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      ))}
      <lineSegments geometry={slabGrid(size)}>
        <lineBasicMaterial color={active ? '#ffffff' : layer.light} transparent opacity={active ? 0.75 : 0.3} />
      </lineSegments>
      {isTop && (
        <lineSegments geometry={lidGrid(size)} position={[0, 1, 0]}>
          <lineBasicMaterial color="#ffffff" transparent opacity={0.22} />
        </lineSegments>
      )}
    </group>
  )
}

function Model({ build, position, rank, onClick }) {
  const object = useMemo(() => build(), [build])
  return <primitive object={object} position={position} userData-rank={rank} onClick={onClick} />
}

function Ring({ position, color }) {
  return (
    <mesh position={[position[0], position[1] + 0.03, position[2]]} rotation={FLAT}>
      <torusGeometry args={[0.4, 0.035, 10, 48]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  )
}

// The cell a lesson asks you to reach: a glowing amber pad on its floor
function GoalPad({ position }) {
  return (
    <group position={[position[0], position[1] + 0.02, position[2]]} rotation={FLAT}>
      <mesh>
        <circleGeometry args={[0.42, 48]} />
        <meshBasicMaterial color="#F5B83D" transparent opacity={0.4} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh>
        <torusGeometry args={[0.44, 0.045, 10, 48]} />
        <meshBasicMaterial color="#F5B83D" toneMapped={false} />
      </mesh>
    </group>
  )
}

// The square a piece just left or arrived on: a pale tile on the cell's floor
function MovePad({ position, arrived }) {
  return (
    <mesh position={[position[0], position[1] + 0.015, position[2]]} rotation={FLAT}>
      <planeGeometry args={[0.94, 0.94]} />
      <meshBasicMaterial color="#FFFFFF" transparent opacity={arrived ? 0.62 : 0.34} depthWrite={false} toneMapped={false} />
    </mesh>
  )
}

const BUILDERS = {}
function pieceBuilder(type, color) {
  const key = `${type}-${color}`
  BUILDERS[key] ??= () => createPiece(type, color)
  return BUILDERS[key]
}

// Moves the camera for the view buttons. Manual orbiting is left to OrbitControls.
function CameraRig({ home, command, interactive }) {
  const { camera, invalidate } = useThree()
  const controls = useRef(null)
  const goal = useRef(null)
  const target = useRef(new THREE.Vector3())

  useLayoutEffect(() => {
    camera.position.setFromSpherical(new THREE.Spherical(home.radius, home.polar, home.azimuth))
    camera.lookAt(0, 0, 0)
    // Only the first placement is instant; later changes of `home` glide there (see below)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera])

  useEffect(() => {
    goal.current = { ...home, recentre: true }
    invalidate()
  }, [home, invalidate])

  useEffect(() => {
    if (!command) return
    if (command.type === 'reset') {
      goal.current = { ...home, recentre: true }
    } else if (command.type === 'turn') {
      const now = new THREE.Spherical().setFromVector3(camera.position.clone().sub(target.current))
      goal.current = { azimuth: now.theta + command.direction * (Math.PI / 2), polar: now.phi, radius: now.radius }
    }
    invalidate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command])

  useFrame((_, delta) => {
    if (!goal.current) return
    const centre = controls.current ? controls.current.target : target.current
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const k = reduced ? 1 : 1 - Math.exp(-delta * 9)
    const now = new THREE.Spherical().setFromVector3(camera.position.clone().sub(centre))
    let turn = goal.current.azimuth - now.theta
    turn = Math.atan2(Math.sin(turn), Math.cos(turn)) // shortest way round
    now.theta += turn * k
    now.phi += (goal.current.polar - now.phi) * k
    now.radius += (goal.current.radius - now.radius) * k
    if (goal.current.recentre) centre.lerp(new THREE.Vector3(), k)
    const done = Math.abs(turn) < 0.002 && Math.abs(goal.current.radius - now.radius) < 0.01
    if (done || reduced) {
      now.theta = goal.current.azimuth
      now.phi = goal.current.polar
      now.radius = goal.current.radius
      if (goal.current.recentre) centre.set(0, 0, 0)
      goal.current = null
    }
    camera.position.setFromSpherical(now).add(centre)
    camera.lookAt(centre)
    controls.current?.update()
    invalidate()
  })

  if (!interactive) return null
  return (
    <OrbitControls ref={controls} makeDefault enableDamping minDistance={5} maxDistance={home.radius * 2.2} maxPolarAngle={Math.PI * 0.92} />
  )
}

// A still picture (frameloop "demand") is drawn only when something asks for it. Safari can
// draw it once before the page has its final size, or lose the drawing when it sets the
// page aside, and then shows an empty box. So it is drawn again whenever that may happen.
function KeepDrawn() {
  const { gl, invalidate, size } = useThree()

  useEffect(() => invalidate(), [invalidate, size.width, size.height])

  useEffect(() => {
    let alive = true
    const again = () => alive && invalidate()
    document.fonts?.ready.then(again)
    const timers = [100, 500, 1500].map((ms) => setTimeout(again, ms))
    const canvas = gl.domElement
    window.addEventListener('pageshow', again)
    document.addEventListener('visibilitychange', again)
    canvas.addEventListener('webglcontextrestored', again)
    return () => {
      alive = false
      timers.forEach(clearTimeout)
      window.removeEventListener('pageshow', again)
      document.removeEventListener('visibilitychange', again)
      canvas.removeEventListener('webglcontextrestored', again)
    }
  }, [gl, invalidate])

  return null
}

// ---------- the board ----------

function Scene({
  board,
  size,
  layers,
  activeLayer,
  selected,
  legalMoves,
  goal,
  lastMove,
  showMoveBalls,
  spread,
  solo,
  side,
  command,
  interactive,
  onCellClick,
}) {
  const half = (size - 1) / 2
  const levels = useMemo(() => [...layers].sort((a, b) => a - b), [layers])
  const step = 1 + (spread ? SPREAD_GAP : 0)
  const height = (levels.length - 1) * step + 1
  const floorY = (z) => levels.indexOf(z) * step - height / 2
  const cellPosition = ([x, y, z]) => [x - half, floorY(z), half - y]
  const visible = (z) => !solo || z === activeLayer
  const isLegal = (coord) => legalMoves.some((move) => sameCoord(move, coord))
  const rankFor = (coord) => (isLegal(coord) ? TARGET : coord[2] === activeLayer ? ON_LAYER : OTHER)

  const home = useMemo(
    () => ({
      azimuth: (side === 'black' ? Math.PI : 0) + 0.62,
      polar: 1.03,
      radius: size * 1.85 + (levels.length - 1) * step * 0.9 + 2,
    }),
    [side, size, levels.length, step],
  )

  // The highest-ranked thing under the cursor gets the click, even when something else is in front
  const clickOn = (coord, rank) => (event) => {
    if (!interactive || event.delta > 4) return // a camera drag, not a click
    if (event.intersections.some((hit) => rankOf(hit.object) > rank)) return
    event.stopPropagation()
    onCellClick?.(coord)
  }
  const clickOnFloor = (z) => (event) => {
    const x = Math.min(size - 1, Math.max(0, Math.floor(event.point.x + size / 2)))
    const y = Math.min(size - 1, Math.max(0, Math.floor(size / 2 - event.point.z)))
    clickOn([x, y, z], ON_LAYER)(event)
  }

  const items = boardItems(board).filter((item) => visible(item.coord[2]))
  const moves = legalMoves.filter((move) => visible(move[2]))

  return (
    <>
      <Studio />
      <CameraRig home={home} command={command} interactive={interactive} />

      {levels.filter(visible).map((z) => (
        <Slab
          key={z}
          layer={layerOf(z)}
          y={floorY(z)}
          size={size}
          active={z === activeLayer}
          isTop={z === levels[levels.length - 1] || spread || solo}
          onFloorClick={clickOnFloor(z)}
        />
      ))}

      {items.map((item) =>
        item.type === 'Rock' ? (
          <Model key={item.key} build={createRock} position={cellPosition(item.coord)} rank={OTHER} />
        ) : (
          <Model
            key={`${item.key}-${item.type}-${item.color}`}
            build={pieceBuilder(item.type, item.color)}
            position={cellPosition(item.coord)}
            rank={rankFor(item.coord)}
            onClick={clickOn(item.coord, rankFor(item.coord))}
          />
        ),
      )}

      {lastMove && visible(lastMove.from[2]) && <MovePad position={cellPosition(lastMove.from)} />}
      {lastMove && visible(lastMove.to[2]) && <MovePad position={cellPosition(lastMove.to)} arrived />}
      {goal && visible(goal[2]) && <GoalPad position={cellPosition(goal)} />}
      {selected && visible(selected[2]) && <Ring position={cellPosition(selected)} color="#F5B83D" />}
      {moves.map((move) =>
        board[keyOf(move)] ? (
          <Ring key={keyOf(move)} position={cellPosition(move)} color="#FF5A4F" />
        ) : (
          showMoveBalls && (
            <Model
              key={keyOf(move)}
              build={createMoveBall}
              position={cellPosition(move)}
              rank={TARGET}
              onClick={clickOn(move, TARGET)}
            />
          )
        ),
      )}
    </>
  )
}

export default function CubeBoard({
  board = {},
  size = 8,
  layers = [2, 1, 0, -1, -2],
  activeLayer = 0,
  selected = null,
  legalMoves = [],
  goal = null,
  lastMove = null,
  showMoveBalls = true,
  spread = false,
  solo = false,
  side = 'white',
  command = null,
  interactive = true,
  onCellClick,
}) {
  return (
    <Canvas
      camera={{ fov: 30, near: 0.1, far: 200 }}
      dpr={[1, 2]}
      frameloop={interactive ? 'always' : 'demand'}
      style={{ touchAction: 'none', pointerEvents: interactive ? 'auto' : 'none' }}
    >
      <Scene
        board={board}
        size={size}
        layers={layers}
        activeLayer={activeLayer}
        selected={selected}
        legalMoves={legalMoves}
        goal={goal}
        lastMove={lastMove}
        showMoveBalls={showMoveBalls}
        spread={spread}
        solo={solo}
        side={side}
        command={command}
        interactive={interactive}
        onCellClick={onCellClick}
      />
      {!interactive && <KeepDrawn />}
    </Canvas>
  )
}
