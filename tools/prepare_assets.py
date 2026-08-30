#!/usr/bin/env python3
"""Convert existing colmap_mast3r PLYs and GT meshes into web LODs. No SfM rerun.

Copies processed files into this repo so GitHub Pages does not depend on
EndoMetric_output remaining on disk.
"""

from __future__ import annotations

import itertools
import json
import re
import shutil
import struct
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image

try:
    import pycolmap
except ImportError:
    pycolmap = None

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
        "sparse": SRC / "C3VD/trans_t4_a/colmap_mast3r/dense/sparse/0",
        "gt_pose": SRC / "C3VD/trans_t4_a_results/GT/pose.txt",
        "pose_kind": "c3vd",
        "thumb": SRC / "C3VD/trans_t4_a/original_images/0000.png",
    },
    {
        "id": "c3vd_sigmoid_t1_a",
        "label": "C3VDv2 · sigmoid t1-a",
        "dataset": "C3VD",
        "modes": ["compare"],
        "ply": SRC / "C3VD/sigmoid_t1_a/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "C3VD/sigmoid_t1_a_results/GT/coverage_mesh_cropped.obj",
        "sparse": SRC / "C3VD/sigmoid_t1_a/colmap_mast3r/dense/sparse/0",
        "gt_pose": SRC / "C3VD/sigmoid_t1_a_results/GT/pose.txt",
        "pose_kind": "c3vd",
        "thumb": SRC / "C3VD/sigmoid_t1_a/original_images/0000.png",
    },
    {
        "id": "vrcaps_colon_17",
        "label": "VR-CAPS · colon GI_2_17",
        "dataset": "VR-CAPS",
        "modes": ["browse", "compare"],
        "ply": SRC / "VR_CAPS/colon_GI_2_17/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "VR_CAPS/colon_GI_2_17_results/GT/evaluated_gt_faces_visible_flip.ply",
        "sparse": SRC / "VR_CAPS/colon_GI_2_17/colmap_mast3r/dense/sparse/0",
        "gt_pose": SRC / "VR_CAPS/colon_GI_2_17_results/GT/images.txt",
        "pose_kind": "colmap_images_txt",
        "thumb": None,
    },
    {
        "id": "vrcaps_stomach_5",
        "label": "VR-CAPS · stomach GI_2_5",
        "dataset": "VR-CAPS",
        "modes": ["compare"],
        "ply": SRC / "VR_CAPS/stomach_GI_2_5/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / "VR_CAPS/stomach_GI_2_5_results/GT/evaluated_gt_faces_visible_flip.ply",
        "sparse": SRC / "VR_CAPS/stomach_GI_2_5/colmap_mast3r/dense/sparse/0",
        "gt_pose": SRC / "VR_CAPS/stomach_GI_2_5_results/GT/images.txt",
        "pose_kind": "colmap_images_txt",
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


def qvec_to_rotmat(q: np.ndarray) -> np.ndarray:
    qw, qx, qy, qz = q
    return np.array(
        [
            [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qz * qw, 2 * qx * qz + 2 * qy * qw],
            [2 * qx * qy + 2 * qz * qw, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qx * qw],
            [2 * qx * qz - 2 * qy * qw, 2 * qy * qz + 2 * qx * qw, 1 - 2 * qx * qx - 2 * qy * qy],
        ]
    )


def cam_center_from_w2c(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    return -R.T @ t


def frame_idx(name: str) -> int:
    nums = re.findall(r"\d+", Path(name).stem)
    return int(nums[-1]) if nums else -1


def estimate_similarity_transform(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    assert A.shape == B.shape
    n = A.shape[0]
    centroid_A = A.mean(axis=0)
    centroid_B = B.mean(axis=0)
    AA = A - centroid_A
    BB = B - centroid_B
    H = AA.T @ BB / n
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    var_A = (AA ** 2).sum() / n
    scale = np.sum(S) / max(var_A, 1e-12)
    t = centroid_B - scale * R @ centroid_A
    T = np.eye(4)
    T[:3, :3] = scale * R
    T[:3, 3] = t
    return T


def load_c3vd_centers(path: Path) -> dict[int, np.ndarray]:
    """C3VD pose.txt is camera-to-world; translations are millimetres."""
    out = {}
    for i, line in enumerate(path.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        data = np.fromstring(line, sep=",")
        if data.size != 16:
            continue
        pose = data.reshape(4, 4).T
        out[i] = pose[:3, 3]
    return out


def load_images_txt_centers(path: Path) -> dict[int, np.ndarray]:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 10 or parts[0] in ("IMAGE_ID",):
            continue
        if not parts[0].replace(".", "", 1).isdigit() and not parts[0].isdigit():
            continue
        try:
            q = np.array(list(map(float, parts[1:5])))
            t = np.array(list(map(float, parts[5:8])))
            name = parts[9] if len(parts) > 9 else parts[-1]
        except ValueError:
            continue
        R = qvec_to_rotmat(q)
        out[frame_idx(name)] = cam_center_from_w2c(R, t)
    return out


def load_colmap_centers(sparse: Path) -> dict[int, np.ndarray]:
    rec = pycolmap.Reconstruction(str(sparse))
    out = {}
    for image in rec.images.values():
        cfw = image.cam_from_world() if callable(getattr(image, "cam_from_world", None)) else image.cam_from_world
        wfc = cfw.inverse()
        mat = wfc.matrix()
        out[frame_idx(image.name)] = np.asarray(mat[:3, 3], dtype=np.float64)
    return out


def pose_sim3_gt_to_est(sc: dict) -> np.ndarray | None:
    if pycolmap is None or not sc.get("sparse") or not sc.get("gt_pose"):
        return None
    sparse, gt_pose = Path(sc["sparse"]), Path(sc["gt_pose"])
    if not sparse.exists() or not gt_pose.exists():
        return None
    est = load_colmap_centers(sparse)
    if sc.get("pose_kind") == "c3vd":
        gt = load_c3vd_centers(gt_pose)
    else:
        gt = load_images_txt_centers(gt_pose)
    ids = sorted(set(est) & set(gt))
    if len(ids) < 8:
        print(f"  pose match too few: {len(ids)}", flush=True)
        return None
    A = np.stack([gt[i] for i in ids])  # GT centers
    B = np.stack([est[i] for i in ids])  # EST centers
    T = estimate_similarity_transform(A, B)  # GT -> EST
    err = np.linalg.norm((T[:3, :3] @ A.T).T + T[:3, 3] - B, axis=1).mean()
    print(f"  pose Sim3 GT->EST: {len(ids)} cams, mean center err {err:.4f}", flush=True)
    return T


def pca_inits(src: np.ndarray, dst: np.ndarray) -> list[np.ndarray]:
    def axes(pts):
        c = pts.mean(0)
        _, _, vh = np.linalg.svd(pts - c, full_matrices=False)
        return c, vh

    cs, As = axes(src)
    cd, Ad = axes(dst)
    ss = np.sqrt(((src - cs) ** 2).sum() / max(len(src), 1))
    sd = np.sqrt(((dst - cd) ** 2).sum() / max(len(dst), 1))
    scale = sd / max(ss, 1e-12)
    inits = []
    for signs in itertools.product([-1.0, 1.0], repeat=3):
        A = np.diag(signs) @ As
        R = Ad.T @ A
        if np.linalg.det(R) < 0:
            R[:, 2] *= -1
        T = np.eye(4)
        T[:3, :3] = scale * R
        T[:3, 3] = cd - scale * R @ cs
        inits.append(T)
    return inits


def icp_gt_to_points(mesh: o3d.geometry.TriangleMesh, pcd: o3d.geometry.PointCloud, T0: np.ndarray | None) -> np.ndarray:
    src_m = mesh.sample_points_uniformly(number_of_points=40000)
    dst = downsample(pcd, 40000)
    src_pts = np.asarray(src_m.points)
    dst_pts = np.asarray(dst.points)
    extent = float(np.linalg.norm(dst.get_axis_aligned_bounding_box().get_extent()))
    thresh = max(extent * 0.08, 1e-3)
    candidates = [T0] if T0 is not None else []
    candidates.extend(pca_inits(src_pts, dst_pts))
    best_t, best_fit = None, -1.0
    est = o3d.pipelines.registration.TransformationEstimationPointToPoint(with_scaling=True)
    crit = o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=80)
    for T in candidates:
        if T is None:
            continue
        reg = o3d.pipelines.registration.registration_icp(src_m, dst, thresh, T, est, crit)
        if reg.fitness > best_fit:
            best_fit, best_t = reg.fitness, reg.transformation
    if best_t is None:
        return np.eye(4)
    # finer
    thresh2 = max(extent * 0.03, 1e-3)
    reg = o3d.pipelines.registration.registration_icp(src_m, dst, thresh2, best_t, est, crit)
    print(f"  ICP fitness {reg.fitness:.3f} rmse {reg.inlier_rmse:.4f}", flush=True)
    return np.asarray(reg.transformation)


def align_gt_mesh(sc: dict, mesh: o3d.geometry.TriangleMesh, pcd: o3d.geometry.PointCloud) -> o3d.geometry.TriangleMesh:
    T_pose = pose_sim3_gt_to_est(sc)
    T = icp_gt_to_points(mesh, pcd, T_pose)
    mesh.transform(T)
    return mesh


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
            mesh = align_gt_mesh(sc, mesh, pcd)
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
