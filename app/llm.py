"""LLM 统一入口（OpenAI 兼容；CLAUDE.md：不散写 HTTP，不硬编码 URL）。"""
import json, urllib.request, time
from . import config
def chat(messages, temperature=0.2, max_tokens=1600, timeout=150, retries=2):
    body = {"model": config.LLM_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(
        config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json"})
    last = None
    for _ in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d["choices"][0]["message"]["content"]
        except Exception as e:
            last = e; time.sleep(3)
    raise RuntimeError(f"LLM 调用失败: {last!r}")