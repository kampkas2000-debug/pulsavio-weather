"""PULSAVIO weather maps engine. Runs on GitHub Actions every hour.

  python engine/build.py --check       prints changed=true when a newer ECMWF or GFS run exists
  python engine/build.py --out site    downloads both models and writes the map images + latest.json

Output (served by GitHub Pages, read by the PULSAVIO Earth):
  latest.json
  ecmwf/<run>/<step>a.png, <step>b.png
  gfs/<run>/<step>a.png, <step>b.png
"""
import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import encode  # noqa: E402
import sources  # noqa: E402

PAGES_URL = os.environ.get("PAGES_URL", "")
CREDITS = {
    "ecmwf": "Based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF), CC BY 4.0. Images made by PULSAVIO.",
    "gfs": "NOAA Global Forecast System (GFS), public domain, via NOAA Open Data Dissemination. Images made by PULSAVIO.",
}


def runkey(t):
    return t.strftime("%Y%m%d%H")


def published():
    if not PAGES_URL:
        return {}
    try:
        with urllib.request.urlopen(PAGES_URL.rstrip("/") + "/latest.json?nocache=%d" % time.time(), timeout=30) as r:
            return json.load(r)
    except Exception:
        return {}


def latest_runs():
    runs = {}
    try:
        runs["ecmwf"] = sources.ecmwf_latest()
    except Exception as e:  # noqa: BLE001
        print("ECMWF latest failed:", e)
    try:
        runs["gfs"] = sources.gfs_latest()
    except Exception as e:  # noqa: BLE001
        print("GFS latest failed:", e)
    return {k: v for k, v in runs.items() if v}


def read_grib(paths):
    """{(shortName, step): (values 2-D, lats 1-D, lons 1-D)} using pygrib."""
    import pygrib
    out = {}
    for p in paths:
        for g in pygrib.open(p):
            vals = g.values
            lats, lons = g.latlons()
            step = int(g.endStep) if hasattr(g, "endStep") else int(g.forecastTime)
            out[(g.shortName, step)] = (np.ma.filled(vals, np.nan), lats[:, 0], lons[0, :])
    return out


def to_grid(item):
    vals, lats, lons = item
    return encode.regrid(vals, lats, lons)


def build_model(model, run, folder, out):
    tmp = tempfile.mkdtemp(prefix=model)
    if model == "gfs":
        paths = sources.gfs_fetch_all(run, tmp)
        data = read_grib(paths.values())
    else:
        data = read_grib(sources.ecmwf_fetch_all(run, tmp))
    names = {"gfs": {"u": "10u", "v": "10v", "t": "2t", "p": "prmsl", "c": "tcc", "r": "prate"},
             "ecmwf": {"u": "10u", "v": "10v", "t": "2t", "p": "msl", "c": "tcc", "r": "tp"}}[model]
    key = runkey(run)
    os.makedirs(os.path.join(out, model, key), exist_ok=True)
    done, prev_tp = [], None
    zeros = np.zeros((encode.H, encode.W))
    for s in sources.STEPS:
        try:
            u, v = to_grid(data[(names["u"], s)]), to_grid(data[(names["v"], s)])
            t = to_grid(data[(names["t"], s)]) - 273.15
            p = to_grid(data[(names["p"], s)]) / 100.0
        except KeyError:
            print(model, "missing step", s)
            continue
        c = to_grid(data[(names["c"], s)]) if (names["c"], s) in data else zeros
        if c.max() <= 1.01:
            c = c * 100.0
        if model == "gfs":
            r = to_grid(data[(names["r"], s)]) * 3600.0 if (names["r"], s) in data else zeros
        else:  # ECMWF total precipitation is accumulated (metres) from the start of the run
            tp = to_grid(data[(names["r"], s)]) if (names["r"], s) in data else None
            if tp is None or prev_tp is None:
                r = zeros
            else:
                r = np.maximum(tp - prev_tp[1], 0) * 1000.0 / max(1, s - prev_tp[0])
            if tp is not None:
                prev_tp = (s, tp)
        a_img, b_img = encode.encode(u, v, t, p, c, r)
        encode.save(a_img, os.path.join(out, model, key, "%03da.png" % s))
        encode.save(b_img, os.path.join(out, model, key, "%03db.png" % s))
        done.append(s)
    return {"run": run.strftime("%Y-%m-%dT%H:00Z"), "path": "%s/%s/" % (model, key), "steps": done, "credit": CREDITS[model]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    runs = latest_runs()
    print("latest runs:", {k: runkey(v) for k, v in runs.items()})
    old = published()
    old_runs = {k: v.get("run") for k, v in (old.get("models") or {}).items()}
    new = {k: v.strftime("%Y-%m-%dT%H:00Z") for k, v in runs.items()}
    changed = any(new.get(k) != old_runs.get(k) for k in new)
    if args.check:
        print("changed=%s" % ("true" if changed else "false"))
        with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
            f.write("changed=%s\n" % ("true" if changed else "false"))
        return
    os.makedirs(args.out, exist_ok=True)
    log, models = [], {}
    for model, run in runs.items():
        t0 = time.time()
        try:
            models[model] = build_model(model, run, args.out, args.out)
            log.append("%s %s: %d steps in %.0fs" % (model, runkey(run), len(models[model]["steps"]), time.time() - t0))
        except Exception as e:  # noqa: BLE001
            log.append("%s %s FAILED: %r" % (model, runkey(run), e))
    latest = {"generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "size": [encode.W, encode.H],
              "scales": encode.SCALES, "models": models}
    with open(os.path.join(args.out, "latest.json"), "w") as f:
        json.dump(latest, f, separators=(",", ":"))
    with open(os.path.join(args.out, "log.txt"), "w") as f:
        f.write("\n".join(log) + "\n")
    with open(os.path.join(args.out, "index.html"), "w") as f:
        f.write("<!doctype html><meta charset=utf-8><title>PULSAVIO weather maps data</title><p>Data images for the PULSAVIO Earth. "
                "ECMWF: based on data and products of ECMWF (CC BY 4.0). GFS: NOAA (public domain).</p><pre>%s</pre>" % "\n".join(log))
    print("\n".join(log))
    if not models:
        sys.exit(1)


if __name__ == "__main__":
    main()
