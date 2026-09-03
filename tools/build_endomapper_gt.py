#!/usr/bin/env python3
"""EXPERIMENTAL — DO NOT SHIP as website GT.

Attempt to fuse EndoMapper depth EXR + trajectory.csv into a world-frame cloud.

Known broken / unvalidated:
  - info.txt says depth & pose units are dm (absolute), but reading EXR R as
    linear camera-Z collapses geometry; EndoRecon notes corr(1/z, exr)~0.8 and
    no simple k/z / A+B*z model fits Seq_0 against the static mesh.
  - Static meshes (export_world / evaluated_gt_faces_visible_flip) are identical
    across Seq_0/1/2; only per-frame deformed depth differs (A, omega in info.txt).
  - Pose: trajectory.csv t + (rW,rX,rY,rZ) treated as c2w; not independently proven.

Do not point prepare_assets / scenes.json at outputs of this script until a
control test on Seq_0 (A=0) matches the static GT mesh closely.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2
import numpy as np
import open3d as o3d

RAW_ROOT = Path("/home/arthur/disk/data1/antony_mpac/sfm/EndoMapper")
OUT_ROOT = Path("/home/arthur/EndoMetric_output/Endomapper/Simulated_Sequences")
SEQS = ["Seq_0", "Seq_1", "Seq_2"]
STRIDE = 4  # pixel stride when back-projecting depth
MAX_POINTS = 400_000


def parse_calibration(path: Path) -> tuple[float, float, float, float, int, int]:
    data = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip()
    return (
        float(data["fx"]),
        float(data["fy"]),
        float(data["cx"]),
        float(data["cy"]),
        int(data["cols"]),
        int(data["rows"]),
    )


def load_trajectory(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            try:
                rows.append(
                    {
                        "t": np.array(
                            [float(row["tX"]), float(row["tY"]), float(row["tZ"])],
                            dtype=np.float64,
                        ),
                        "q": np.array(
                            [
                                float(row["rW"]),
                                float(row["rX"]),
                                float(row["rY"]),
                                float(row["rZ"]),
                            ],
                            dtype=np.float64,
                        ),
                    }
                )
            except (TypeError, ValueError, KeyError):
                continue
    return rows


def quat_c2w_to_R(q_wxyz: np.ndarray) -> np.ndarray:
    q = q_wxyz / max(np.linalg.norm(q_wxyz), 1e-12)
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def c2w_to_w2c_qvec_tvec(t_c2w: np.ndarray, q_wxyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    R_c2w = quat_c2w_to_R(q_wxyz)
    R_w2c = R_c2w.T
    t_w2c = -R_w2c @ t_c2w
    # rotation matrix -> quaternion (w,x,y,z)
    m = R_w2c
    tr = np.trace(m)
    if tr > 0:
        s = 0.5 / np.sqrt(tr + 1.0)
        w = 0.25 / s
        x = (m[2, 1] - m[1, 2]) * s
        y = (m[0, 2] - m[2, 0]) * s
        z = (m[1, 0] - m[0, 1]) * s
    else:
        if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
            w = (m[2, 1] - m[1, 2]) / s
            x = 0.25 * s
            y = (m[0, 1] + m[1, 0]) / s
            z = (m[0, 2] + m[2, 0]) / s
        elif m[1, 1] > m[2, 2]:
            s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
            w = (m[0, 2] - m[2, 0]) / s
            x = (m[0, 1] + m[1, 0]) / s
            y = 0.25 * s
            z = (m[1, 2] + m[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
            w = (m[1, 0] - m[0, 1]) / s
            x = (m[0, 2] + m[2, 0]) / s
            y = (m[1, 2] + m[2, 1]) / s
            z = 0.25 * s
    q = np.array([w, x, y, z], dtype=np.float64)
    q /= max(np.linalg.norm(q), 1e-12)
    return q, t_w2c


def load_depth(path: Path) -> np.ndarray | None:
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 3:
        # EndoMapper AOV stores metric depth in R
        return im[..., 2].astype(np.float32) if im.shape[2] >= 3 else im[..., 0].astype(np.float32)
    return im.astype(np.float32)


def fuse_sequence(seq: str) -> None:
    raw = RAW_ROOT / seq
    out_scene = OUT_ROOT / seq
    gt_dir = out_scene / "GT"
    gt_dir.mkdir(parents=True, exist_ok=True)

    fx, fy, cx, cy, cols, rows = parse_calibration(raw / "calibration.txt")
    traj = load_trajectory(raw / "trajectory.csv")
    depth_files = sorted((raw / "depth").glob("aov_image_*.exr"))
    rgb_dir = raw / "origin_flip"
    if not rgb_dir.is_dir():
        rgb_dir = raw / "origin"

    n = min(len(traj), len(depth_files))
    print(f"=== {seq}: traj={len(traj)} depth={len(depth_files)} use={n}  {cols}x{rows} ===", flush=True)

    all_xyz: list[np.ndarray] = []
    all_rgb: list[np.ndarray] = []
    images_txt_lines: list[str] = []

    ys, xs = np.mgrid[0:rows:STRIDE, 0:cols:STRIDE]
    for i in range(n):
        depth = load_depth(depth_files[i])
        if depth is None:
            continue
        if depth.shape[0] != rows or depth.shape[1] != cols:
            depth = cv2.resize(depth, (cols, rows), interpolation=cv2.INTER_NEAREST)
        z = depth[::STRIDE, ::STRIDE]
        m = np.isfinite(z) & (z > 1e-4) & (z < 50.0)
        if not np.any(m):
            continue
        X = (xs[m] - cx) * z[m] / fx
        Y = (ys[m] - cy) * z[m] / fy
        Z = z[m]
        Xc = np.stack([X, Y, Z], axis=1)

        t = traj[i]["t"]
        q = traj[i]["q"]
        R_c2w = quat_c2w_to_R(q)
        Xw = Xc @ R_c2w.T + t

        rgb_path = rgb_dir / f"image_{i:04d}.png"
        if rgb_path.exists():
            bgr = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
            if bgr is not None:
                if bgr.shape[0] != rows or bgr.shape[1] != cols:
                    bgr = cv2.resize(bgr, (cols, rows), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
                cols_rgb = rgb[::STRIDE, ::STRIDE][m]
            else:
                cols_rgb = np.tile(np.array([[0.82, 0.62, 0.52]]), (Xw.shape[0], 1))
        else:
            cols_rgb = np.tile(np.array([[0.82, 0.62, 0.52]]), (Xw.shape[0], 1))

        all_xyz.append(Xw)
        all_rgb.append(cols_rgb)

        q_w2c, t_w2c = c2w_to_w2c_qvec_tvec(t, q)
        name = f"image_{i:04d}.png"
        images_txt_lines.append(
            f"{i + 1} {q_w2c[0]:.9f} {q_w2c[1]:.9f} {q_w2c[2]:.9f} {q_w2c[3]:.9f} "
            f"{t_w2c[0]:.9f} {t_w2c[1]:.9f} {t_w2c[2]:.9f} 1 {name}"
        )

        if (i + 1) % 50 == 0:
            print(f"  fused {i + 1}/{n}", flush=True)

    if not all_xyz:
        raise RuntimeError(f"No points fused for {seq}")

    xyz = np.concatenate(all_xyz, axis=0)
    rgb = np.concatenate(all_rgb, axis=0)
    if len(xyz) > MAX_POINTS:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(xyz), MAX_POINTS, replace=False)
        xyz, rgb = xyz[idx], rgb[idx]

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    pcd.colors = o3d.utility.Vector3dVector(rgb)
    ply_path = gt_dir / "gt_from_depth_traj.ply"
    o3d.io.write_point_cloud(str(ply_path), pcd)
    print(f"  wrote {ply_path}  ({len(xyz)} pts)", flush=True)

    # COLMAP text poses for alignment (centers via cam_from_world inverse)
    cam_line = f"1 PINHOLE {cols} {rows} {fx} {fy} {cx} {cy}\n"
    (gt_dir / "cameras.txt").write_text(
        "# Camera list\n# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n" + cam_line
    )
    img_txt = (
        "# Image list with two lines of data per image:\n"
        "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n"
        "#   POINTS2D[] as (X, Y, POINT3D_ID)\n"
    )
    for line in images_txt_lines:
        img_txt += line + "\n\n"
    (gt_dir / "images.txt").write_text(img_txt)
    (gt_dir / "points3D.txt").write_text("# empty\n")
    print(f"  wrote {gt_dir / 'images.txt'}  ({len(images_txt_lines)} poses)", flush=True)


def main() -> None:
    for seq in SEQS:
        fuse_sequence(seq)


if __name__ == "__main__":
    main()
