// Ocean depth — Stamen Watercolor darkened for ops readability
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
      {
        id: 'base', type: 'raster', source: 'base',
        // Watercolor is very bright & warm — darken and desaturate for legibility
        paint: {
          'raster-opacity': 1.0,
          'raster-brightness-min': 0.0,
          'raster-brightness-max': 0.52,
          'raster-saturation': -0.30,
          'raster-contrast': 0.10,
        },
      },
      {
        id: 'seamarks', type: 'raster', source: 'seamarks',
        paint: { 'raster-opacity': 0.80 },
      },
    ],
  },
}
