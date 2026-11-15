import type {Manifest} from './observatoryData';

export default function ProjectMethod({manifest,fileBase}:{manifest:Manifest|null;fileBase:string}){
 return <>
  <span className="eyebrow">DATA, DESIGN & DEVELOPMENT</span>
  <h2>How we built<br/>CinderTrace.</h2>
  <p>CinderTrace brings satellite fire observations and published historical analytics into an interactive web application. We built it for the NASA Space Apps challenge, Harmonization of MODIS and VIIRS Hot Spots, to help people explore burning activity across Sri Lanka, California and New South Wales.</p>

  <h3>NASA data at the foundation</h3>
  <p>Our versioned archive contains 5,072,279 satellite pixel observations spanning 2000–2026. The records originate from NASA’s Fire Information for Resource Management System (FIRMS), covering MODIS on Terra and Aqua and VIIRS on Suomi-NPP, NOAA-20 and NOAA-21. We use an official-source-reconciled standard-data checkpoint for Sri Lanka through 2024 and regional extracts from Portolan’s FIRMS mirror for the remaining years and regions.</p>

  <h3>Preparing the regional archive</h3>
  <p>We used Python to select observations within each region’s reference boundary, remove exact duplicate source records and organise the results by region and year. Each record retains its acquisition time in UTC, coordinates, satellite, confidence, source type, quality and recorded fire radiative power. geoBoundaries administrative files support local area selections. Source-file SHA256 fingerprints and a dataset manifest connect the exported files to their inputs.</p>

  <h3>Building the observation explorer</h3>
  <p>We connected the map, date brush, record inspector and CSV download to one shared selection. Users can filter by satellite, date, confidence and published source attributes, choose an administrative area, draw a polygon or enter coordinates and a radius. Geographic selections use observation point centres. H3 resolution-6 hexagons group records for the map display, while the inspector and CSV provide the individual observations. Flat and raised map views offer two ways to explore the selected pattern.</p>

  <h3>Creating the burning activity calendar</h3>
  <p>For the harmonized historical reference, we integrated Fire Harmony v1.0, published by Kopi and Cosmos (Saw Yong Quan and Yap Yong Son) under CC BY 4.0. Its monthly estimates use the provider’s NOAA-20 scale. We pinned the dataset revision and built the calendar, seasonal charts, annual summaries and year comparisons around that published series. The interface identifies native observations and provider-derived history by their source and scope.</p>
  <p>The calendar offers activity, anomaly and percentile views. We calculate historical comparisons against matching months in 2001–2025, excluding the selected year, and show seasonal medians with interquartile and P10–P90 ranges. Annual summaries use complete twelve-month provider series. New South Wales also supports a July–June calendar for exploring seasons across two years.</p>

  <h3>Adding imagery and geographic context</h3>
  <p>The imagery workspace requests dated MODIS Terra and Aqua true-colour mosaics from NASA Global Imagery Browse Services (GIBS). A swipe comparison lets users explore two dates alongside their selected observations. We also prepared attributed geographic layers for health facilities, response facilities, settlements and protected areas, with source details available in the context panel.</p>

  <h3>Checking the data and calculations</h3>
  <p>We reconciled all 171,244 Sri Lanka standard-data records for 2000–2024 against the authoritative checkpoint, comparing nine native fields. The validation lab presents that source-to-screen check alongside a geographic comparison with CAL FIRE’s Creek Fire final perimeter. Automated checks cover dataset counts, shared selections, historical calculations, imagery requests and report receipts.</p>

  <h3>Turning an investigation into a report</h3>
  <p>Users can save selections, add field notes and export observed CSVs, historical CSVs, calendar images and visual PDF reports. Evidence packs combine selected records, charts, notes, investigation metadata and source receipts. Summaries calculate directly from the selected data. Browser storage retains saved investigations, and the app caches its interface and recently visited archives for field use.</p>

  <h3>The tools behind the experience</h3>
  <p>We developed the interface with React and TypeScript, using Vite for production builds. Mapbox GL powers the observation map, Three.js provides the terrain and raised hexagon view, and GSAP handles camera and interface animation. Python, pandas, NumPy, Shapely and H3 support data preparation and geographic processing. jsPDF creates browser-based reports, and fflate packages downloadable evidence. Compressed static datasets load by region and year, allowing the production website to run as a static deployment on Vercel.</p>

  <h3>Sources and project files</h3>
  <p>
   <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS fire observations ↗</a><br/>
   <a href="https://nasa-gibs.github.io/gibs-api-docs/" target="_blank" rel="noreferrer">NASA GIBS satellite imagery ↗</a><br/>
   <a href="https://github.com/portolan-mirrors/firms-catalog" target="_blank" rel="noreferrer">Portolan source catalogue ↗</a><br/>
   <a href="https://huggingface.co/datasets/warrensaw530/fire-harmony" target="_blank" rel="noreferrer">Fire Harmony dataset · CC BY 4.0 ↗</a><br/>
   <a href="https://github.com/Warren-530/fire-harmony" target="_blank" rel="noreferrer">Fire Harmony method and code ↗</a><br/>
   <a href="https://www.geoboundaries.org/" target="_blank" rel="noreferrer">geoBoundaries administrative boundaries ↗</a><br/>
   <a href="https://github.com/kavishan-weer/CinderTrace" target="_blank" rel="noreferrer">CinderTrace source code ↗</a><br/>
   <a href={fileBase+'manifest.json'} download>Download dataset manifest ↗</a>
  </p>
  <small>{manifest?.version} · provider revision {manifest?.provider.revision}</small>
 </>;
}
