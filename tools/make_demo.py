#!/usr/bin/env python3
"""Build a short paper-faithful demo (no reuse of the old Demov4 file)."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/home/arthur/EndoCDCG")
DOCS = ROOT / "docs"
FRAMES = ROOT / "tools" / ".cache" / "demo_frames"
W, H, FPS = 1280, 720, 30

INK = (28, 25, 22)
PAPER = (247, 245, 241)
ACCENT = (139, 46, 46)
MUTED = (92, 86, 78)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def slide(lines: list[tuple[str, int, bool]], subtitle: str | None = None) -> Image.Image:
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 12, H), fill=ACCENT)
    y = 160
    for text, size, bold in lines:
        f = font(size, bold)
        bbox = d.textbbox((0, 0), text, font=f)
        x = (W - (bbox[2] - bbox[0])) // 2
        d.text((x, y), text, font=f, fill=INK)
        y += size + 18
    if subtitle:
        f = font(28, False)
        bbox = d.textbbox((0, 0), subtitle, font=f)
        x = (W - (bbox[2] - bbox[0])) // 2
        d.text((x, H - 90), subtitle, font=f, fill=MUTED)
    return im


def write_still(im: Image.Image, stem: str, seconds: float) -> Path:
    FRAMES.mkdir(parents=True, exist_ok=True)
    path = FRAMES / f"{stem}.png"
    im.save(path)
    n = max(1, int(round(seconds * FPS)))
    seq = FRAMES / stem
    seq.mkdir(exist_ok=True)
    for i in range(n):
        shutil.copy(path, seq / f"{i:04d}.png")
    return seq


def paper_panel(page: int, caption: str, seconds: float) -> Path:
    src = DOCS / "figures" / f"paper-{page}.webp"
    im = Image.new("RGB", (W, H), PAPER)
    fig = Image.open(src).convert("RGB")
    fig.thumbnail((1180, 560))
    im.paste(fig, ((W - fig.width) // 2, 70))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 12, H), fill=ACCENT)
    f = font(26, True)
    d.text((40, 24), caption, font=f, fill=INK)
    return write_still(im, f"paper{page}", seconds)


def parse_pnts(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    n = int.from_bytes(raw[4:8], "little")
    mn = np.frombuffer(raw, dtype="<f4", count=3, offset=8)
    mx = np.frombuffer(raw, dtype="<f4", count=3, offset=20)
    span = np.maximum(mx - mn, 1e-8)
    body = np.frombuffer(raw, dtype="<u2", offset=32).reshape(n, 5)
    xyz = mn + (body[:, :3].astype(np.float64) / 65535.0) * span
    r = body[:, 3] & 0xFF
    g = (body[:, 3] >> 8) & 0xFF
    b = body[:, 4] & 0xFF
    rgb = np.stack([r, g, b], 1).astype(np.float64) / 255.0
    return xyz.astype(np.float32), rgb.astype(np.float32)


def render_orbit(points_bin: Path, gt_glb: Path | None, stem: str, seconds: float, split: bool) -> Path:
    xyz, rgb = parse_pnts(points_bin)
    rng = np.random.default_rng(0)
    if len(xyz) > 80000:
        idx = rng.choice(len(xyz), 80000, replace=False)
        xyz, rgb = xyz[idx], rgb[idx]
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(rgb.astype(np.float64))

    renderer = o3d.visualization.rendering.OffscreenRenderer(W, H)
    scene = renderer.scene
    scene.set_background([0.07, 0.07, 0.08, 1.0])
    mat = o3d.visualization.rendering.MaterialRecord()
    mat.shader = "defaultUnlit"
    mat.point_size = 2.5
    scene.add_geometry("pcd", pcd, mat)

    if split and gt_glb and gt_glb.exists():
        mesh = o3d.io.read_triangle_mesh(str(gt_glb))
        mesh.compute_vertex_normals()
        mesh.paint_uniform_color([0.85, 0.55, 0.42])
        mm = o3d.visualization.rendering.MaterialRecord()
        mm.shader = "defaultLit"
        mm.base_color = [0.85, 0.55, 0.42, 1.0]
        scene.add_geometry("gt", mesh, mm)

    bounds = pcd.get_axis_aligned_bounding_box()
    center = bounds.get_center()
    extent = max(float(np.linalg.norm(bounds.get_extent())), 1e-3)
    eye0 = center + np.array([0.15 * extent, 0.2 * extent, 1.15 * extent])
    n = max(1, int(round(seconds * FPS)))
    out = FRAMES / stem
    out.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        ang = 2 * math.pi * i / n
        c, s = math.cos(ang), math.sin(ang)
        eye = center + np.array([1.15 * extent * s, 0.18 * extent, 1.15 * extent * c])
        renderer.setup_camera(55.0, center, eye, [0, 1, 0])
        img = renderer.render_to_image()
        Image.fromarray(np.asarray(img)).save(out / f"{i:04d}.png")
    return out


def concat(seqs: list[Path], dest: Path) -> None:
    listfile = FRAMES / "list.txt"
    # encode each seq then concat
    parts = []
    for i, seq in enumerate(seqs):
        mp4 = FRAMES / f"part{i}.mp4"
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(seq / "%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(mp4),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        parts.append(mp4)
    listfile.write_text("".join(f"file '{p}'\n" for p in parts))
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22",
            "-movflags", "+faststart", str(dest),
        ]
    )


def main() -> None:
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    seqs = []
    seqs.append(write_still(
        slide(
            [
                ("IEEE ICIP 2026", 28, True),
                ("Constrained Dense Correspondence Graphs", 36, True),
                ("for Robust Endoscopic Structure-from-Motion", 30, False),
                ("Lin, Han, Yen, Chen  ·  NTU / NTUH", 24, False),
            ]
        ),
        "title",
        4.0,
    ))
    seqs.append(paper_panel(1, "Problem: dense matchers invent edges between non-overlapping views", 5.0))
    seqs.append(write_still(
        slide(
            [
                ("Constrained graph, not exhaustive matching", 32, True),
                ("E_local   temporal window", 28, False),
                ("E_keyframe   flow-selected parallax", 28, False),
                ("E_loop   CosPlace revisits", 28, False),
                ("Then incremental COLMAP SfM", 28, False),
            ]
        ),
        "method",
        6.0,
    ))
    seqs.append(paper_panel(3, "C3VD: denser clouds, stable trajectories vs COLMAP", 5.0))
    pts = DOCS / "assets/points/c3vd_trans_t4_a_desktop.bin"
    gt = DOCS / "assets/meshes/c3vd_trans_t4_a_gt.glb"
    seqs.append(render_orbit(pts, gt, "orbit", 8.0, split=False))
    seqs.append(write_still(
        slide(
            [
                ("Registration on clinical Dataset 1 (N = 601)", 28, True),
                ("Local only                 2.2%", 32, False),
                ("+ keyframes              98.5%", 32, False),
                ("+ loop closures        99.7%", 32, True),
            ],
            subtitle="Interactive reconstructions: pianoholic0120.github.io/EndoCDCG/",
        ),
        "numbers",
        6.0,
    ))
    qr = Image.open(DOCS / "qr/endocdcg.png").convert("RGB").resize((220, 220))
    end = slide(
        [
            ("See the reconstructions in 3D", 34, True),
            ("https://pianoholic0120.github.io/EndoCDCG/", 24, False),
        ]
    )
    end.paste(qr, ((W - 220) // 2, 420))
    seqs.append(write_still(end, "end", 4.0))

    dest = DOCS / "video" / "demo.mp4"
    concat(seqs, dest)
    subprocess.check_call(
        ["ffmpeg", "-y", "-ss", "1", "-i", str(dest), "-frames:v", "1", "-q:v", "4", str(DOCS / "video" / "poster.jpg")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("wrote", dest, dest.stat().st_size)


if __name__ == "__main__":
    main()
