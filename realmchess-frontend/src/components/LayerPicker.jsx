import { LAYERS } from '../lib/chess.js'

// One button per layer on the board; the chosen one takes its layer's colour
export default function LayerPicker({ layers, value, onChange }) {
  return (
    <div className="layer-picker" role="group" aria-label="Current layer">
      {LAYERS.filter((layer) => layers.includes(layer.z)).map((layer) => (
        <button
          key={layer.z}
          type="button"
          className={`button layer-button ${value === layer.z ? 'is-selected' : ''}`}
          aria-pressed={value === layer.z}
          style={value === layer.z ? { background: layer.light, borderColor: layer.light } : undefined}
          onClick={() => onChange(layer.z)}
        >
          <i className="swatch" style={{ background: layer.dark }} />
          {layer.name}
        </button>
      ))}
    </div>
  )
}
