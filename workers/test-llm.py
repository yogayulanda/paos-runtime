from openai import OpenAI

env = {}
with open("/home/ubuntu/paos/runtime/.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env[k] = v

client = OpenAI(
    api_key=env.get("LLM_API_KEY", "local"),
    base_url=env["LLM_BASE_URL"],
)

response = client.chat.completions.create(
    model=env["LLM_MODEL"],
    messages=[
        {"role": "user", "content": "Reply only: PAOS LLM connected"}
    ],
)

print(response.choices[0].message.content)
