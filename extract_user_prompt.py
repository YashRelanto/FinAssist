import json

transcript_path = r"C:\Users\Relanto\.gemini\antigravity-ide\brain\8aadd4db-74b4-46d4-97ad-fc7e242cff97\.system_generated\logs\transcript.jsonl"
last_user_message = ""

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            entry = json.loads(line)
            if entry.get("type") == "USER_INPUT":
                content = entry.get("content", "")
                if "Orchestration & Workflow Refactor" in content:
                    last_user_message = content
        except Exception:
            pass

with open("user_request.txt", "w", encoding="utf-8") as f:
    f.write(last_user_message)
