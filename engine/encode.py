"""Turn model fields into small PNG "data images" the PULSAVIO Earth can draw.

Every forecast step becomes two 512 x 256 RGB images (about 0.7 degrees per pixel, whole planet):
  a.png  R = wind east (u), G = wind north (v), B = temperature at 2 m
  b.png  R = sea-level pressure, G = cloud cover, B = precipitation rate (square-root scale)
Pixel (i, j) is the cell centred at lon = -180 + (i + 0.5) * 360/W, lat = 90 - (j + 0.5) * 180/H.
The value ranges are written to latest.json so the site decodes them without guessing.
"""
import numpy as np
from PIL import Image

W, H = 512, 256
SCALES = {
    "a": {"r": ["u", -40.0, 40.0], "g": ["v", -40.0, 40.0], "b": ["t", -50.0, 50.0]},
    "b": {"r": ["p", 950.0, 1060.0], "g": ["c", 0.0, 100.0], "b": ["rain", 0.0, 50.0]},  # rain: sqrt scale (mm/h)
}
T_LON = -180.0 + (np.arange(W) + 0.5) * 360.0 / W
T_LAT = 90.0 - (np.arange(H) + 0.5) * 180.0 / H


def regrid(field, lats, lons):
    """Bilinear resampling of a regular lat/lon grid (any orientation, 0..360 or -180..180) to W x H."""
    field = np.asarray(field, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    if lats[0] < lats[-1]:  # make latitude descend (north first)
        lats = lats[::-1]
        field = field[::-1, :]
    lon0, dlon = lons[0], lons[1] - lons[0]
    nlon = len(lons)
    # fractional source column for every target longitude, wrapping around the globe
    x = ((T_LON - lon0) % 360.0) / dlon
    x0 = np.floor(x).astype(int) % nlon
    x1 = (x0 + 1) % nlon
    fx = x - np.floor(x)
    dlat = lats[0] - lats[1]
    y = np.clip((lats[0] - T_LAT) / dlat, 0, len(lats) - 1)
    y0 = np.floor(y).astype(int)
    y1 = np.minimum(y0 + 1, len(lats) - 1)
    fy = y - y0
    f00 = field[np.ix_(y0, x0)]
    f01 = field[np.ix_(y0, x1)]
    f10 = field[np.ix_(y1, x0)]
    f11 = field[np.ix_(y1, x1)]
    fx = fx[None, :]
    fy = fy[:, None]
    return (f00 * (1 - fx) + f01 * fx) * (1 - fy) + (f10 * (1 - fx) + f11 * fx) * fy


def _byte(v, lo, hi):
    v = np.nan_to_num(np.asarray(v, dtype=np.float64), nan=lo)
    return np.clip(np.round((v - lo) / (hi - lo) * 255.0), 0, 255).astype(np.uint8)


def encode(u, v, t_c, p_hpa, cloud_pct, rain_mmh):
    """All inputs already on the W x H target grid. Returns (a_image, b_image)."""
    s = SCALES
    a = np.dstack([_byte(u, *s["a"]["r"][1:]), _byte(v, *s["a"]["g"][1:]), _byte(t_c, *s["a"]["b"][1:])])
    rain = np.sqrt(np.clip(np.nan_to_num(rain_mmh), 0, 50.0) / 50.0) * 50.0
    b = np.dstack([_byte(p_hpa, *s["b"]["r"][1:]), _byte(cloud_pct, *s["b"]["g"][1:]), _byte(rain, *s["b"]["b"][1:])])
    return Image.fromarray(a, "RGB"), Image.fromarray(b, "RGB")


def save(img, path):
    img.save(path, format="PNG", optimize=True)
