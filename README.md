# PULSAVIO weather maps

The engine behind the wind, temperature, rain, cloud and pressure maps on the PULSAVIO Earth.

Every hour a GitHub Action checks for a new run of two global weather models, and when there is one it
downloads the fields, turns each forecast step (0–240 hours) into two small "data images", and publishes
them here with GitHub Pages: `https://kampkas2000-debug.github.io/pulsavio-weather/latest.json`.

| Model | Resolution | Licence |
|---|---|---|
| ECMWF IFS (open data) | 0.25° | CC BY 4.0. Based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF). |
| NOAA GFS | 0.5° | Public domain (NOAA Open Data Dissemination, AWS). |

Images are 512 × 256 pixels (about 0.7° per pixel): `a.png` = wind east, wind north, temperature at 2 m;
`b.png` = sea-level pressure, cloud cover, precipitation rate. The value ranges are in `latest.json`.

ECMWF does not endorse PULSAVIO. The images are a simplified, resampled version of the model output.
