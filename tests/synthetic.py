"""Synthetic weather (moving lows and highs) shaped like real model output, for testing offline.
Also writes the test maps the PULSAVIO dev server uses."""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import build  # noqa: E402
import encode  # noqa: E402
import sources  # noqa: E402

LATS = np.linspace(90, -90, 361)          # GFS-like 0.5 degree grid, longitudes 0..359.5
LONS = np.arange(0, 360, 0.5)
LON2, LAT2 = np.meshgrid(LONS, LATS)
RNG = np.random.default_rng(3)
SYSTEMS = [(lat, lon, amp, rad, dlon) for lat, lon, amp, rad, dlon in
           [(52, 330, -32, 12, 1.2), (60, 180, -26, 14, 1.0), (45, 25, -14, 8, 0.8), (-50, 60, -36, 14, 1.5), (-55, 200, -30, 15, 1.4),
            (35, 320, 22, 18, 0.3), (30, 220, 18, 20, 0.2), (-30, 280, 16, 18, 0.3), (-30, 80, 15, 18, 0.4), (50, 100, 20, 15, 0.2),
            (15, 300, -12, 4, -1.2), (18, 130, -24, 4, -0.9)]]


def dist_deg(lat1, lon1, lat2, lon2):
    d = np.radians
    c = np.sin(d(lat1)) * np.sin(d(lat2)) + np.cos(d(lat1)) * np.cos(d(lat2)) * np.cos(d(lon1 - lon2))
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def fields(step):
    p = np.full(LAT2.shape, 1013.0) + 6 * np.cos(np.radians(LAT2) * 3)  # subtropical highs, polar lows
    for lat, lon, amp, rad, dlon in SYSTEMS:
        lo = (lon + dlon * step) % 360
        p += amp * np.exp(-(dist_deg(LAT2, LON2, lat, lo) / rad) ** 2)
    # geostrophic-like wind from the pressure gradient (+ friction turning)
    dpdy, dpdx = np.gradient(p)
    f = np.sign(LAT2) * np.maximum(np.abs(np.sin(np.radians(LAT2))), 0.25)
    coslat = np.maximum(np.cos(np.radians(LAT2)), 0.1)
    k = 3.2
    u = -k * (-dpdy) / f * 1.0 - 0.3 * dpdx / coslat
    v = k * (dpdx / coslat) / f - 0.3 * (-dpdy)
    u += np.where(np.abs(LAT2) < 25, -6.0, 0) + np.where(np.abs(LAT2) > 35, 4.0, 0)  # trade winds, westerlies
    u, v = np.clip(u, -38, 38), np.clip(v, -38, 38)
    hour = (step + 0) % 24
    t = 28 - 0.55 * np.abs(LAT2) ** 1.08 + 4 * np.cos(np.radians(LON2 + 15 * hour - 180)) * np.cos(np.radians(LAT2)) + RNG.normal(0, 0.4, LAT2.shape)
    low = np.clip(1013 - p, 0, None)
    c = np.clip(low * 7 + 25 * np.sin(np.radians(LON2 * 3 + step * 4)) * np.cos(np.radians(LAT2 * 4)) + 20, 0, 100)
    r = np.clip((low - 6) * 0.45, 0, None) * (0.6 + 0.4 * np.sin(np.radians(LON2 * 7 + LAT2 * 5)))
    return u, v, t, p, c, r


def write_maps(out, model="gfs"):
    run = dt.datetime(2026, 10, 28, 0)
    key = build.runkey(run)
    os.makedirs(os.path.join(out, model, key), exist_ok=True)
    for s in sources.STEPS:
        u, v, t, p, c, r = fields(s)
        g = lambda x: encode.regrid(x, LATS, LONS)  # noqa: E731
        a, b = encode.encode(g(u), g(v), g(t), g(p), g(c), g(r))
        encode.save(a, os.path.join(out, model, key, "%03da.png" % s))
        encode.save(b, os.path.join(out, model, key, "%03db.png" % s))
    return {"run": "2026-10-28T00:00Z", "path": "%s/%s/" % (model, key), "steps": sources.STEPS, "credit": build.CREDITS[model] + " (TEST DATA)"}


if __name__ == "__main__":
    out = sys.argv[1]
    models = {"ecmwf": write_maps(out, "ecmwf"), "gfs": write_maps(out, "gfs")}
    with open(os.path.join(out, "latest.json"), "w") as f:
        json.dump({"generated": "2026-10-28T08:00:00Z", "size": [encode.W, encode.H], "scales": encode.SCALES, "models": models, "test": True}, f)
    print("ok", out)
