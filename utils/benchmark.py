"""
Model Performance Benchmark Script
-----------------------------------
Compare: Gemini Flash, Exaone-deep:7.8b, Qwen3:8b
Metrics: Response time, JSON validity, reliability_level match
"""
import asyncio
import csv
import json
import time
from datetime import datetime
from typing import Optional

# Import model handlers
from gemini_main import main as gemini_analyze, PROMPT_6
from ollama_main import main as ollama_analyze

# Configuration
CSV_PATH = "scripts.csv"
OUTPUT_PATH = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

MODELS = [
    {"name": "gemini", "provider": "gemini", "model": None},
    {"name": "exaone-deep", "provider": "ollama", "model": "exaone-deep:7.8b"},
    {"name": "qwen3", "provider": "ollama", "model": "qwen3:8b"},
]

def load_scripts(path: str) -> list[dict]:
    """Load ad scripts from CSV."""
    scripts = []
    with open(path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f)
        for row in reader:
            scripts.append({
                "ad": row["ad"],
                "is_hoax": int(row["isHoax"]),
                "url": row["url"],
                "script": row["script"]
            })
    return scripts

async def run_single_test(provider: str, model: Optional[str], script: str) -> dict:
    """Run analysis on a single script with specified model."""
    start_time = time.perf_counter()
    result = {
        "provider": provider,
        "model": model or "gemini-3-flash",
        "duration": 0,
        "json_valid": False,
        "reliability_level": None,
        "error": None
    }
    
    try:
        if provider == "gemini":
            response = await gemini_analyze(PROMPT_6, script)
        else:
            response = await ollama_analyze("", script, model_name=model)
        
        result["duration"] = time.perf_counter() - start_time
        
        # Check JSON validity
        try:
            data = json.loads(response)
            result["json_valid"] = True
            result["reliability_level"] = data.get("reliability_level")
        except (json.JSONDecodeError, TypeError):
            result["json_valid"] = False
            result["reliability_level"] = "PARSE_ERROR"
            
    except Exception as e:
        result["duration"] = time.perf_counter() - start_time
        result["error"] = str(e)
        result["reliability_level"] = "ERROR"
    
    return result

async def run_benchmark():
    """Run full benchmark across all models and scripts."""
    print("=" * 60)
    print("Model Performance Benchmark")
    print("=" * 60)
    
    scripts = load_scripts(CSV_PATH)
    print(f"Loaded {len(scripts)} scripts from {CSV_PATH}")
    
    results = []
    
    for script_data in scripts:
        ad_name = script_data["ad"]
        is_hoax = script_data["is_hoax"]
        script = script_data["script"]
        
        print(f"\n--- Testing: {ad_name} (isHoax={is_hoax}) ---")
        
        for model_config in MODELS:
            model_name = model_config["name"]
            provider = model_config["provider"]
            model = model_config["model"]
            
            print(f"  [{model_name}] Running...", end=" ", flush=True)
            
            result = await run_single_test(provider, model, script)
            result["ad"] = ad_name
            result["is_hoax"] = is_hoax
            
            print(f"Done ({result['duration']:.2f}s, valid={result['json_valid']}, level={result['reliability_level']})")
            
            results.append(result)
    
    # Save results
    with open(OUTPUT_PATH, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["ad", "is_hoax", "provider", "model", "duration", "json_valid", "reliability_level", "error"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\n✅ Results saved to {OUTPUT_PATH}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for model_config in MODELS:
        model_name = model_config["name"]
        model_results = [r for r in results if r["provider"] == model_config["provider"] and r["model"] == (model_config["model"] or "gemini-3-flash")]
        
        avg_time = sum(r["duration"] for r in model_results) / len(model_results) if model_results else 0
        json_valid_count = sum(1 for r in model_results if r["json_valid"])
        
        print(f"[{model_name}]")
        print(f"  Avg Time: {avg_time:.2f}s")
        print(f"  JSON Valid: {json_valid_count}/{len(model_results)}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
