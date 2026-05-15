# PlanX: Urban Resilience

QGIS **3.10-3.99** · Processing · **GPL-3**

PlanX Urban Resilience is a modular QGIS suite for early-stage city-scale resilience screening. Version **1.1.0** includes seismic debris logistics, urban heat comfort risk, and pluvial flood susceptibility modules, plus a QGIS dashboard for module discovery and data readiness review.

## Modules

### Seismic Debris and Logistics

Monte Carlo seismic scenario analysis for building collapse likelihood, debris spread, road blockage, and post-earthquake clearance corridors.

### Urban Heat Comfort Risk

Offline-first screening model that combines impervious surfaces, building density, green/cooling deficit, and optional vulnerable assets into a 0-100 heat risk grid.

Outputs:

- Heat risk grid
- Priority cooling zones
- Exposed buildings / vulnerable assets

### Pluvial Flood Susceptibility

DEM-based screening model for identifying low-lying, flat, drainage-sensitive areas and exposed buildings or road segments.

Outputs:

- Flood susceptibility grid
- Exposed buildings
- Exposed road segments

This is not a hydrodynamic model. It is intended for planning support, classroom analysis, and prioritization.

## Dashboard

The plugin adds a `PlanX Urban Resilience` toolbar/menu action. The dashboard includes:

- Overview of available modules
- Data readiness report for loaded QGIS layers
- Module cards with required and optional inputs
- Processing launch shortcuts
- Summary guidance and limitations

## Future Roadmap

- Social Vulnerability Index
- Emergency Accessibility and Shelter Coverage
- Air Quality / Urban Exposure
- Drought and Green Infrastructure Stress
- Optional Google Earth Engine backed historical heat/flood/land-cover connector

## Install

Use QGIS Plugin Manager or install the release ZIP from QGIS Plugin Hub / GitHub Releases. For development, add the parent directory of this plugin folder to `QGIS_PLUGINPATH`.

## License

See [LICENSE](LICENSE).
