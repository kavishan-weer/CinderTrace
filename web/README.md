# CinderTrace Observatory

The interactive application for **CinderTrace**, developed for the NASA Space Apps challenge **Harmonization of MODIS and VIIRS Hot Spots**.

Read the [project overview](../README.md) for the challenge, illustrated features, data workflow and source credits.

## What the application includes

- An observation atlas for Sri Lanka, California and New South Wales, with shared date, satellite and geographic filters.
- A burning activity calendar using attributed Fire Harmony v1.0 monthly estimates, with seasonal patterns and year comparisons.
- Dated NASA GIBS imagery, geographic context layers and a validation workspace.
- Guided investigations, saved field notes, CSV downloads, calendar images, visual PDF reports and evidence packs.

## How it works

React and TypeScript connect the map, timeline, inspector and downloads to one observation selection. Mapbox GL renders the map, H3 groups observations into display cells, and Three.js provides raised hexagons and the terrain illustration. GSAP supports camera and interface motion.

Python prepares the regional datasets before the browser loads them. The application retrieves compressed archives by region and year, calculates selection summaries locally, and creates reports and evidence downloads in the browser.

## Data and attribution

| Files | Contents |
| --- | --- |
| `site-public/ready/` | Prepared NASA FIRMS observations, Fire Harmony monthly series and the dataset manifest |
| `site-public/context/` | Geographic context, imagery and source credits |
| `site-public/validation/` | Source reconciliation and the CAL FIRE geographic reference case |

NASA FIRMS supplies the underlying MODIS and VIIRS observations. NASA GIBS supplies dated satellite imagery. Portolan provides mirrored observation archives. **Fire Harmony v1.0**, by **Kopi and Cosmos (Saw Yong Quan and Yap Yong Son)**, supplies the published harmonized historical reference under **CC BY 4.0**.

The in-app **Data & method** section explains preparation, calculations and exports. See the [project’s source credits](../README.md#sources-and-credit) and [data attribution](site-public/ATTRIBUTION.md) for the supporting resources.
