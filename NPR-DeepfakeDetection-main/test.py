# test.py
import os
import json
from datetime import datetime, timezone, timedelta

import torch
import numpy as np
from sklearn.metrics import average_precision_score, accuracy_score, precision_recall_curve

from networks.resnet import resnet50
from options.test_options import TestOptions
from data import create_dataloader

KST = timezone(timedelta(hours=9))


def ensure_dir_for_file(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def dump_json(path: str, obj: dict):
    ensure_dir_for_file(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def append_jsonl(path: str, record: dict):
    ensure_dir_for_file(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def compute_best_f1(y_true, y_score):
    """
    y_true: list[int] (0/1)
    y_score: list[float] (prob of fake)
    """
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    # precision_recall_curve returns len(thresholds) = len(precision)-1
    f1 = (2 * precision * recall) / (precision + recall + 1e-12)
    best_idx = int(np.argmax(f1))
    best_f1 = float(f1[best_idx])
    # threshold index alignment: f1 has same length as precision/recall
    # thresholds corresponds to points [1:] typically, so guard.
    if best_idx == 0:
        best_thr = 0.0
    else:
        best_thr = float(thresholds[best_idx - 1]) if (best_idx - 1) < len(thresholds) else float(thresholds[-1])
    return best_f1, best_thr


def validate_and_collect(model, opt, device):
    data_loader = create_dataloader(opt)

    y_true = []
    y_score = []
    predictions = []

    # JSONL을 쓰면 대용량에서도 안전
    jsonl_path = getattr(opt, "output_jsonl", None)
    use_jsonl = bool(jsonl_path)

    with torch.no_grad():
        for batch in data_loader:
            # ✅ (호환) (img, label) 또는 (img, label, path) 둘 다 처리
            if len(batch) == 2:
                img, label = batch
                paths = [None] * len(label)
            else:
                img, label, paths = batch

            img = img.to(device)
            label_np = label.detach().cpu().numpy().astype(int).tolist()

            logit = model(img).flatten()
            prob = torch.sigmoid(logit).detach().cpu().numpy().astype(float).tolist()
            logit_list = logit.detach().cpu().numpy().astype(float).tolist()

            for i in range(len(label_np)):
                _lab = int(label_np[i])
                _prob = float(prob[i])
                _logit = float(logit_list[i])

                if paths[i] is None:
                    _id = None
                else:
                    # paths[i]가 tensor/bytes/string 등일 수 있으니 안전 처리
                    p = paths[i]
                    if isinstance(p, (bytes, bytearray)):
                        p = p.decode("utf-8", errors="ignore")
                    _id = os.path.basename(str(p))

                rec = {
                    "id": _id,
                    "label": _lab,
                    "prob_fake": _prob,
                    "logit": _logit
                }

                y_true.append(_lab)
                y_score.append(_prob)

                if use_jsonl:
                    append_jsonl(jsonl_path, rec)
                else:
                    predictions.append(rec)

    # metrics
    acc = float(accuracy_score(y_true, [1 if s >= 0.5 else 0 for s in y_score]))
    ap = float(average_precision_score(y_true, y_score))

    f1_05 = None
    # f1@0.5 계산(선택) - 필요하면 사용
    # 여기서는 간단히 넣어둠
    tp = sum((yt == 1 and ys >= 0.5) for yt, ys in zip(y_true, y_score))
    fp = sum((yt == 0 and ys >= 0.5) for yt, ys in zip(y_true, y_score))
    fn = sum((yt == 1 and ys < 0.5) for yt, ys in zip(y_true, y_score))
    precision = tp / (tp + fp + 1e-12)
    recall = tp / (tp + fn + 1e-12)
    f1_05 = float(2 * precision * recall / (precision + recall + 1e-12))

    best_f1, best_thr = compute_best_f1(y_true, y_score)

    metrics = {
        "acc": acc,
        "ap": ap,
        "f1_at_0_5": f1_05,
        "best_f1": {"value": best_f1, "thr": best_thr}
    }

    return metrics, predictions, len(y_true)


def main():
    opt = TestOptions().parse()
    use_cuda = torch.cuda.is_available() and (len(getattr(opt, "gpu_ids", [])) > 0)
    device = torch.device("cuda" if use_cuda else "cpu")

    model = resnet50(num_classes=1)
    model.to(device)

    # 가중치 로드(Colab/CPU/GPU 호환)
    state_dict = torch.load(opt.model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()

    run = {
        "timestamp": datetime.now(KST).isoformat(),
        "device": str(device)
    }

    # opt를 config로 (JSON화 가능한 것만)
    config = {}
    for k, v in vars(opt).items():
        try:
            json.dumps(v)
            config[k] = v
        except TypeError:
            config[k] = str(v)

    # (중요) JSONL을 쓸 경우: 기존 파일이 있으면 덮어쓰기 느낌으로 비우는 걸 권장
    if getattr(opt, "output_jsonl", None):
        ensure_dir_for_file(opt.output_jsonl)
        if os.path.exists(opt.output_jsonl):
            os.remove(opt.output_jsonl)

    metrics, predictions, n_samples = validate_and_collect(model, opt, device)

    out = {
        "run": run,
        "config": config,
        "metrics": metrics,
        "n_samples": n_samples
    }

    # ✅ predictions를 summary JSON에 포함할지 여부
    if getattr(opt, "save_predictions", False):
        out["predictions"] = predictions

    # ✅ 저장
    if getattr(opt, "output_json", None):
        dump_json(opt.output_json, out)

    # ✅ 기존 콘솔 출력도 유지(원하면 지워도 됨)
    print("========== RESULT ==========")
    print(json.dumps(out["metrics"], ensure_ascii=False, indent=2))
    if getattr(opt, "output_json", None):
        print(f"[Saved] summary json -> {opt.output_json}")
    if getattr(opt, "output_jsonl", None):
        print(f"[Saved] predictions jsonl -> {opt.output_jsonl}")


if __name__ == "__main__":
    main()
