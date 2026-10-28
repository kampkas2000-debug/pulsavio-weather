"""Downloads the latest model run.

ECMWF IFS (open data, 0.25 deg, CC BY 4.0) through the official ecmwf-opendata client.
NOAA GFS (0.5 deg, public domain) from the NOAA Open Data bucket on AWS, using the .idx files to
fetch only the fields we need (byte ranges), so each step is a few MB instead of hundreds.
"""
import datetime as dt
import os
import concurrent.futures as cf
import urllib.request

UA = {"User-Agent": "PULSAVIO-weather-maps/1.0 (+https://www.pulsavio.workers.dev)"}
STEPS = list(range(0, 121, 3)) + list(range(126, 241, 6))


def http(url, rng=None, timeout=60):
    h = dict(UA)
    if rng:
        h["Range"] = "bytes=%d-%s" % (rng[0], "" if rng[1] is None else rng[1])
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def exists(url):
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


# ── GFS ───────────────────────────────────────────────────────────
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{d}/{h:02d}/atmos/gfs.t{h:02d}z.pgrb2.0p50.f{s:03d}"
GFS_WANT = [("UGRD", "10 m above ground"), ("VGRD", "10 m above ground"), ("TMP", "2 m above ground"),
            ("PRMSL", "mean sea level"), ("TCDC", "entire atmosphere"), ("PRATE", "surface")]


def gfs_latest(now=None):
    """Newest GFS run whose last step we use is already published."""
    now = now or dt.datetime.utcnow()
    t = now.replace(minute=0, second=0, microsecond=0)
    t -= dt.timedelta(hours=t.hour % 6)
    for _ in range(8):
        url = GFS.format(d=t.strftime("%Y%m%d"), h=t.hour, s=STEPS[-1]) + ".idx"
        if exists(url):
            return t
        t -= dt.timedelta(hours=6)
    return None


def _gfs_ranges(idx_text):
    lines = [l.split(":") for l in idx_text.strip().splitlines()]
    out = []
    for want in GFS_WANT:
        for k, l in enumerate(lines):
            if l[3] == want[0] and l[4] == want[1]:
                start = int(l[1])
                end = int(lines[k + 1][1]) - 1 if k + 1 < len(lines) else None
                out.append((start, end))
                break
    return out


def gfs_download(run, step, path):
    base = GFS.format(d=run.strftime("%Y%m%d"), h=run.hour, s=step)
    idx = http(base + ".idx").decode("ascii", "replace")
    with open(path, "wb") as f:
        for rng in _gfs_ranges(idx):
            f.write(http(base, rng))
    return path


def gfs_fetch_all(run, folder):
    os.makedirs(folder, exist_ok=True)
    paths = {}
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(gfs_download, run, s, os.path.join(folder, "gfs_%03d.grib2" % s)): s for s in STEPS}
        for f in cf.as_completed(futs):
            paths[futs[f]] = f.result()
    return paths


# ── ECMWF ─────────────────────────────────────────────────────────
ECMWF_PARAMS = ["10u", "10v", "2t", "msl", "tp"]


def ecmwf_client():
    from ecmwf.opendata import Client
    return Client(source=os.environ.get("ECMWF_SOURCE", "ecmwf"))


def ecmwf_latest():
    c = ecmwf_client()
    # Only 00 and 12 UTC runs reach 240 hours.
    return c.latest(type="fc", step=STEPS[-1], param="2t")


def ecmwf_fetch_all(run, folder):
    os.makedirs(folder, exist_ok=True)
    c = ecmwf_client()
    main = os.path.join(folder, "ecmwf_main.grib2")
    c.retrieve(date=run.strftime("%Y%m%d"), time=run.hour, type="fc", step=STEPS, param=ECMWF_PARAMS, target=main)
    files = [main]
    try:  # total cloud cover is not offered by every version of the open data
        cc = os.path.join(folder, "ecmwf_tcc.grib2")
        c.retrieve(date=run.strftime("%Y%m%d"), time=run.hour, type="fc", step=STEPS, param=["tcc"], target=cc)
        files.append(cc)
    except Exception as e:  # noqa: BLE001
        print("ECMWF: no cloud cover:", e)
    return files
