// Procedural 3D chess pieces, the move ball and the dungeon rock.
// One unit = one board cell. Every model stands on y = 0, centred on the cell.
import * as THREE from 'three'

const SEGMENTS = 56

// Profiles are [radius, height] pairs spun around the vertical axis
const PROFILES = {
  Pawn: [
    [0, 0], [0.26, 0], [0.26, 0.04], [0.23, 0.07], [0.17, 0.09], [0.12, 0.14], [0.09, 0.24], [0.075, 0.32],
    [0.13, 0.34], [0.13, 0.36], [0.07, 0.38], [0.1, 0.41], [0.125, 0.46], [0.115, 0.51], [0.08, 0.55], [0, 0.565],
  ],
  Rook: [
    [0, 0], [0.29, 0], [0.29, 0.05], [0.25, 0.08], [0.19, 0.11], [0.15, 0.18], [0.14, 0.4], [0.17, 0.44],
    [0.195, 0.46], [0.195, 0.58], [0.14, 0.58], [0.14, 0.53], [0, 0.53],
  ],
  Bishop: [
    [0, 0], [0.29, 0], [0.29, 0.05], [0.25, 0.08], [0.18, 0.11], [0.12, 0.18], [0.085, 0.36], [0.07, 0.46],
    [0.14, 0.48], [0.14, 0.5], [0.075, 0.52], [0.1, 0.56], [0.125, 0.62], [0.11, 0.68], [0.06, 0.74],
    [0.03, 0.76], [0.045, 0.78], [0.035, 0.8], [0, 0.81],
  ],
  Queen: [
    [0, 0], [0.31, 0], [0.31, 0.05], [0.27, 0.08], [0.2, 0.11], [0.13, 0.2], [0.09, 0.42], [0.075, 0.56],
    [0.15, 0.58], [0.15, 0.6], [0.08, 0.62], [0.1, 0.68], [0.16, 0.77], [0.14, 0.78], [0.09, 0.74], [0, 0.74],
  ],
  King: [
    [0, 0], [0.31, 0], [0.31, 0.05], [0.27, 0.08], [0.2, 0.11], [0.13, 0.2], [0.09, 0.42], [0.075, 0.56],
    [0.15, 0.58], [0.15, 0.6], [0.08, 0.62], [0.11, 0.68], [0.15, 0.75], [0.13, 0.77], [0.06, 0.78], [0, 0.785],
  ],
  KnightBase: [
    [0, 0], [0.29, 0], [0.29, 0.05], [0.25, 0.08], [0.19, 0.11], [0.16, 0.16], [0.15, 0.2], [0, 0.2],
  ],
}

function lathe(points) {
  return new THREE.LatheGeometry(points.map(([r, y]) => new THREE.Vector2(r, y)), SEGMENTS)
}

function knightHead() {
  // Side silhouette of the horse head, nose toward +x, then given thickness
  const shape = new THREE.Shape()
  shape.moveTo(-0.13, 0.18)
  shape.quadraticCurveTo(-0.2, 0.38, -0.1, 0.55)
  shape.lineTo(-0.045, 0.69)
  shape.lineTo(0.0, 0.61)
  shape.quadraticCurveTo(0.11, 0.59, 0.2, 0.46)
  shape.lineTo(0.215, 0.4)
  shape.lineTo(0.16, 0.365)
  shape.quadraticCurveTo(0.09, 0.41, 0.06, 0.33)
  shape.quadraticCurveTo(0.08, 0.25, 0.13, 0.18)
  shape.closePath()
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.13,
    bevelEnabled: true,
    bevelThickness: 0.03,
    bevelSize: 0.025,
    bevelSegments: 4,
    curveSegments: 16,
  })
  geometry.translate(0, 0, -0.065)
  return geometry
}

export function pieceMaterial(color) {
  return color === 'white'
    ? new THREE.MeshPhysicalMaterial({ color: '#cfc6b4', roughness: 0.42, clearcoat: 0.45, clearcoatRoughness: 0.3 })
    : new THREE.MeshPhysicalMaterial({ color: '#2b2e38', roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.25 })
}

// type: King | Queen | Rook | Bishop | Knight | Pawn, color: white | black
export function createPiece(type, color) {
  const material = pieceMaterial(color)
  const group = new THREE.Group()
  const add = (geometry, x = 0, y = 0, z = 0) => {
    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(x, y, z)
    group.add(mesh)
    return mesh
  }

  if (type === 'Knight') {
    add(lathe(PROFILES.KnightBase))
    const head = add(knightHead())
    // White faces up the board (toward higher ranks, -z), black faces down it
    head.rotation.y = color === 'white' ? Math.PI / 2 : -Math.PI / 2
    return group
  }

  add(lathe(PROFILES[type]))

  if (type === 'Rook') {
    // Battlements around the rim
    for (let i = 0; i < 6; i++) {
      const angle = (i / 6) * Math.PI * 2
      const merlon = add(new THREE.BoxGeometry(0.075, 0.07, 0.11), Math.cos(angle) * 0.165, 0.615, Math.sin(angle) * 0.165)
      merlon.rotation.y = -angle
    }
  }
  if (type === 'Queen') {
    for (let i = 0; i < 8; i++) {
      const angle = (i / 8) * Math.PI * 2
      add(new THREE.SphereGeometry(0.032, 16, 12), Math.cos(angle) * 0.15, 0.795, Math.sin(angle) * 0.15)
    }
    add(new THREE.SphereGeometry(0.05, 20, 16), 0, 0.79, 0)
  }
  if (type === 'King') {
    add(new THREE.BoxGeometry(0.045, 0.16, 0.045), 0, 0.86, 0)
    add(new THREE.BoxGeometry(0.13, 0.045, 0.045), 0, 0.875, 0)
  }
  return group
}

// A see-through glass ball that floats inside a cell to mark a legal move
export function createMoveBall() {
  const material = new THREE.MeshPhysicalMaterial({
    color: '#22c7a9',
    roughness: 0.15,
    clearcoat: 1,
    clearcoatRoughness: 0.1,
    transparent: true,
    opacity: 0.6,
  })
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.27, 48, 32), material)
  ball.position.y = 0.42
  return ball
}

export function createRock() {
  const material = new THREE.MeshStandardMaterial({ color: '#6c6276', roughness: 0.95, flatShading: true })
  const rock = new THREE.Mesh(new THREE.DodecahedronGeometry(0.36, 0), material)
  rock.scale.set(1, 0.78, 0.92)
  rock.rotation.set(0.3, 0.6, 0.1)
  rock.position.y = 0.27
  return rock
}
