// Classic nautical chart style
export const nautical = {
  id: 'nautical',
  label: 'Nautical',
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
      { id: 'base',     type: 'raster', source: 'base' },
      { id: 'seamarks', type: 'raster', source: 'seamarks',
        paint: { 'raster-opacity': 0.9 } },
    ],
  },
}
