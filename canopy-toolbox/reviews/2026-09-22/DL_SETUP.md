# ArcGIS Pro point-cloud deep learning setup — 2026-09-22

## Installed runtime

ArcGIS Pro 3.7.2 now has the matching [Esri Deep Learning Libraries for Pro 3.7](https://github.com/Esri/deep-learning-frameworks) installed into its default arcgispro-py3 environment. The downloaded installer was the Pro 3.7 archive from Esri (SHA-256 1771D1535CEC61ABDA681E190118576BAF65B8BF74BAB68179E492FF000A53DE); the MSI carried a valid Environmental Systems Research Institute signature and exited with code 0. The archive and extracted installer were temporary installation files.

Runtime verification: PyTorch 2.9.1 imports; CUDA is available on NVIDIA RTX A4000; ArcGIS API for Python is 2.4.3. The existing 3D Analyst license was used for model smoke tests. ArcGIS Pro should be restarted after the MSI installation.

## Downloaded models

Both public Esri DLPKs are in ignored scratch storage. They are input files for Classify Point Cloud Using Trained Model, not Python packages.

| Model | Living Atlas item | Local file | SHA-256 | Embedded EMD |
|---|---|---|---|---|
| Tree Point Classification | [item](https://www.arcgis.com/home/item.html?id=58d77b24469d4f30b5f68973deb65599) | [DLPK](../../scratch/models/tree-point-classification.dlpk) | 3da9136594bca05f650e0bbbecfd802365e7b854916b9218126f3867d285e91e | PointCNN; XYZ plus Number of Returns; outputs 0/background and 5/tree; 50 m block and 8,192 point limit |
| Building Point Classification | [item](https://www.arcgis.com/home/item.html?id=a64fa0b01aef406c8a0b2feaa1feee76) | [DLPK](../../scratch/models/building-point-classification.dlpk) | 854bd59ee4626244897641b224ceb77dda017a7008756a888c361b6d553d2ef6 | RandLA-Net; XYZ; outputs 0/background and 6/building; 100 m block and 30,000 point limit |

Both archives passed ZIP integrity checks. The pilot LAS is format 6 and supplies all attributes required by these two model files. It has no RGB/NIR point color. The current Esri [Tree Point Classification fine-tuning page](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/finetuning-the-tree-point-classification.htm) gives a 40 m / 40,000-point example; this downloaded DLPK's embedded EMD declares 50 m / 8,192 points. Inspect the actual EMD and resolve the mismatch before fine-tuning; no training data was created or model fine-tuned in this setup.

## Isolated GPU inference smoke test

A new prepared LAS copy over 428200–428250 E, 4504250–4504300 N contained 35,611 points. A [smoke-test script](../../scratch/models/smoke_test.py) created separate working LAS copies and ran both models on GPU with batch size 1. Existing ground/noise classes were preserved. [Output class counts](../../scratch/models/smoke_test.json):

| Trial | Class 0 | Class 2 | Class 5 | Class 6 | Class 18 |
|---|---:|---:|---:|---:|---:|
| Tree model | 21,962 | 7,141 | 6,482 | 0 | 26 |
| Building model | 25,476 | 7,141 | 0 | 2,968 | 26 |

Both ArcGIS geoprocessing calls completed successfully. This only establishes installation and model execution. The predictions have not been compared with independent labels, and these trial classes must not be treated as validated Millcreek inventory results. Source delivery LAS files and the prior prepared copy were unchanged.

The next experiment should run each model on a copied representative AOI and compare canopy area, roof-edge artifacts, and tree detections against a fixed imagery/reference sample before changing the production pipeline. Model inference edits the LAS copy supplied to it, so always create a new working copy.
