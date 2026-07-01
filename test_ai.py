import time
from ollama import chat

start = time.time()

response = chat(
    model="qwen3.5:9b",
    messages=[
        {
            "role": "user",
            "content": "Say hello"
        }
    ]
)

end = time.time()

print(response["message"]["content"])
print(f"Time: {end-start:.2f} sec")