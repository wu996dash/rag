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
def chat_stream(messages, temperature=0.3, max_tokens=1400, timeout=150):
    """SSE 流式：逐段 yield 增量文本（首 token 即回显，改善体感延迟）。"""
    body = {"model": config.LLM_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": True}
    req = urllib.request.Request(
        config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json", "Accept": "text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                d = json.loads(payload)
            except Exception:
                continue
            ch = (d.get("choices") or [{}])[0]
            delta = (ch.get("delta") or {}).get("content") or ch.get("text") or ""
            if delta:
                yield delta
