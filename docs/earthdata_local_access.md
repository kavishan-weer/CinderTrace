# Local Earthdata access for the Sri Lanka pilot

The first batch contains 60 files (about 37 MB) for disputed January 2001 and December 2023, with populated January 2002 and December 2022 controls. It reads regional daily fire masks and quality classes; it does not restore zero months or change production data.

Run this in the project terminal after the optional observation dependencies have been installed:

```sh
cd '/Users/kavishanwee/Documents/ignite copy'
.venv/bin/python -m pipeline.lk_observation_analysis --login
```

Enter your Earthdata username and password in the local terminal prompts. Password entry is hidden. The login is not persisted: this flow does not write credentials to `.netrc`, tracked files, logs or chat. Signing in to NASA in a browser does not authenticate this separate local process. If NASA asks you to approve the data-provider application, complete that approval on NASA's site.

The command authenticates, downloads and verifies the first batch, and then computes daily tile counts and monthly screening summaries. Credentials remain in the local process only. Downloads are cached under `data/observation_pilot/lk/science_files/`; output folders begin with `analysis_`. A nonsecret summary is also written to `docs/lk_observation_pixel_screening.json` when analysis succeeds.

After downloads, cached files can be analyzed without another login:

```sh
.venv/bin/python -m pipeline.lk_observation_analysis --analyze-only
```

A screening summary is not archive certification. Daily composites do not enumerate all swaths or overpasses. Fire, nonfire, cloud, unknown, missing input and quality classes remain separate. Usable-class fractions exclude QA-missing pixels and are reported without automatically declaring a month eligible. Compare any discrepancies against swath products before restoring zeros or recalculating baselines.

The optional libraries are pinned in `requirements-observations.txt`. This bounded downloader uses [NASA's documented Python authentication method](https://urs.earthdata.nasa.gov/documentation/for_users/data_access/python), with an in-memory cookie jar and credentials scoped to the HTTPS Earthdata host.

Downloads retry transient errors up to four times and compare HDF signatures and catalogue byte sizes. Re-running the same command reuses verified cached files. An interrupted nonpersistent login requires entering credentials again. Errors identify the file and HTTP status or transport error type without displaying authentication material.
