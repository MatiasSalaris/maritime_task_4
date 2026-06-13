export { tactical }    from './tactical.js'
export { nautical }    from './nautical.js'
export { satellite }   from './satellite.js'
export { bathymetric } from './bathymetric.js'

import { tactical }    from './tactical.js'
import { nautical }    from './nautical.js'
import { satellite }   from './satellite.js'
import { bathymetric } from './bathymetric.js'

export const OVERLAYS = [tactical, nautical, satellite, bathymetric]
export const OVERLAY_MAP = Object.fromEntries(OVERLAYS.map(o => [o.id, o]))
