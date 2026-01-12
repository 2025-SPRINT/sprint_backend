# app/main.py
import json
from modules.npr_wrapper import run_npr_json

MODULES = {
    "ai_detection": run_npr_json,
    # "fact_check": run_factcheck_json,
    # "script_extract": run_script_extract_json,
    # "video_download": run_video_download_json,
}

def run_pipeline(req: dict) -> dict:
    task = (req.get("options", {}) or {}).get("task", "ai_detection")
    if task not in MODULES:
        return {
            "request_id": req.get("request_id", ""),
            "module": "main",
            "status": "error",
            "results": {"label": "unknown", "score": None, "threshold": None, "details": {}},
            "artifacts": {},
            "error": {"code": "UNKNOWN_TASK", "message": f"지원하지 않는 task: {task}", "trace": ""},
            "meta": {}
        }
    return MODULES[task](req)

if __name__ == "__main__":
    # 예: python app/main.py app/schemas/request_example.json
    import sys
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        req = json.load(f)

    out = run_pipeline(req)
    print(json.dumps(out, ensure_ascii=False, indent=2))
