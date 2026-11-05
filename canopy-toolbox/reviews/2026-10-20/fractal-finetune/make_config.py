"""Write the Myria3D configuration for fine-tuning FRACTAL on the sparse training labels: one complete YAML.

    python reviews/2026-10-20/fractal-finetune/make_config.py DATA_DIR RUN_DIR [--epochs 30] [--lr 1e-4] [--batch 10]

Run with the Myria3D environment's Python. The model, dataset description and data transforms come from the released FRACTAL
inference config (trained_model_assets), so the network matches the checkpoint exactly; the training parts it lacks come from
Myria3D's own defaults (training transforms from configs/datamodule/transforms), with these choices:
- task finetune from the FRACTAL checkpoint (weights only; epoch 0, fresh optimizer);
- CrossEntropyLoss with ignore_index 7: unlabelled points (raw code 250, see the Myria3D patch) stay in each 50 m block as
  context and are never scored; Adam at a small learning rate (default 1e-4 against the original 0.0039) so the pretrained
  features are adjusted, not relearned; ReduceLROnPlateau with patience 3;
- samples without any labelled point are dropped (pre_filter_no_labels), since an all-ignored batch gives a NaN loss;
- GPU, early stopping on validation loss (patience 5), best and last checkpoints, CSV logs; no Comet;
- Windows: no worker processes anywhere (the transforms hold lambdas that cannot be pickled).
Writes RUN_DIR/finetune.yaml and prints the command to run it.
"""
import argparse
from pathlib import Path

from omegaconf import OmegaConf

TOOLS = Path(r"C:\Users\bbusch\tools")
CHECKOUT = TOOLS/"myria3d"
INFERENCE = CHECKOUT/"trained_model_assets"/"FRACTAL-LidarHD_7cl_randlanet-inference-Myria3DV3.8.yaml"
CHECKPOINT = CHECKOUT/"trained_model_assets"/"FRACTAL-LidarHD_7cl_randlanet.ckpt"
IGNORE_INDEX = 7


def build(data_dir, run_dir, epochs, lr, batch):
    c = OmegaConf.load(INFERENCE)
    run_dir, data_dir = Path(run_dir).resolve(), Path(data_dir).resolve()
    c.task = {"task_name": "finetune"}
    c.seed = 12345
    m = c.model
    m.ckpt_path = CHECKPOINT.as_posix()
    m.lr = lr
    m.momentum = 0.9
    m.monitor = "val/loss_epoch"
    m.num_workers = 0
    m.criterion = {"_target_": "torch.nn.CrossEntropyLoss", "label_smoothing": 0.0, "ignore_index": IGNORE_INDEX}
    m.optimizer = {"_target_": "functools.partial", "_args_": ["${get_method:torch.optim.Adam}"], "lr": "${model.lr}"}
    m.lr_scheduler = {"_target_": "functools.partial",
                      "_args_": ["${get_method:torch.optim.lr_scheduler.ReduceLROnPlateau}"],
                      "mode": "min", "factor": 0.5, "patience": 3, "cooldown": 1}
    d = c.datamodule
    d.data_dir = data_dir.as_posix()
    d.split_csv_path = (data_dir/"split.csv").as_posix()
    d.hdf5_file_path = (run_dir/"dataset.hdf5").as_posix()
    d.epsg = 6341
    d.subtile_overlap_train = 0
    d.batch_size = batch
    d.num_workers = 0
    d.prefetch_factor = None
    d.pre_filter = {"_target_": "functools.partial",
                    "_args_": ["${get_method:myria3d.pctl.dataset.utils.pre_filter_no_labels}"], "min_num_nodes": 1}
    # The released config is for inference only: take the training preparations (the same steps as eval, without the copies
    # kept for interpolation) and the light augmentations (random x and y flips) from Myria3D's own transforms configs.
    transforms = CHECKOUT/"configs"/"datamodule"/"transforms"
    d.transforms.preparations.train = OmegaConf.load(transforms/"preparations"/"points_budget.yaml").train
    d.transforms.augmentations = OmegaConf.load(transforms/"augmentations"/"light.yaml")
    d.transforms.preparations_train_list = "${oc.dict.values: datamodule.transforms.preparations.train}"
    d.transforms.augmentations_list = "${oc.dict.values: datamodule.transforms.augmentations}"
    c.trainer = {"_target_": "pytorch_lightning.Trainer", "accelerator": "gpu", "devices": 1, "num_nodes": 1,
                 "min_epochs": 1, "max_epochs": epochs, "log_every_n_steps": 1, "num_sanity_val_steps": 1}
    c.logger = {"csv": {"_target_": "pytorch_lightning.loggers.csv_logs.CSVLogger", "save_dir": (run_dir/"logs").as_posix(),
                        "name": "csv", "prefix": ""}}
    c.callbacks = {
        "lr_monitor": {"_target_": "pytorch_lightning.callbacks.LearningRateMonitor", "logging_interval": "step"},
        "model_checkpoint": {"_target_": "pytorch_lightning.callbacks.ModelCheckpoint", "monitor": "val/loss_epoch",
                             "mode": "min", "save_top_k": 1, "save_last": True, "verbose": True,
                             "dirpath": (run_dir/"checkpoints").as_posix(), "filename": "epoch_{epoch:03d}",
                             "auto_insert_metric_name": False},
        "early_stopping": {"_target_": "pytorch_lightning.callbacks.EarlyStopping", "monitor": "val/loss_epoch",
                           "mode": "min", "patience": 5, "min_delta": 0},
        "model_detailed_metrics": {"_target_": "myria3d.callbacks.metric_callbacks.ModelMetrics",
                                   "num_classes": "${model.num_classes}"}}
    c.work_dir = CHECKOUT.as_posix()
    return c


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch", type=int, default=10)
    args = parser.parse_args(argv)
    for folder in ("train", "val"):
        if not (args.data_dir/folder).is_dir():
            raise FileNotFoundError(f"{args.data_dir/folder} is missing (Myria3D reads DATA_DIR/<split>/<basename>)")
    args.run_dir.mkdir(parents=True, exist_ok=True)
    config = build(args.data_dir, args.run_dir, args.epochs, args.lr, args.batch)
    out = args.run_dir/"finetune.yaml"
    if out.exists():
        raise FileExistsError(out)
    OmegaConf.save(config, out)
    print(f"wrote {out}")
    # run.py picks its launcher from task.task_name on the command line, not from the YAML, so both steps name it there.
    base = f'run.py --config-path "{args.run_dir.resolve()}" --config-name finetune.yaml'
    print(f"with LOGS_DIR and PYTHONNOUSERSITE=1 set, in {CHECKOUT}, using the Myria3D environment's Python:")
    print(f"  {base} task.task_name=create_hdf5")
    print(f"  {base} task.task_name=finetune")


if __name__ == "__main__":
    main()
