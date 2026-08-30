#!/usr/bin/env python3
"""Convert existing colmap_mast3r PLYs and GT meshes into web LODs. No SfM rerun.

Copies processed files into this repo so GitHub Pages does not depend on
EndoMetric_output remaining on disk.
"""

from __future__ import annotations

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

def _c3vd(scene_id: str, folder: str, title: str) -> dict:
    return {
        "id": scene_id,
        "label": title,
        "dataset": "C3VD",
        "ply": SRC / f"C3VD/{folder}/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": SRC / f"C3VD/{folder}_results/GT/coverage_mesh_cropped.obj",
        "sparse": SRC / f"C3VD/{folder}/colmap_mast3r/dense/sparse/0",
        "gt_pose": SRC / f"C3VD/{folder}_results/GT/pose.txt",
        "pose_kind": "c3vd",
        "thumb": SRC / f"C3VD/{folder}/original_images/0000.png",
    }


def _vrcaps(scene_id: str, folder: str, title: str) -> dict:
    results_gt = SRC / f"VR_CAPS/{folder}_results/GT"
    gt = results_gt / "evaluated_gt_faces_visible_flip.ply"
    if not gt.exists():
        gt = results_gt / "gt_input.ply"
    thumb = None
    for cand in (
        SRC / f"VR_CAPS/{folder}/original_images/0000.jpg",
        SRC / f"VR_CAPS/{folder}/original_images/0000.png",
    ):
        if cand.exists():
            thumb = cand
            break
    return {
        "id": scene_id,
        "label": title,
        "dataset": "VR-CAPS",
        "ply": SRC / f"VR_CAPS/{folder}/colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": gt if gt.exists() else None,
        "sparse": SRC / f"VR_CAPS/{folder}/colmap_mast3r/dense/sparse/0",
        "gt_pose": results_gt / "images.txt" if (results_gt / "images.txt").exists() else None,
        "pose_kind": "colmap_images_txt",
        "thumb": thumb,
    }


def _endomapper(scene_id: str, seq: str, title: str) -> dict:
    root = SRC / f"Endomapper/Simulated_Sequences/{seq}"
    thumb = root / "original_images/image_0000.png"
    return {
        "id": scene_id,
        "label": title,
        "dataset": "EndoMapper",
        "ply": root / "colmap_mast3r/dense/sparse/0/points3D.ply",
        "gt": None,
        "thumb": thumb if thumb.exists() else None,
    }


# Compare viewer: GT when available. EndoMapper is a separate points-only section.
COMPARE_SCENES = [
    _c3vd("c3vd_cecum_t1_b", "cecum_t1_b", "C3VDv2 · cecum t1-b"),
    _c3vd("c3vd_cecum_t2_a", "cecum_t2_a", "C3VDv2 · cecum t2-a"),
    _c3vd("c3vd_cecum_t2_b", "cecum_t2_b", "C3VDv2 · cecum t2-b"),
    _c3vd("c3vd_trans_t4_a", "trans_t4_a", "C3VDv2 · transverse t4-a"),
    _c3vd("c3vd_sigmoid_t1_a", "sigmoid_t1_a", "C3VDv2 · sigmoid t1-a"),
    _c3vd("c3vd_sigmoid_t3_b", "sigmoid_t3_b", "C3VDv2 · sigmoid t3-b"),
    _vrcaps("vrcaps_colon_17", "colon_GI_2_17", "VR-CAPS · colon GI_2_17"),
    _vrcaps("vrcaps_colon_18", "colon_GI_2_18", "VR-CAPS · colon GI_2_18"),
    _vrcaps("vrcaps_stomach_5", "stomach_GI_2_5", "VR-CAPS · stomach GI_2_5"),
    _vrcaps("vrcaps_stomach_7", "stomach_GI_2_7", "VR-CAPS · stomach GI_2_7"),
]

ENDOMAPPER_SCENES = [
    _endomapper("endomapper_seq_0", "Seq_0", "EndoMapper · Seq 0"),
    _endomapper("endomapper_seq_1", "Seq_1", "EndoMapper · Seq 1"),
    _endomapper("endomapper_seq_2", "Seq_2", "EndoMapper · Seq 2"),
]

