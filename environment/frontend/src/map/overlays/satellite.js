// Satellite imagery with seamark overlay
export const satellite = {
  id: 'satellite',
  label: 'Satellite',
  style: {
    version: 8,
    sources: {
      base: {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri, Maxar, Earthstar Geographics',
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
        paint: { 'raster-opacity': 0.8 } },
    ],
  },
}
