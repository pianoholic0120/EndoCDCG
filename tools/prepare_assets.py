#!/usr/bin/env python3
"""Convert existing colmap_mast3r PLYs and GT meshes into web LODs. No SfM rerun.

Copies processed files into this repo so GitHub Pages does not depend on
EndoMetric_output remaining on disk.
"""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image

ROOT = Path("/home/arthur/EndoCDCG")
SRC = Path("/home/arthur/EndoMetric_output")
OUT = ROOT / "docs" / "assets"
PREVIEW = OUT / "previews"
POINTS = OUT / "points"
MESHES = OUT / "meshes"
ARCHIVE = ROOT / "source_archive"

SCENES = [
    {
        "id": "c3vd_cecum_t2_a",
        "label": "C3VDv2 · cecum t2-a",
        "dataset": "C3VD",
        "modes": ["browse"],
        "ply": SRC / "C3VD/cecum_t2_a/colmap_mast3r/dense/sparse/0/points3D.ply",
        "thumb": SRC / "C3VD/cecum_t2_a/original_images/0000.png",
    },
    {
        "id": "c3vd_trans_t4_a",
        "label": "C3VDv2 · transverse t4-a",
        "dataset": "C3VD",
        "modes": ["browse", "compare"],
        "ply": SRC / "C3VD/trans_t4_a/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "C3VD/trans_t4_a_results/GT/coverage_mesh_cropped.obj",
        "thumb": SRC / "C3VD/trans_t4_a/original_images/0000.png",
    },
    {
        "id": "c3vd_sigmoid_t1_a",
        "label": "C3VDv2 · sigmoid t1-a",
        "dataset": "C3VD",
        "modes": ["compare"],
        "ply": SRC / "C3VD/sigmoid_t1_a/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "C3VD/sigmoid_t1_a_results/GT/coverage_mesh_cropped.obj",
        "thumb": SRC / "C3VD/sigmoid_t1_a/original_images/0000.png",
    },
    {
        "id": "vrcaps_colon_17",
        "label": "VR-CAPS · colon GI_2_17",
        "dataset": "VR-CAPS",
        "modes": ["browse", "compare"],
        "ply": SRC / "VR_CAPS/colon_GI_2_17/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "VR_CAPS/colon_GI_2_17_results/GT/evaluated_gt_faces_visible_flip.ply",
        "thumb": None,
    },
    {
        "id": "vrcaps_stomach_5",
        "label": "VR-CAPS · stomach GI_2_5",
        "dataset": "VR-CAPS",
        "modes": ["compare"],
        "ply": SRC / "VR_CAPS/stomach_GI_2_5/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "VR_CAPS/stomach_GI_2_5_results/GT/evaluated_gt_faces_visible_flip.ply",
        "thumb": None,
    },
]

LODS = {
    "desktop": 280_000,
    "mobile": 90_000,
}


def ensure_dirs() -> None:
    for p in (PREVIEW, POINTS, MESHES, ARCHIVE):
        p.mkdir(parents=True, exist_ok=True)


def archive_copy(src: Path, dest_name: str) -> None:
    dest = ARCHIVE / dest_name
    if src.exists() and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"  archived {src} -> {dest}", flush=True)


def save_thumb(src: Path | None, dest: Path, pcd: o3d.geometry.PointCloud) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src and src.exists():
        im = Image.open(src).convert("RGB")
        im.thumbnail((640, 480))
        im.save(dest, "WEBP", quality=78, method=4)
        return
    xyz = np.asarray(pcd.points)
    rgb = np.asarray(pcd.colors) if pcd.has_colors() else np.full((len(xyz), 3), 0.7)
    if len(xyz) > 80_000:
        idx = np.random.default_rng(1).choice(len(xyz), 80_000, replace=False)
        xyz, rgb = xyz[idx], rgb[idx] if len(rgb) == len(pcd.points) else np.full((len(idx), 3), 0.7)
    mn, mx = xyz.min(axis=0), xyz.max(axis=0)
    span = np.maximum(mx - mn, 1e-8)
    u = (xyz[:, 0] - mn[0]) / span[0]
    v = 1.0 - (xyz[:, 1] - mn[1]) / span[1]
    w, h = 640, 480
    img = np.zeros((h, w, 3), dtype=np.uint8)
    xs = np.clip((u * (w - 1)).astype(int), 0, w - 1)
    ys = np.clip((v * (h - 1)).astype(int), 0, h - 1)
    cols = np.clip(rgb * 255, 0, 255).astype(np.uint8)
    img[ys, xs] = cols
    Image.fromarray(img).save(dest, "WEBP", quality=78, method=4)


