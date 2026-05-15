# PlanX: Urban Resilience

QGIS **3.10-3.99** - Processing - **GPL-3**

PlanX Urban Resilience is a modular QGIS suite for early-stage city-scale resilience screening. Version **1.2.0** includes seismic debris logistics, urban heat comfort risk, pluvial flood susceptibility, social vulnerability, and emergency accessibility modules, plus a QGIS dashboard for module discovery and data readiness review.

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

### Social Vulnerability Index

Weighted screening model for neighborhood, census, or planning-unit polygons. It can combine population density, elderly population, children, disability or care needs, and low-income/deprivation indicators into a normalized 0-100 `svi_score`.

Outputs:

- Social vulnerability polygons
- `svi_score`
- `svi_class`
- `pop_density`
- `data_flags` for missing optional indicators

### Emergency Accessibility and Shelter Coverage

Grid-based accessibility deficit model for shelters, safe assembly areas, or emergency service points. It identifies places beyond a target service distance and optionally flags underserved buildings, facilities, or population assets.

Outputs:

- Emergency accessibility grid
- `access_score`
- `access_class`
- Underserved assets

## Dashboard

The plugin adds a `PlanX Urban Resilience` toolbar/menu action. The dashboard includes:

- Overview of available modules
- Data readiness report for loaded QGIS layers
- Module cards with required and optional inputs
- Processing launch shortcuts
- Summary guidance and limitations

## Important Limitations

These modules are screening and prioritization tools. They are designed for planning studios, early feasibility studies, and comparative spatial analysis. They do not replace engineering-grade seismic, hydrodynamic, microclimate, public-health, or evacuation-network models.

## Future Roadmap

- Air Quality / Urban Exposure
- Drought and Green Infrastructure Stress
- Climate adaptation priority synthesis
- Optional Google Earth Engine backed historical heat/flood/land-cover connector

## Install

Use QGIS Plugin Manager or install the release ZIP from QGIS Plugin Hub / GitHub Releases. For development, add the parent directory of this plugin folder to `QGIS_PLUGINPATH`.

## License

See [LICENSE](LICENSE).
