# Cached Sri Lanka pixel and satellite-pass audit

Prepared `notebooks/CinderTrace_Atlas_LK_Cached_Pixel_Pass_Audit.ipynb` as the next step after the successful six-day observation-evidence pilot. The completed pilot notebook, its returned ZIP, the frozen observed dataset and frontend are preserved.

## Run it

1. Open the new notebook in Colab, using the same Drive account as the completed pilot.
2. Run installation once, restart the Colab session (or VS Code kernel), then continue from step 2 of the notebook without rerunning installation. Run the remaining cells in order. The default `PILOT_ROOT` is `/content/drive/MyDrive/CinderTrace_Observation_Evidence_v1`; change it only if you moved that folder. It must contain the original `science_cache`.
3. No Earthdata login, FIRMS key, input upload or new NASA science download is needed. Colab may request permission to mount Drive. Dependency installation may download Python packages.
4. The audit first hashes all 68 cached science files against the verified download receipts. Reading approximately 5 GiB from Drive can take several minutes. Missing or changed files stop the integrity check; they are never downloaded or silently substituted.
5. Processing writes a separate `pixel_pass_audit_v1` folder. Each completed granule has a derived cache that supports reruns. Allow additional space for nominal-clear-centre tables; retain this derived cache as well as the original science cache.
6. Save notebook outputs and use its last cell to download one review ZIP. Add that ZIP to the project folder. The large original and derived caches are excluded from the ZIP.

## What it checks

The notebook includes frozen inventory, download receipts and 335 matching-date standard archive observations from the already verified data. It records the prior result ZIP hash and observed-manifest hash. Both processing implementations and runtime versions are included in the output bundle.

For every local native fire pixel, it retains source granule, sensor, grid indices, native confidence class, input QA, residual-bowtie status, sparse and geolocation coordinates, coordinate differences, viewing/solar angles and quality-screen exclusion reasons. Sparse locations and confidence must agree with the fire mask. Reprocessed native, clear and screened totals must reproduce the completed pilot. Failures remain explicit and cannot become available zero activity.

Archive type attribution requires a unique spatial candidate within two metres, the same sensor and acquisition interval, with no archive observation reused. Ambiguous/unmatched pixels retain their state and unavailable type. A matched type is a label carried from the standard archive, not independently validated burning-type truth. Unmatched standard observations are exported for review.

Granules are grouped into same-sensor/date/day-night passes with a maximum six-minute gap. These are pilot pass groups; the six selected dates may clip full orbital passes. One-to-one pass assignment maximizes eligible pair count and then minimizes midpoint time separation separately at 30, 60 and 90 minutes. Unknown day/night, incomplete science screens and passes without local centres cannot supply a valid comparison. Each pass appears at most once within a window, but can reappear across sensitivity windows.

Nominal-clear pixel centres are compared through mutual nearest-neighbour matching on a sphere. Distance screens of 250/500 metres and known-geometry/all-view, at-most-40° and at-most-60° viewing screens are prespecified sensitivities. Mutual matching prevents repeated use of a target centre within a comparison. No matched centres means unavailable fire activity on shared support, not zero fire activity.

## Scope and next decision

This improves on coarse H3-label overlap, but remains a point-centre diagnostic. It does not establish physical pixel-footprint equivalence, complete regional area coverage or simultaneous fire conditions. Granule intervals are not precise per-pixel times. The same purposive six-day data appears in multiple sensitivities and is not independent replacement-model evidence.

The immediate decision after reviewing these outputs is whether archive attribution, geometry screening and pass matching are consistent enough to freeze a larger seasonally balanced, multi-year simulated-gap study. That larger study needs disjoint fitting, calibration and evaluation periods and an explicit spatial/type target before fitting replacement models. Historical transfer-chain uncertainty, district/custom-area allocation and all unsupported category/confidence slices remain separate required checks. No reconstructed bands, medians/seasons, gap-filled records or frontend changes are enabled here.

The cache is held in the user's Drive and was not available for a local real-data rerun. The reader and workflow are tested on synthetic NetCDF files, including archive ambiguities, pass reuse prevention, changed files, zero shared support and checkpoint reuse. The standalone notebook's embedded method, frozen inputs, ordinary Python cells and final hashed ZIP export are also checked locally.

## Product references

- [NASA VIIRS imagery geolocation specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP03IMG): pixel-centre coordinates and viewing/solar geometry fields.
- [NASA Collection 2 fire-product guide](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.0.pdf): fire-mask classes, QA, zero-based sparse pixel indices and fire-pixel fields. Runtime units, array shape and sparse/grid consistency checks guard the actual cached product schemas.

## NumPy/SciPy import recovery

An error mentioning `_blas_supports_fpe` during the method-loading cell occurs before science processing and suggests mixed installed/loaded NumPy components. First restart the session/kernel and rerun notebook steps 2 onward, skipping installation. If a fresh session still fails, reinstall NumPy and SciPy together, restart again, and run from step 2. The original science cache is preserved.
