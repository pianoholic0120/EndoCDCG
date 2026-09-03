#!/usr/bin/env python3
"""Export multi-method LODs for the Method compare section (VR-CAPS only).

Keep Ours fixed, align GT / COLMAP-native / COLMAP+Wei into the Ours frame
via camera-center best-fit, then canonicalize with the Ours bounding box.

Writes:
  docs/assets/points/methods/{scene_id}__{method}_{lod}.bin
  docs/assets/meshes/methods/{scene_id}__gt.ply
  docs/data/methods.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path("/home/arthur/EndoCDCG")
sys.path.insert(0, str(ROOT / "tools"))
from prepare_assets import (  # noqa: E402
    ARCHIVE,
    COMPARE_SCENES,
    LODS,
    MESHES,
    POINTS,
    align_gt_geometry,
    best_fit_transform,
    downsample,
    ensure_dirs,
    load_est_centers,
    simplify_o3d_mesh,
    write_gt_ply,
    write_pnts,
)

METHOD_POINTS = POINTS / "methods"
METHOD_MESHES = MESHES / "methods"


def resolve_sparse(root: Path, trial: str) -> Path | None:
    """Prefer a sparse model that actually has a points3D.ply."""
    cands = [
        root / trial / "sparse" / "0",
        root / trial / "dense" / "sparse" / "0",
    ]
    with_ply = [c for c in cands if (c / "points3D.ply").exists()]
    if with_ply:
        return with_ply[0]
    for c in cands:
        if (c / "points3D.bin").exists() or (c / "images.bin").exists() or (c / "images.txt").exists():
            return c
    return None


def ensure_points_ply(sparse: Path) -> Path | None:
    ply = sparse / "points3D.ply"
    if ply.exists():
        return ply
    bin_path = sparse / "points3D.bin"
    if not bin_path.exists():
        # Fallback: parse COLMAP text export if present.
        txt = sparse / "points3D.txt"
        if txt.exists():
            try:
                xyz, rgb = [], []
                for line in txt.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # COLMAP points3D.txt:
                    # POINT3D_ID X Y Z R G B ERROR [TRACK[]...]
                    parts = line.split()
                    if len(parts) < 7:
                        continue
                    xyz.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    rgb.append([int(parts[4]) / 255.0, int(parts[5]) / 255.0, int(parts[6]) / 255.0])
                if not xyz:
                    return None
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(np.asarray(xyz, dtype=np.float64))
                pcd.colors = o3d.utility.Vector3dVector(np.asarray(rgb, dtype=np.float64))
                o3d.io.write_point_cloud(str(ply), pcd)
                print(f"    wrote {ply} from txt ({len(xyz)} pts)", flush=True)
                return ply
            except Exception as e:
                print(f"    txt→ply failed: {e}", flush=True)
                return None
        return None
    try:
        import pycolmap

        rec = pycolmap.Reconstruction(str(sparse))
        xyz, rgb = [], []
        for p in rec.points3D.values():
            xyz.append(p.xyz)
            rgb.append(np.asarray(p.color, dtype=np.float64) / 255.0)
        if not xyz:
            return None
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(np.asarray(xyz))
        pcd.colors = o3d.utility.Vector3dVector(np.asarray(rgb))
        o3d.io.write_point_cloud(str(ply), pcd)
        print(f"    wrote {ply} from bin ({len(xyz)} pts)", flush=True)
        return ply
    except Exception as e:
        print(f"    bin→ply failed: {e}", flush=True)
        # If pycolmap is missing, still try the text export.
        txt = sparse / "points3D.txt"
        if txt.exists():
            try:
                xyz, rgb = [], []
                for line in txt.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) < 7:
                        continue
                    xyz.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    rgb.append([int(parts[4]) / 255.0, int(parts[5]) / 255.0, int(parts[6]) / 255.0])
                if not xyz:
                    return None
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(np.asarray(xyz, dtype=np.float64))
                pcd.colors = o3d.utility.Vector3dVector(np.asarray(rgb, dtype=np.float64))
                o3d.io.write_point_cloud(str(ply), pcd)
                print(f"    wrote {ply} from txt ({len(xyz)} pts)", flush=True)
                return ply
            except Exception as e2:
                print(f"    txt→ply failed: {e2}", flush=True)
        return None


def resolve_ply(sparse: Path) -> Path | None:
    return ensure_points_ply(sparse)


def scene_root(sc: dict) -> Path:
    p = Path(sc["ply"]).resolve()
    for up in [p.parents[i] for i in range(1, min(8, len(p.parents)))]:
        if (up / "original_images").is_dir() or (up / "camera_info.json").is_file():
            return up
    return p.parents[4]


def canonicalize_xyz(xyz: np.ndarray, center: np.ndarray, scale: float) -> np.ndarray:
    return (xyz - center) / scale


def frame_stats(xyz: np.ndarray) -> tuple[np.ndarray, float]:
    mn, mx = xyz.min(0), xyz.max(0)
    center = 0.5 * (mn + mx)
    scale = float(np.max(0.5 * np.maximum(mx - mn, 1e-8)))
    return center, scale


def align_method_to_ours(
    sc: dict, xyz: np.ndarray, sparse: Path
) -> np.ndarray:
    """Map another COLMAP reconstruction into the fixed Ours frame."""
    source = load_est_centers(sparse)
    target = load_est_centers(Path(sc["sparse"]))
    ids = sorted(set(source) & set(target))
    if len(ids) < 4:
        print(f"  pose match too few for method→Ours: {len(ids)}", flush=True)
        return xyz
    a = np.stack([source[i] for i in ids])
    b = np.stack([target[i] for i in ids])
    source_scale = float(np.linalg.norm(a - a.mean(0), axis=1).mean())
    target_scale = float(np.linalg.norm(b - b.mean(0), axis=1).mean())
    ratio = target_scale / max(source_scale, 1e-12)
    a_scaled = a * ratio
    rotation, translation = best_fit_transform(a_scaled, b)
    err = float(np.linalg.norm(a_scaled @ rotation.T + translation - b, axis=1).mean())
    print(
        f"  method→Ours {len(ids)} cams, center err {err:.4f}, scale {ratio:.4f}",
        flush=True,
    )
    return (xyz * ratio) @ rotation.T + translation


def export_points_method(
    scene_id: str,
    method_key: str,
    label: str,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    center: np.ndarray,
    scale: float,
) -> dict:
    xyz_c = canonicalize_xyz(xyz, center, scale)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz_c)
    if rgb is not None and len(rgb) == len(xyz):
        pcd.colors = o3d.utility.Vector3dVector(np.clip(rgb, 0, 1))
    else:
        col = np.tile(np.array([[0.75, 0.72, 0.68]]), (len(xyz_c), 1))
        pcd.colors = o3d.utility.Vector3dVector(col)

    entry: dict = {"key": method_key, "label": label, "kind": "points", "lods": {}}
    for lod, n in LODS.items():
        ds = downsample(pcd, n)
        path = METHOD_POINTS / f"{scene_id}__{method_key}_{lod}.bin"
        meta = write_pnts(ds, path)
        entry["lods"][lod] = {
            "url": f"assets/points/methods/{path.name}?v=ours-frame-20260903",
            **meta,
        }
        print(f"    {method_key}/{lod}: {meta['count']} pts", flush=True)
    return entry


def export_gt_mesh_method(
    scene_id: str, mesh: o3d.geometry.TriangleMesh, center: np.ndarray, scale: float
) -> dict:
    verts = np.asarray(mesh.vertices)
    mesh.vertices = o3d.utility.Vector3dVector(canonicalize_xyz(verts, center, scale))
    mesh.compute_vertex_normals()
    mesh = simplify_o3d_mesh(mesh)
    path = METHOD_MESHES / f"{scene_id}__gt.ply"
    gmeta = write_gt_ply(mesh, path)
    return {
        "key": "gt",
        "label": "Ground truth",
        "kind": "mesh",
        "url": f"assets/meshes/methods/{gmeta['file']}?v=ours-frame-20260903",
        **{k: v for k, v in gmeta.items() if k != "file"},
        "file": gmeta["file"],
    }


def process_scene(sc: dict) -> dict | None:
    print(f"=== {sc['id']} ===", flush=True)
    ours_ply = Path(sc["ply"])
    if not ours_ply.exists():
        print("  missing Ours ply", flush=True)
        return None

    aligned_gt = align_gt_geometry(sc)
    if aligned_gt is None:
        print("  no GT — skip", flush=True)
        return None

    methods: list[dict] = []

    # Ours defines both the world frame and the canonical viewer extent.
    ours_pcd = o3d.io.read_point_cloud(str(ours_ply))
    ours_xyz = np.asarray(ours_pcd.points)
    ours_rgb = np.asarray(ours_pcd.colors) if ours_pcd.has_colors() else None
    center, scale = frame_stats(ours_xyz)
    methods.append(
        export_points_method(
            sc["id"], "ours", "Ours (EndoCDCG)", ours_xyz, ours_rgb, center, scale
        )
    )

    # GT has already been mapped GT→Ours by camera-center alignment.
    kind, geom = aligned_gt
    if kind == "mesh":
        mesh = o3d.geometry.TriangleMesh(geom)  # type: ignore[arg-type]
        methods.append(export_gt_mesh_method(sc["id"], mesh, center, scale))
    else:
        gxyz = np.asarray(geom.points)  # type: ignore[attr-defined]
        grgb = np.asarray(geom.colors) if geom.has_colors() else None  # type: ignore[union-attr]
        methods.append(
            export_points_method(sc["id"], "gt", "Ground truth", gxyz, grgb, center, scale)
        )

    root = scene_root(sc)
    for trial, key, label in (
        ("colmap_native", "colmap_native", "COLMAP (native)"),
        ("colmap_wei_enhance", "colmap_enhance", "COLMAP + Wei enhance"),
    ):
        sparse = resolve_sparse(root, trial)
        if sparse is None:
            print(f"  skip {key}: missing {trial}", flush=True)
            continue
        ply = resolve_ply(sparse)
        if ply is None:
            print(f"  skip {key}: no points3D.ply", flush=True)
            continue
        pcd = o3d.io.read_point_cloud(str(ply))
        if pcd.is_empty():
            print(f"  skip {key}: empty cloud", flush=True)
            continue
        xyz = np.asarray(pcd.points)
        rgb = np.asarray(pcd.colors) if pcd.has_colors() else None
        print(f"  {key}: {len(xyz)} pts from {ply}", flush=True)
        xyz = align_method_to_ours(sc, xyz, sparse)
        methods.append(
            export_points_method(sc["id"], key, label, xyz, rgb, center, scale)
        )

    keys = {m["key"] for m in methods}
    default_left = "colmap_enhance" if "colmap_enhance" in keys else (
        "colmap_native" if "colmap_native" in keys else "ours"
    )
    default_right = "ours" if "ours" in keys else next(iter(keys))
    return {
        "id": sc["id"],
        "label": sc["label"],
        "dataset": sc["dataset"],
        "preview": f"assets/previews/{sc['id']}.webp",
        "methods": {m["key"]: m for m in methods},
        "default_left": default_left,
        "default_right": default_right,
    }


METHOD_COMPARE_SCENES = [sc for sc in COMPARE_SCENES if sc.get("dataset") == "VR-CAPS"]


def main() -> None:
    ensure_dirs()
    METHOD_POINTS.mkdir(parents=True, exist_ok=True)
    METHOD_MESHES.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    keep_ids = {sc["id"] for sc in METHOD_COMPARE_SCENES}
    for folder in (METHOD_POINTS, METHOD_MESHES):
        for p in folder.glob("*"):
            sid = p.name.split("__", 1)[0]
            if sid not in keep_ids:
                p.unlink()
                print(f"  removed stale {p.name}", flush=True)

    manifest = []
    for sc in METHOD_COMPARE_SCENES:
        entry = process_scene(sc)
        if entry and len(entry["methods"]) >= 2:
            manifest.append(entry)
        elif entry:
            print(f"  skip {sc['id']}: need ≥2 methods", flush=True)

    out = ROOT / "docs" / "data" / "methods.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out} ({len(manifest)} VR-CAPS scenes)", flush=True)


if __name__ == "__main__":
    main()
