// Ocean depth (GEBCO bathymetry) — great for maritime ops look
export const bathymetric = {
  id: 'bathymetric',
  label: 'Bathymetric',
  style: {
    version: 8,
    sources: {
      base: {
        type: 'raster',
        tiles: [
          'https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg',
        ],
        tileSize: 256,
        attribution: '© Stadia Maps © Stamen Design © OpenStreetMap',
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
        paint: { 'raster-opacity': 0.7 } },
    ],
  },
}