def downsample(pcd: o3d.geometry.PointCloud, n: int) -> o3d.geometry.PointCloud:
    xyz = np.asarray(pcd.points)
    if len(xyz) <= n:
        return pcd
    rng = np.random.default_rng(0)
    idx = rng.choice(len(xyz), n, replace=False)
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(xyz[idx])
    if pcd.has_colors() and len(pcd.colors) == len(xyz):
        out.colors = o3d.utility.Vector3dVector(np.asarray(pcd.colors)[idx])
    return out


def write_pnts(pcd: o3d.geometry.PointCloud, path: Path) -> dict:
    xyz = np.asarray(pcd.points, dtype=np.float64)
    rgb = np.asarray(pcd.colors, dtype=np.float64) if pcd.has_colors() else np.full((len(xyz), 3), 0.75)
    if rgb.ndim != 2 or len(rgb) != len(xyz):
        rgb = np.full((len(xyz), 3), 0.75)
    mn = xyz.min(axis=0)
    mx = xyz.max(axis=0)
    span = np.maximum(mx - mn, 1e-8)
    q = np.clip(((xyz - mn) / span) * 65535.0, 0, 65535).astype(np.uint16)
    c = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    n = len(xyz)
    header = struct.pack("<4sI6f", b"ECD1", n, *mn.tolist(), *mx.tolist())
    body = np.empty((n, 5), dtype=np.uint16)
    body[:, 0:3] = q
    body[:, 3] = c[:, 0].astype(np.uint16) | (c[:, 1].astype(np.uint16) << 8)
    body[:, 4] = c[:, 2].astype(np.uint16)
    path.write_bytes(header + body.tobytes())
    return {"count": n, "bytes": path.stat().st_size, "min": mn.tolist(), "max": mx.tolist()}


def simplify_mesh(path: Path, target_tris: int = 70000) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=True)
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.compute_vertex_normals()
    n = len(mesh.triangles)
    if n > target_tris:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_tris)
        mesh.compute_vertex_normals()
    if not mesh.has_vertex_colors():
        col = np.tile(np.array([[0.82, 0.62, 0.52]]), (len(mesh.vertices), 1))
        mesh.vertex_colors = o3d.utility.Vector3dVector(col)
    return mesh


def write_glb(mesh: o3d.geometry.TriangleMesh, path: Path) -> dict:
    ok = o3d.io.write_triangle_mesh(str(path), mesh, write_vertex_colors=True)
    if not ok or not path.exists():
        ply = path.with_suffix(".ply")
        o3d.io.write_triangle_mesh(str(ply), mesh, write_vertex_colors=True)
        return {"format": "ply", "file": ply.name, "tris": int(len(mesh.triangles)), "bytes": ply.stat().st_size}
    return {"format": "glb", "file": path.name, "tris": int(len(mesh.triangles)), "bytes": path.stat().st_size}


def main() -> None:
    ensure_dirs()
    manifest = []
    for sc in SCENES:
        print(f"=== {sc['id']} ===", flush=True)
        archive_copy(sc["ply"], f"{sc['id']}_points3D.ply")
        if sc.get("gt"):
            archive_copy(sc["gt"], f"{sc['id']}_gt{sc['gt'].suffix}")
        pcd = o3d.io.read_point_cloud(str(sc["ply"]))
        print(f"  points {len(pcd.points)}", flush=True)
        entry = {
            "id": sc["id"],
            "label": sc["label"],
            "dataset": sc["dataset"],
            "modes": sc["modes"],
            "preview": f"assets/previews/{sc['id']}.webp",
            "points": {},
        }
        save_thumb(sc.get("thumb"), PREVIEW / f"{sc['id']}.webp", pcd)
        for lod, n in LODS.items():
            ds = downsample(pcd, n)
            meta = write_pnts(ds, POINTS / f"{sc['id']}_{lod}.bin")
            entry["points"][lod] = {
                "url": f"assets/points/{sc['id']}_{lod}.bin",
                **meta,
            }
            print(f"  lod {lod}: {meta['count']} pts, {meta['bytes']/1024:.0f} KB", flush=True)
        if "compare" in sc["modes"] and sc.get("gt"):
            mesh = simplify_mesh(sc["gt"])
            gmeta = write_glb(mesh, MESHES / f"{sc['id']}_gt.glb")
            entry["gt"] = {"url": f"assets/meshes/{gmeta['file']}", **gmeta}
            print(f"  gt {gmeta}", flush=True)
        manifest.append(entry)
    dest = ROOT / "docs" / "data" / "scenes.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2))
    print("wrote", dest)


if __name__ == "__main__":
    main()
