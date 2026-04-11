# PlanX: Urban Resilience

QGIS **3.10–3.99** · Processing · **GPL-3**

Suite for urban resilience analyses. **Current release (1.0.1):** one Processing tool — Monte Carlo seismic scenario with building collapse likelihood, debris on the road network, and post-earthquake clearance corridors. More modules may be added later in the same plugin.

| | |
|--|--|
| **Issues** | [github.com/YusufEminoglu/planx_urban_resilience/issues](https://github.com/YusufEminoglu/planx_urban_resilience/issues) |
| **Source** | [github.com/YusufEminoglu/planx_urban_resilience](https://github.com/YusufEminoglu/planx_urban_resilience) |

## Install (users)

QGIS → **Plugins** → **Manage and Install Plugins** → **Install from ZIP** and pick the official `.zip` (e.g. from [plugins.qgis.org](https://plugins.qgis.org) when listed, or from GitHub Releases if you publish one).

## Install (developers)

1. Clone this repository (root = plugin folder: `__init__.py`, `metadata.txt`, …).
2. Add the **parent directory** of that folder to **`QGIS_PLUGINPATH`**, restart QGIS, enable **PlanX: Urban Resilience**.
3. Release version and changelog: edit **`metadata.txt`**, then build a Hub-ready ZIP (single top-level folder `planx_urban_resilience/`; use a ZIP tool that stores **/** paths, not Windows `Compress-Archive` backslashes).

## License

See [LICENSE](LICENSE).