# Back-compat alias
SCENES = COMPARE_SCENES

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


def frame_id_from_name(name: str) -> int | None:
    """Same as Endoscopic_3D_Reconstruction/utils/align_mesh.py."""
    try:
        return int(Path(name).name.split(".")[0])
    except (ValueError, IndexError):
        return None


def frame_idx(name: str) -> int:
    fid = frame_id_from_name(name)
    if fid is not None:
        return fid
    nums = re.findall(r"\d+", Path(name).stem)
    return int(nums[-1]) if nums else -1


def estimate_similarity_transform(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Umeyama Sim(3); identical to align_mesh.py."""
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


def best_fit_transform(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rigid best-fit (R, t) mapping A onto B. Same as align_to_gt_VR_CAPS.py."""
    assert A.shape == B.shape
    m = A.shape[1]
    centroid_A = np.mean(A, axis=0)
    centroid_B = np.mean(B, axis=0)
    AA = A - centroid_A
    BB = B - centroid_B
    H = AA.T @ BB
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[m - 1, :] *= -1
        R = Vt.T @ U.T
    t = centroid_B - R @ centroid_A
    return R, t


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


def load_est_centers(sparse: Path) -> dict[int, np.ndarray]:
    txt = load_colmap_centers_from_images_txt(sparse)
    if txt:
        return txt
    if pycolmap is None:
        return {}
    rec = pycolmap.Reconstruction(str(sparse))
    out = {}
    for image in rec.images.values():
        cfw = image.cam_from_world() if callable(getattr(image, "cam_from_world", None)) else image.cam_from_world
        wfc = cfw.inverse()
        mat = wfc.matrix()
        fid = frame_idx(image.name)
        if fid >= 0:
            out[fid] = np.asarray(mat[:3, 3], dtype=np.float64)
    return out


def load_colmap_centers_from_images_txt(sparse: Path) -> dict[int, np.ndarray]:
    """COLMAP camera centers from images.txt (two lines per image, or one)."""
    txt = sparse / "images.txt"
    if not txt.exists():
        return {}
    out = {}
    lines = [ln for ln in txt.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        i += 1
        if len(parts) < 10:
            continue
        try:
            q = np.array(list(map(float, parts[1:5])))
            t = np.array(list(map(float, parts[5:8])))
            name = parts[9]
        except ValueError:
            continue
        fid = frame_idx(name)
        if fid < 0:
            continue
        R = qvec_to_rotmat(q)
        out[fid] = cam_center_from_w2c(R, t)
        # POINTS2D line
        if i < len(lines) and (lines[i].startswith(" ") or not lines[i][0].isdigit()):
            i += 1
        elif i < len(lines) and len(lines[i].split()) != 10:
            i += 1
    return out


def align_c3vd_via_align_mesh(sc: dict) -> o3d.geometry.TriangleMesh | None:
    """Same Sim(3) as run.sh -> utils/align_mesh.py (GT pose.txt cameras -> COLMAP cameras)."""
    gt_obj = Path(sc["gt"])
    pose = Path(sc["gt_pose"])
    sparse = Path(sc["sparse"])
    if not gt_obj.exists() or not pose.exists() or not sparse.exists():
        return None
    if pycolmap is None:
        print("  pycolmap missing; cannot match align_mesh COLMAP poses", flush=True)
        return None
    lines = pose.read_text().splitlines()
    rec = pycolmap.Reconstruction(str(sparse))
    points_setA = []
    points_setB = []
    used_frame_ids = []
    for image in rec.images.values():
        try:
            frame_id = int(Path(image.name).name.split(".")[0])
        except (ValueError, IndexError):
            continue
        if frame_id >= len(lines):
            continue
        line = lines[frame_id].strip()
        if not line:
            continue
        data = np.fromstring(line, sep=",")
        if data.size != 16:
            continue
        pose_a = data.reshape((4, 4)).T
        cfw = image.cam_from_world() if callable(getattr(image, "cam_from_world", None)) else image.cam_from_world
        center_b = np.asarray(cfw.inverse().matrix()[:3, 3], dtype=np.float64)
        points_setA.append(pose_a[:3, 3])
        points_setB.append(center_b)
        used_frame_ids.append(frame_id)
    if len(points_setA) < 4:
        print(f"  align_mesh: too few frames ({len(points_setA)})", flush=True)
        return None
    A = np.asarray(points_setA)
    B = np.asarray(points_setB)
    T = estimate_similarity_transform(A, B)
    err = np.linalg.norm((T[:3, :3] @ A.T).T + T[:3, 3] - B, axis=1).mean()
    print(
        f"  align_mesh Sim3: {len(A)} frames ({min(used_frame_ids)}–{max(used_frame_ids)}), "
        f"center err {err:.4f}",
        flush=True,
    )
    mesh = o3d.io.read_triangle_mesh(str(gt_obj), enable_post_processing=True)
    mesh.transform(T)
    return mesh


def align_vrcaps_best_fit(sc: dict, mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
    """align_to_gt_VR_CAPS inverse: scale GT then rigid best-fit of camera centers into pred frame."""
    est = load_est_centers(Path(sc["sparse"]))
    gt = load_images_txt_centers(Path(sc["gt_pose"]))
    ids = sorted(set(est) & set(gt))
    if len(ids) < 4:
        print(f"  VR-CAPS pose match too few: {len(ids)}", flush=True)
        return mesh
    points = np.stack([est[i] for i in ids])
    gt_points = np.stack([gt[i] for i in ids])
    scale_points = np.linalg.norm(points - points.mean(axis=0), axis=1).mean()
    scale_gt_points = np.linalg.norm(gt_points - gt_points.mean(axis=0), axis=1).mean()
    ratio = scale_points / max(scale_gt_points, 1e-12)
    gt_s = gt_points * ratio
    R, t = best_fit_transform(gt_s, points)
    verts = np.asarray(mesh.vertices) * ratio
    mesh.vertices = o3d.utility.Vector3dVector(verts @ R.T + t)
    err = np.linalg.norm(gt_s @ R.T + t - points, axis=1).mean()
    print(f"  VR-CAPS best-fit {len(ids)} cams, center err {err:.4f}, scale {ratio:.4f}", flush=True)
    return mesh


def align_gt_mesh(sc: dict) -> o3d.geometry.TriangleMesh | None:
    if sc.get("gt") is None or not Path(sc["gt"]).exists():
        return None
    if sc.get("pose_kind") == "c3vd":
        aligned = align_c3vd_via_align_mesh(sc)
        if aligned is not None and not aligned.is_empty():
            return aligned
        print("  falling back to in-process Sim(3)", flush=True)
        gt = load_c3vd_centers(Path(sc["gt_pose"]))
        est = load_est_centers(Path(sc["sparse"]))
        ids = sorted(set(est) & set(gt))
        mesh = o3d.io.read_triangle_mesh(str(sc["gt"]), enable_post_processing=True)
        if len(ids) >= 4:
            A = np.stack([gt[i] for i in ids])
            B = np.stack([est[i] for i in ids])
            T = estimate_similarity_transform(A, B)
            err = np.linalg.norm((T[:3, :3] @ A.T).T + T[:3, 3] - B, axis=1).mean()
            print(f"  Sim3 GT->EST {len(ids)} cams, err {err:.4f}", flush=True)
            mesh.transform(T)
        return mesh
    if not sc.get("gt_pose") or not Path(sc["gt_pose"]).exists():
        print("  missing GT poses; exporting unaligned mesh", flush=True)
        return o3d.io.read_triangle_mesh(str(sc["gt"]), enable_post_processing=True)
    mesh = o3d.io.read_triangle_mesh(str(sc["gt"]), enable_post_processing=True)
    return align_vrcaps_best_fit(sc, mesh)


def simplify_o3d_mesh(mesh: o3d.geometry.TriangleMesh, target_tris: int = 70000) -> o3d.geometry.TriangleMesh:
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


def simplify_mesh(path: Path, target_tris: int = 70000) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=True)
    return simplify_o3d_mesh(mesh, target_tris)


def canonicalize_pcd(pcd: o3d.geometry.PointCloud) -> None:
    pts = np.asarray(pcd.points)
    mn, mx = pts.min(0), pts.max(0)
    center = 0.5 * (mn + mx)
    scale = float(np.max(0.5 * np.maximum(mx - mn, 1e-8)))
    pcd.points = o3d.utility.Vector3dVector((pts - center) / scale)


def canonicalize(pcd: o3d.geometry.PointCloud, mesh: o3d.geometry.TriangleMesh | None) -> None:
    """Frame the full reconstruction; apply the same transform to aligned GT if present."""
    pts = np.asarray(pcd.points)
    mn, mx = pts.min(0), pts.max(0)
    center = 0.5 * (mn + mx)
    scale = float(np.max(0.5 * np.maximum(mx - mn, 1e-8)))
    pcd.points = o3d.utility.Vector3dVector((pts - center) / scale)
    if mesh is not None:
        verts = np.asarray(mesh.vertices)
        mesh.vertices = o3d.utility.Vector3dVector((verts - center) / scale)
        mesh.compute_vertex_normals()


def write_gt_ply(mesh: o3d.geometry.TriangleMesh, path: Path) -> dict:
    path = path.with_suffix(".ply")
    o3d.io.write_triangle_mesh(str(path), mesh, write_vertex_colors=True, write_ascii=False)
    return {"format": "ply", "file": path.name, "tris": int(len(mesh.triangles)), "bytes": path.stat().st_size}


def process_points_entry(sc: dict, with_gt: bool) -> dict:
    print(f"=== {sc['id']} ===", flush=True)
    archive_copy(sc["ply"], f"{sc['id']}_points3D.ply")
    if with_gt and sc.get("gt"):
        archive_copy(Path(sc["gt"]), f"{sc['id']}_gt{Path(sc['gt']).suffix}")
    pcd = o3d.io.read_point_cloud(str(sc["ply"]))
    print(f"  points {len(pcd.points)}", flush=True)
    mesh = None
    if with_gt:
        aligned = align_gt_mesh(sc)
        if aligned is not None and not aligned.is_empty():
            mesh = simplify_o3d_mesh(aligned)
        else:
            print("  no GT mesh for this scene", flush=True)
        canonicalize(pcd, mesh)
    else:
        canonicalize_pcd(pcd)
    save_thumb(sc.get("thumb"), PREVIEW / f"{sc['id']}.webp", pcd)
    entry = {
        "id": sc["id"],
        "label": sc["label"],
        "dataset": sc["dataset"],
        "preview": f"assets/previews/{sc['id']}.webp",
        "points": {},
    }
    for lod, n in LODS.items():
        ds = downsample(pcd, n)
        meta = write_pnts(ds, POINTS / f"{sc['id']}_{lod}.bin")
        entry["points"][lod] = {"url": f"assets/points/{sc['id']}_{lod}.bin", **meta}
        print(f"  lod {lod}: {meta['count']} pts, {meta['bytes']/1024:.0f} KB", flush=True)
    if mesh is not None:
        gmeta = write_gt_ply(mesh, MESHES / f"{sc['id']}_gt.ply")
        entry["gt"] = {"url": f"assets/meshes/{gmeta['file']}", **gmeta}
        print(f"  gt {gmeta}", flush=True)
    return entry


def main() -> None:
    ensure_dirs()
    for old in MESHES.glob("*.glb"):
        old.unlink()
    compare_manifest = [process_points_entry(sc, with_gt=True) for sc in COMPARE_SCENES]
    endo_manifest = [process_points_entry(sc, with_gt=False) for sc in ENDOMAPPER_SCENES]
    data = ROOT / "docs" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "scenes.json").write_text(json.dumps(compare_manifest, indent=2))
    (data / "endomapper.json").write_text(json.dumps(endo_manifest, indent=2))
    print("wrote", data / "scenes.json")
    print("wrote", data / "endomapper.json")


if __name__ == "__main__":
    main()
