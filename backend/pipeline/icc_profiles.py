"""
icc_profiles.py — ICC プロファイル生成・管理
"""

import io
import struct
import numpy as np
from PIL import ImageCms
from PIL.ImageCms import ImageCmsProfile, Intent

_profile_cache: dict[str, bytes] = {}

# Primaries (CIE 1931 chromaticity)
_SRGB_PRIMARIES = (0.64, 0.33, 0.30, 0.60, 0.15, 0.06)
_ADOBE_PRIMARIES = (0.64, 0.33, 0.21, 0.71, 0.15, 0.06)
_P3_PRIMARIES = (0.68, 0.32, 0.265, 0.69, 0.15, 0.06)
_ADOBE_GAMMA = 2.19921875
_P3_GAMMA = 2.2


def _s15f16(val):
    return struct.pack('>i', int(round(val * 65536)))


def _generate_icc_profile(primaries, gamma, description):
    """Build minimal ICC v2 RGB profile binary."""
    wp_X, wp_Y, wp_Z = 0.9505, 1.0000, 1.0890
    rx, ry, gx, gy, bx, by = primaries

    def chr_to_xyz(cx, cy):
        return cx / cy, 1.0, (1.0 - cx - cy) / cy

    rX, rY, rZ = chr_to_xyz(rx, ry)
    gX, gY, gZ = chr_to_xyz(gx, gy)
    bX, bY, bZ = chr_to_xyz(bx, by)

    M = np.array([[rX, gX, bX], [rY, gY, bY], [rZ, gZ, bZ]])
    S = np.linalg.solve(M, np.array([wp_X, wp_Y, wp_Z]))
    M_s = M * S[np.newaxis, :]

    tags = {}

    # desc
    db = description.encode('ascii', errors='replace')
    d = b'desc' + b'\x00' * 4 + struct.pack('>I', len(db) + 1) + db + b'\x00'
    d += b'\x00' * ((4 - len(d) % 4) % 4)
    d += struct.pack('>I', 0) + struct.pack('>I', 0)
    d += struct.pack('>H', 0) + struct.pack('>B', 0) + b'\x00' * 67
    tags[b'desc'] = d

    # wtpt
    tags[b'wtpt'] = b'XYZ ' + b'\x00' * 4 + _s15f16(wp_X) + _s15f16(wp_Y) + _s15f16(wp_Z)

    # rXYZ, gXYZ, bXYZ
    for sig, ci in [(b'rXYZ', 0), (b'gXYZ', 1), (b'bXYZ', 2)]:
        tags[sig] = b'XYZ ' + b'\x00' * 4 + _s15f16(M_s[0, ci]) + _s15f16(M_s[1, ci]) + _s15f16(M_s[2, ci])

    # TRC
    trc = b'curv' + b'\x00' * 4 + struct.pack('>I', 1) + struct.pack('>H', int(round(gamma * 256)))
    trc += b'\x00' * ((4 - len(trc) % 4) % 4)
    tags[b'rTRC'] = trc
    tags[b'gTRC'] = trc
    tags[b'bTRC'] = trc

    # cprt
    ct = b'text' + b'\x00' * 4 + b'Public Domain\x00'
    ct += b'\x00' * ((4 - len(ct) % 4) % 4)
    tags[b'cprt'] = ct

    num_tags = len(tags)
    header_size = 128
    tag_table_size = 4 + num_tags * 12
    data_offset = header_size + tag_table_size
    data_offset += (4 - data_offset % 4) % 4

    tag_entries = []
    blob = b''
    off = data_offset
    for sig, data in tags.items():
        tag_entries.append((sig, off, len(data)))
        blob += data
        pad = (4 - len(data) % 4) % 4
        blob += b'\x00' * pad
        off += len(data) + pad

    profile_size = data_offset + len(blob)

    # Header
    h = struct.pack('>I', profile_size) + b'NONE'
    h += struct.pack('>I', 0x02100000) + b'mntr' + b'RGB ' + b'XYZ '
    h += b'\x00' * 12 + b'acsp' + b'APPL'
    h += struct.pack('>I', 0) + b'\x00' * 4 + b'\x00' * 4 + b'\x00' * 8
    h += struct.pack('>I', 0)
    h += _s15f16(0.9642) + _s15f16(1.0) + _s15f16(0.8249)
    h += b'\x00' * 4 + b'\x00' * 16
    h += b'\x00' * (128 - len(h))

    tt = struct.pack('>I', num_tags)
    for sig, o, s in tag_entries:
        tt += sig + struct.pack('>I', o) + struct.pack('>I', s)
    tt += b'\x00' * (data_offset - header_size - len(tt))

    return h + tt + blob


def get_icc_profile(color_space: str) -> bytes:
    """指定色空間のICCプロファイルバイトを返す。"""
    if color_space in _profile_cache:
        return _profile_cache[color_space]

    if color_space == "srgb":
        p = ImageCms.createProfile("sRGB")
        data = ImageCmsProfile(p).tobytes()
    elif color_space == "adobe_rgb":
        data = _generate_icc_profile(_ADOBE_PRIMARIES, _ADOBE_GAMMA, "Adobe RGB (1998)")
    elif color_space == "display_p3":
        data = _generate_icc_profile(_P3_PRIMARIES, _P3_GAMMA, "Display P3")
    else:
        raise ValueError(f"Unknown color space: {color_space}")

    _profile_cache[color_space] = data
    return data
