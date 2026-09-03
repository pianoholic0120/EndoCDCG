#!/usr/bin/env python3
"""Build low-res sequence preview MP4s for the project page.

Reads original_images from EndoMetric_output (same 13 website scenes),
subsamples frames, scales to ~480px wide, encodes H.264 for the browser.

Outputs:
  docs/video/previews/{scene_id}.mp4
  docs/data/videos.json
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import cv2

ROOT = Path("/home/arthur/EndoCDCG")
SRC = Path("/home/arthur/EndoMetric_output")
OUT = ROOT / "docs" / "video" / "previews"

# Match Interactive scene order / ids
SCENES = [
    ("endomapper_seq_0", "EndoMapper · Seq 0", "Endomapper/Simulated_Sequences/Seq_0"),
    ("endomapper_seq_1", "EndoMapper · Seq 1", "Endomapper/Simulated_Sequences/Seq_1"),
    ("endomapper_seq_2", "EndoMapper · Seq 2", "Endomapper/Simulated_Sequences/Seq_2"),
    ("vrcaps_colon_17", "VR-CAPS · colon GI_2_17", "VR_CAPS/colon_GI_2_17"),
    ("vrcaps_colon_18", "VR-CAPS · colon GI_2_18", "VR_CAPS/colon_GI_2_18"),
    ("vrcaps_stomach_5", "VR-CAPS · stomach GI_2_5", "VR_CAPS/stomach_GI_2_5"),
    ("vrcaps_stomach_7", "VR-CAPS · stomach GI_2_7", "VR_CAPS/stomach_GI_2_7"),
    ("c3vd_cecum_t1_b", "C3VDv2 · cecum t1-b", "C3VD/cecum_t1_b"),
    ("c3vd_cecum_t2_a", "C3VDv2 · cecum t2-a", "C3VD/cecum_t2_a"),
    ("c3vd_cecum_t2_b", "C3VDv2 · cecum t2-b", "C3VD/cecum_t2_b"),
    ("c3vd_trans_t4_a", "C3VDv2 · transverse t4-a", "C3VD/trans_t4_a"),
    ("c3vd_sigmoid_t1_a", "C3VDv2 · sigmoid t1-a", "C3VD/sigmoid_t1_a"),
    ("c3vd_sigmoid_t3_b", "C3VDv2 · sigmoid t3-b", "C3VD/sigmoid_t3_b"),
]

TARGET_W = 480
FPS = 10
MAX_FRAMES = 150  # ~15s at 10 fps
CRF = 32


def list_images(scene_dir: Path) -> list[Path]:
    for sub in ("original_images", "origin_flip", "origin"):
        d = scene_dir / sub
        if not d.is_dir():
            continue
        imgs = sorted(
            [
                *d.glob("*.png"),
                *d.glob("*.jpg"),
                *d.glob("*.jpeg"),
                *d.glob("*.PNG"),
                *d.glob("*.JPG"),
            ]
        )
        if imgs:
            return imgs
    return []


def subsample(imgs: list[Path], max_n: int) -> list[Path]:
    if len(imgs) <= max_n:
        return imgs
    step = len(imgs) / max_n
    return [imgs[int(i * step)] for i in range(max_n)]


def encode_scene(scene_id: str, label: str, rel: str) -> dict | None:
    imgs = list_images(SRC / rel)
    if not imgs:
        print(f"  SKIP {scene_id}: no images", flush=True)
        return None
    chosen = subsample(imgs, MAX_FRAMES)
    print(f"=== {scene_id}: {len(imgs)} → {len(chosen)} frames ===", flush=True)

    out_mp4 = OUT / f"{scene_id}.mp4"
    OUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"prev_{scene_id}_") as tmp:
        tmp_p = Path(tmp)
        for i, src in enumerate(chosen):
            im = cv2.imread(str(src), cv2.IMREAD_COLOR)
            if im is None:
                continue
            h, w = im.shape[:2]
            if w > TARGET_W:
                nh = max(1, int(round(h * (TARGET_W / w))))
                # even dims for yuv420
                nh = nh + (nh % 2)
                nw = TARGET_W + (TARGET_W % 2)
                im = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA)
            else:
                nh, nw = h + (h % 2), w + (w % 2)
                if (nh, nw) != (h, w):
                    im = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(tmp_p / f"f_{i:05d}.jpg"), im, [int(cv2.IMWRITE_JPEG_QUALITY), 85])

        pattern = str(tmp_p / "f_%05d.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-profile:v", "baseline",
            "-level", "3.0",
            "-crf", str(CRF),
            "-preset", "medium",
            "-movflags", "+faststart",
            "-an",
            str(out_mp4),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    kb = out_mp4.stat().st_size / 1024
    print(f"  wrote {out_mp4.name}  {kb:.0f} KB", flush=True)
    dataset = label.split(" · ")[0] if " · " in label else label.split()[0]
    return {
        "id": scene_id,
        "label": label,
        "dataset": dataset,
        "url": f"assets/../video/previews/{scene_id}.mp4".replace("assets/../", ""),
        "bytes": out_mp4.stat().st_size,
        "frames": len(chosen),
        "fps": FPS,
    }


def main() -> None:
    manifest = []
    for sid, label, rel in SCENES:
        entry = encode_scene(sid, label, rel)
        if entry:
            # cleaner URL
            entry["url"] = f"video/previews/{sid}.mp4"
            manifest.append(entry)
    out = ROOT / "docs" / "data" / "videos.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    total = sum(e["bytes"] for e in manifest) / (1024 * 1024)
    print(f"wrote {out} ({len(manifest)} videos, {total:.1f} MB total)", flush=True)


if __name__ == "__main__":
    main()
