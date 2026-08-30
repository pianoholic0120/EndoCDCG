# EndoCDCG

Project page for:

**Constrained Dense Correspondence Graphs for Robust Structure-from-Motion Targeting Endoscopic Videos**  
Yu-Chun Lin, Ming-Lun Han, Kuang-Chen Yen, Homer H. Chen  
IEEE International Conference on Image Processing (**ICIP 2026**)

**Live page:** [https://pianoholic0120.github.io/EndoCDCG/](https://pianoholic0120.github.io/EndoCDCG/)

[IEEE Xplore](https://ieeexplore.ieee.org/document/11630223)

This repository hosts the **static project website** (interactive reconstructions, abstract, citation). It does **not** include source code for the reconstruction pipeline.

## Contents

- Abstract and citation (BibTeX)
- Interactive 3D SfM point clouds on public phantom / simulated data:
  - **C3VDv2** and **VR-CAPS** — with optional ground-truth mesh comparison
  - **EndoMapper** simulated sequences — point cloud viewer only
- Author PDF and poster QR linking to the canonical page URL above

## Local preview

```bash
cd docs
python3 -m http.server 8080
```

Then open [http://127.0.0.1:8080/](http://127.0.0.1:8080/).

## Citation

```bibtex
@inproceedings{lin2026endocdcg,
  title     = {Constrained Dense Correspondence Graphs for Robust Structure-from-Motion Targeting Endoscopic Videos},
  author    = {Lin, Yu-Chun and Han, Ming-Lun and Yen, Kuang-Chen and Chen, Homer H.},
  booktitle = {IEEE International Conference on Image Processing (ICIP)},
  year      = {2026}
}
```

## Acknowledgements

Interactive 3D on the page uses public datasets only (C3VDv2, VR-CAPS, EndoMapper simulated sequences). Please cite those datasets as listed on the project page. Clinical reconstructions are not hosted here.
