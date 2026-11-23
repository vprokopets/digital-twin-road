/**
 * Eagerly initializes PrismJS and binds `globalThis.Prism` before any side-effectful
 * `prismjs/components/*` language grammar imports execute in Vite/Rolldown bundles.
 */
import Prism from 'prismjs'
import 'prismjs/themes/prism-tomorrow.css'

// Eagerly evaluate the CommonJS factory and bind globalThis.Prism before
// side-effectful prismjs/components/* grammar scripts run in Vite/Rolldown chunks.
;(globalThis as Record<string, unknown>).Prism = Prism
Prism.manual = true

export default Prism
