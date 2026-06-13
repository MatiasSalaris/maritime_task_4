// Classic nautical chart — OSM tiles darkened for tactical contrast
export const nautical = {
  id: 'nautical',
  label: 'Nautica',
  style: {
    version: 8,
    sources: {
      base: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
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
        // OSM is white/light — crush brightness so agent glows pop
        paint: {
          'raster-opacity': 1.0,
          'raster-brightness-min': 0.0,
          'raster-brightness-max': 0.45,
          'raster-saturation': -0.50,
          'raster-contrast': 0.10,
        },
      },
      {
        id: 'seamarks', type: 'raster', source: 'seamarks',
        paint: { 'raster-opacity': 0.88 },
      },
    ],
  },
}
