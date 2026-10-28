import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import encode  # noqa: E402
import sources  # noqa: E402


def test_regrid_orientations_and_wrap():
    lats = np.linspace(90, -90, 181)
    lons = np.arange(0, 360, 1.0)
    lon2, lat2 = np.meshgrid(lons, lats)
    field = lat2 * 1000 + np.where(lon2 > 180, lon2 - 360, lon2)  # value encodes position
    g = encode.regrid(field, lats, lons)
    # cell (row j, col i) holds lat*1000 + lon of its centre
    for j, i in [(0, 0), (128, 256), (255, 511), (64, 300)]:
        want = encode.T_LAT[j] * 1000 + encode.T_LON[i]
        assert abs(g[j, i] - want) < 600, (j, i, g[j, i], want)
    # same field given south-to-north and -180..180 gives the same result
    lons2 = np.arange(-180, 180, 1.0)
    lon2b, lat2b = np.meshgrid(lons2, lats[::-1])
    g2 = encode.regrid(lat2b * 1000 + lon2b, lats[::-1], lons2)
    assert np.nanmax(np.abs(g2[:, 1:-1] - g[:, 1:-1])) < 1e-6


def test_encode_ranges():
    z = np.zeros((encode.H, encode.W))
    a, b = encode.encode(z + 40, z - 40, z + 0, z + 1013, z + 50, z + 50)
    pa, pb = np.asarray(a), np.asarray(b)
    assert pa[0, 0].tolist() == [255, 0, 128]
    assert pb[0, 0, 0] == round((1013 - 950) / 110 * 255) and pb[0, 0, 2] == 255


def test_gfs_idx_ranges():
    idx = "\n".join(["1:0:d=2026102800:PRMSL:mean sea level:anl:", "2:100:d=2026102800:TMP:2 m above ground:anl:",
                     "3:250:d=2026102800:UGRD:10 m above ground:anl:", "4:400:d=2026102800:VGRD:10 m above ground:anl:", "5:520:d=2026102800:TCDC:entire atmosphere:anl:"])
    r = sources._gfs_ranges(idx)
    assert r[0] == (250, 399) and r[1] == (400, 519) and r[2] == (100, 249) and r[3] == (0, 99) and r[4] == (520, None)
    assert len(r) == 5  # PRATE is not in the analysis


def test_steps():
    assert sources.STEPS[0] == 0 and sources.STEPS[-1] == 240 and 120 in sources.STEPS and 126 in sources.STEPS
