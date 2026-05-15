# PlanX: Urban Resilience

QGIS **3.10-3.99** - Processing - **GPL-3**

PlanX Urban Resilience is a modular QGIS suite for early-stage city-scale resilience screening. Version **1.6.0** includes a synthetic QA dataset generator, seismic debris logistics, urban heat comfort risk, pluvial flood susceptibility, social vulnerability, Euclidean and network emergency accessibility, air exposure, green infrastructure drought stress, climate adaptation priority synthesis, scenario comparison, and HTML reporting modules, plus a QGIS dashboard for module discovery and data readiness review.

## Modules

### Synthetic Resilience Demo Dataset

Creates artificial metric layers for smoke testing and teaching the suite without external data. Outputs include study area, buildings, roads, impervious surfaces, green infrastructure, water, shelters, social units, and sensitive receptors.

Suggested smoke-test flow:

- Generate the synthetic dataset.
- Run Heat with study area, buildings, impervious, green, water and sensitive layers.
- Run Air with study area, roads, sensitive receptors and green buffers.
- Run Social with synthetic social units and the generated demographic fields.
- Run Emergency with study area, shelters and buildings or sensitive receptors.
- Run Drought with green infrastructure, impervious surfaces, water and optional tree points.
- Use Synthesis after joining 0-100 risk fields into one planning-unit layer.

A QGIS Console helper is included at `tools/qgis_synthetic_smoke.py`. It generates the demo data and runs the modules that do not require an external DEM or a pre-joined synthesis layer.

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

### Network Emergency Accessibility

Road-network screening model that estimates access distance and travel time from origins such as buildings, facilities or population points to shelters or safe assembly areas. It builds an offline graph from road line vertices and uses multi-source shortest paths from destinations.

Outputs:

- Network accessibility origins
- `net_dist_m`
- `time_min`
- `access_cls`
- `qa_flag`
- Network underserved origins

### Air Quality / Urban Exposure

Planning-support exposure model that combines major road proximity, optional industrial or emission-source proximity, sensitive receptors, and green buffer mitigation.

Outputs:

- Air exposure grid
- `air_score`
- `risk_class`
- Exposed sensitive receptors

### Drought and Green Infrastructure Stress

Green infrastructure stress model for parks, canopy patches, and ecological open spaces. It combines impervious context, distance to water or blue infrastructure, patch size, and optional tree density.

Outputs:

- Green infrastructure stress polygons
- `stress_score`
- `stress_class`
- High-priority patches

### Climate Adaptation Priority Synthesis

Weighted synthesis model for joined planning units. After spatially joining outputs from other modules into one polygon layer, this tool creates a single `adapt_score`, `adapt_class`, top-driver summary, and missing-data flags.

Outputs:

- Climate adaptation priority layer
- `adapt_score`
- `adapt_class`
- `drivers`
- `missing`

### Scenario Comparison / Delta Map

Compares baseline and proposed scenario score fields in the same layer. Lower scores are treated as better, so negative deltas indicate improvement.

Outputs:

- Scenario comparison layer
- `delta`
- `pct_change`
- `change_cls`
- `action_hint`

### Resilience Score HTML Report

Exports a compact standalone HTML summary from any scored resilience layer. It summarizes feature count, score range, average score, high-priority feature count, class distribution, and top driver labels.

Outputs:

- HTML report file

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

- GEE-backed historical climate and land-cover connectors
- PDF atlas export
- Scenario library templates

## Install

Use QGIS Plugin Manager or install the release ZIP from QGIS Plugin Hub / GitHub Releases. For development, add the parent directory of this plugin folder to `QGIS_PLUGINPATH`.

## License

See [LICENSE](LICENSE).
