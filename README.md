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
- Interactive 3D SfM point clouds with ground-truth comparison on public phantom / simulated data:
  - **C3VDv2**, **VR-CAPS**, and **EndoMapper** simulated sequences
- Author PDF and poster QR linking to the canonical page URL above

## Local preview

```bash
cd docs
python3 -m http.server 8080
```

Then open [http://127.0.0.1:8080/](http://127.0.0.1:8080/).

## Citation

```bibtex
@INPROCEEDINGS{11630223,
  author={Lin, Yu-Chun and Han, Ming-Lun and Yen, Kuang-Chen and Chen, Homer H.},
  booktitle={2026 IEEE International Conference on Image Processing (ICIP)},
  title={Constrained Dense Correspondence Graphs for Robust Structure-From-Motion Targeting Endoscopic Videos},
  year={2026},
  volume={},
  number={},
  pages={1-6},
  keywords={Printing;Three-dimensional displays;Videos;Sequential analysis;Sequences;Endoscopes;Geometry;Lighting;Biological tissues;Structure from motion;Endoscopy;3D reconstruction;structure-from-motion (SfM);feature matching;image registration},
  doi={10.1109/ICIP61757.2026.11630223}}
```

## Acknowledgements

Interactive 3D on the page uses public datasets only (C3VDv2, VR-CAPS, EndoMapper simulated sequences). Please cite those datasets as listed on the project page. Clinical reconstructions are not hosted here.
