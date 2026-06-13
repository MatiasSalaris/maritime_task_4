// Dark tactical/military overlay — default for demos
export const tactical = {
  id: 'tactical',
  label: 'Tattica',
  style: {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      base: {
        type: 'raster',
        tiles: ['https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© Stadia Maps © OpenMapTiles © OpenStreetMap',
      },
      seamarks: {
        type: 'raster',
        tiles: ['https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenSeaMap',
      },
    },
    layers: [
      {
        id: 'base', type: 'raster', source: 'base',
        paint: {
          'raster-opacity': 1.0,
          'raster-brightness-min': 0.0,
          'raster-brightness-max': 1.0,
          'raster-saturation': 0.0,
          'raster-contrast': 0.0,
        },
      },
      {
        id: 'seamarks', type: 'raster', source: 'seamarks',
        paint: { 'raster-opacity': 0.75 },
      },
    ],
  },
}
