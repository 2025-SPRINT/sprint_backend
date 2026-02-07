"""
Quick script to capture Ollama responses for specific ads
"""
import asyncio
import csv
import json
from datetime import datetime

from ollama_main import main as ollama_analyze

# Target ads
TARGET_ADS = ["삼양 스페셜티", "페이커", "비문증", "아이지에프업"]
MODELS = ["exaone-deep:7.8b", "qwen3:8b"]

def load_scripts(path: str) -> dict:
    scripts = {}
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scripts[row["ad"]] = row["script"]
    return scripts

async def capture_responses():
    scripts = load_scripts("scripts.csv")
    results = {}
    
    for ad_name in TARGET_ADS:
        if ad_name not in scripts:
            print(f"❌ {ad_name} not found in scripts.csv")
            continue
            
        script = scripts[ad_name]
        results[ad_name] = {}
        
        for model in MODELS:
            print(f"\n🔄 {ad_name} - {model}...")
            response = await ollama_analyze("", script, model_name=model)
            
            # Parse JSON
            try:
                data = json.loads(response)
                results[ad_name][model] = data
            except:
                results[ad_name][model] = {"raw": response}
            
            print(f"✅ Done")
    
    # Save to file
    output_path = f"ollama_responses_{datetime.now().strftime('%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 Saved to {output_path}")
    
    # Also print formatted output
    for ad_name, models in results.items():
        print(f"\n{'='*60}")
        print(f"## {ad_name}")
        print(f"{'='*60}")
        for model, data in models.items():
            print(f"\n### {model}")
            if isinstance(data, dict) and "reliability_level" in data:
                print(f"- 등급: {data.get('reliability_level')}")
                print(f"- 요약: {data.get('summary')}")
                print(f"- 문제점: {data.get('issues')}")
                if data.get('patent_check'):
                    print(f"- 특허: {data.get('patent_check')}")
                print(f"- 조언: {data.get('consultation')}")
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(capture_responses())
