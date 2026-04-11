# PlanX: Urban Resilience

**QGIS 3.10–3.99** · Processing provider · **GPL-3**

| | |
|--|--|
| **Version** | 1.0.1 |
| **Author** | Araş. Gör. Yusuf Eminoğlu |
| **Repository** | https://github.com/YusufEminoglu/planx_urban_resilience |
| **Issues** | https://github.com/YusufEminoglu/planx_urban_resilience/issues |

## Description

PlanX urban resilience suite for QGIS. Version 1.0 ships the seismic module: Monte Carlo building collapse, debris on the transport network, and post-earthquake clearance corridors. Additional hazard modules (heat, flood, livability, etc.) will be added over time in the same plugin.

## About

Single Processing provider umbrella for city-scale resilience analyses. Current focus: stochastic seismic debris and logistics on vector road and building layers.


## Features (current)

This plugin registers a **Processing** provider. Open **Processing Toolbox** and look under the provider name above.

Source layout: `planx_urban_resilience/processing/` (add new modules there as the suite grows).

**Current module:** seismic Monte Carlo debris, road blockage, and clearance corridors (`processing/seismic/`).

## Install

- **From ZIP (Plugin Hub / manual):** install the released `.zip` in QGIS **Plugins → Manage and Install Plugins → Install from ZIP**.  
  Hub packages for this repo are built with `packaging/Build-PluginZip.ps1` (POSIX-safe paths).

- **Development:** add the parent folder of this plugin to `QGIS_PLUGINPATH` so QGIS loads `planx_urban_resilience/`.

## Development & packaging

From the monorepo root `qgis_plugins/`:

```powershell
# Regenerate this README from metadata.txt (after version / description edits)
py -3 packaging\gen_plugin_readme.py planx_urban_resilience

# Hub-style zip → QGIS_Plugin_Releases\<plugin>.zip
.\packaging\Build-PluginZip.ps1 -PluginDir planx_urban_resilience
```

Re-run **`gen_plugin_readme.py`** whenever you change `metadata.txt` and want the GitHub README to stay in sync.

## License

See [LICENSE](LICENSE) in this repository (GPL-3).
