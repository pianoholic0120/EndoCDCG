# Do not delete — GitHub backup of selected reconstructions

This folder stores **copies** (not shortcuts) of the exact files used to build the project page.

If `EndoMetric_output` is cleaned up, the website in `docs/` still works: it only reads
processed files under `docs/assets/`. Those processed files are also in git.

| File | Role |
|------|------|
| `*_points3D.ply` | COLMAP SfM cloud from `colmap_mast3r` (paper output) |
| `*_gt.obj` / `*_gt.ply` | Dataset ground-truth mesh for slider comparison only |

Rebuild web LODs (does not re-run SfM):

```bash
python3 tools/prepare_assets.py
```

Edit `tools/prepare_assets.py` to point `SRC` at this folder if the original dataset path is gone.
