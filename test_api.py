import urllib.request
import json

try:
    req = urllib.request.Request("http://localhost:8000/api/v1/review/history")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        if data.get("history"):
            summary = data["history"][0].get("summary", "")
            print("Summary length:", len(summary))
            print("Contains \\n:", "\\n" in summary or "\n" in summary)
            print("Summary Snippet:")
            print(repr(summary[-300:]))
        else:
            print("No history found.")
except Exception as e:
    print("Error:", e)
