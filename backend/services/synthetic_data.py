import os
import json
import httpx
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
from core.config import DATA_DIR

# Constants
DATASETS_DIR = os.path.join(DATA_DIR, "datasets")
os.makedirs(DATASETS_DIR, exist_ok=True)

class SyntheticDataRequest(BaseModel):
    topic: str
    count: int
    provider: str  # "openai" or "gemini"
    api_key: str
    system_prompt: Optional[str] = "You are a helpful assistant."
    edge_cases: Optional[str] = ""
    examples: Optional[List[dict]] = [] # [{"user": "...", "assistant": "..."}]

class GenerationStatus(BaseModel):
    status: str # "idle", "generating", "completed", "failed"
    completed_count: int
    total_count: int
    current_file: Optional[str] = None
    error: Optional[str] = None

# Global Status Tracker (Simple in-memory for POC)
current_job = {
    "status": "idle",
    "completed": 0,
    "total": 0,
    "file": None,
    "error": None
}

async def generate_synthetic_data(request: SyntheticDataRequest):
    global current_job
    current_job["status"] = "generating"
    current_job["total"] = request.count
    current_job["completed"] = 0
    current_job["error"] = None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"dataset_{request.topic.replace(' ', '_')}_{timestamp}.jsonl"
    filepath = os.path.join(DATASETS_DIR, filename)
    current_job["file"] = filename

    # Meta Prompt Construction
    meta_system_prompt = f"""
    You are an expert data generator for training LLMs.
    Your task is to generate diverse, high-quality conversation pairs (User query and Assistant response) for the topic: '{request.topic}'.
    
    Target Persona for Assistant:
    {request.system_prompt}
    
    Edge Cases and Constraints to handle:
    {request.edge_cases}
    
    Generate PRECISELY ONE conversation pair in JSON format:
    {{
        "messages": [
            {{"role": "user", "content": "..."}},
            {{"role": "assistant", "content": "..."}}
        ]
    }}
    Do not output markdown code blocks. Output ONLY the raw JSON object.
    """
    
    if request.examples:
        meta_system_prompt += "\n\nFollow this style from these examples:\n"
        for ex in request.examples:
            meta_system_prompt += f"User: {ex['user']}\nAssistant: {ex['assistant']}\n---\n"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(request.count):
                try:
                    content = ""
                    
                    if request.provider == "openai":
                        resp = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {request.api_key}"},
                            json={
                                "model": "gpt-4o",
                                "messages": [
                                    {"role": "system", "content": meta_system_prompt},
                                    {"role": "user", "content": f"Generate conversation #{i+1}."}
                                ],
                                "temperature": 0.7
                            }
                        )
                        resp.raise_for_status()
                        content = resp.json()["choices"][0]["message"]["content"]
                        
                    elif request.provider == "gemini":
                        # Simplification: Assuming API key works with standard Gemini endpoint or via a wrapper
                        # For POC, let's assume OpenAI format or similar if using a proxy, 
                        # otherwise raw Gemini API call structure:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={request.api_key}"
                        resp = await client.post(
                            url,
                            json={
                                "contents": [{
                                    "parts": [{"text": meta_system_prompt + f"\n\nGenerate conversation #{i+1}."}]
                                }]
                            }
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        content = data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # Cleanup JSON
                    json_str = content.strip()
                    if json_str.startswith("```json"):
                        json_str = json_str[7:-3]
                    elif json_str.startswith("```"):
                         json_str = json_str[3:-3]
                    
                    record = json.loads(json_str)
                    
                    # Append to file immediatey (streaming save)
                    with open(filepath, "a") as f:
                        f.write(json.dumps(record) + "\n")
                        
                    current_job["completed"] += 1
                    
                except Exception as e:
                    print(f"Error generating record {i}: {e}")
                    # Continue to next record even if one fails
                    continue

        current_job["status"] = "completed"
        
    except Exception as e:
        current_job["status"] = "failed"
        current_job["error"] = str(e)
        print(f"Job failed: {e}")
