# EndoCDCG

Project page for **Constrained Dense Correspondence Graphs for Robust Structure-from-Motion Targeting Endoscopic Videos** (IEEE ICIP 2026).

Canonical URL (use this on the poster QR; do not change the path later):

**https://pianoholic0120.github.io/EndoCDCG/**

This repository is a **static demonstration site**. It does not include source code for the reconstruction pipeline.

## What is durable vs what is not

| Location | Purpose | If deleted |
|----------|---------|------------|
| **This GitHub repo** (`docs/` + `source_archive/`) | Canonical public backup | Site and selected reconstructions are gone unless restored from git |
| `docs/` | Files actually served by GitHub Pages | Breaks the website |
| `docs/assets/` | Compressed point clouds, GT meshes, previews, video, PDF | Breaks 3D / video / PDF |
| `source_archive/` | Uncompressed copies of the chosen PLY/OBJ | Website still works; you lose the ability to re-export LODs |
| `~/EndoMetric_output` | Original experiment disk | **Safe to keep or delete for the live site** — nothing on GitHub Pages is a symlink to it |

We **copied** (not symlinked) selected `colmap_mast3r` clouds and GT meshes into this repo so the page does not depend on local disks.

Do **not** put OpenMVS / PGSR / TSDF meshes on this site; they are outside the paper.

## Local preview

```bash
cd docs
python3 -m http.server 8080
```

Open http://127.0.0.1:8080/  (modules will not load from `file://`).

Poster layout: http://127.0.0.1:8080/#poster

## Publish (run these yourself)

1. Create an empty **public** GitHub repository named `EndoCDCG` (no README).
2. In this folder:

```bash
cd /home/arthur/EndoCDCG
git init
git add .
git status   # confirm no secrets; source_archive is intended
git commit -m "Add ICIP 2026 EndoCDCG project page"
git branch -M main
git remote add origin https://github.com/pianoholic0120/EndoCDCG.git
git push -u origin main
```

3. GitHub → **Settings → Pages**:
   - Source: **GitHub Actions**
   - After the workflow `Deploy GitHub Pages` succeeds, the site is live.
4. Print `docs/qr/endocdcg.png` (Level H) on the poster, at least 3–4 cm wide, with white margin.

Optional extra protection: GitHub → Settings → Collaborators, and enable **Rulesets** to prevent force-push to `main`.

## License / data

Cite C3VD / C3VDv2, VR-CAPS, and EndoMapper as listed on the page. Clinical 3D is not hosted here.
