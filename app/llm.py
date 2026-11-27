"""LLM 统一入口（OpenAI 兼容；CLAUDE.md：不散写 HTTP，不硬编码 URL）。

失败语义约定（2026-10-22 加固）：
- 可重试错误（5xx / 429 / 网络抖动）：按退避重试；
- 不可重试错误（401/403 鉴权、404 端点或模型不存在）：立即抛出 AuthError，
  不做无效重试——否则要白等 5 轮退避才报错，且掩盖真实原因；
- 所有发起与失败都写日志（logs/app.log / error.log），不再静默。
"""
import json, urllib.request, urllib.error, time
from . import config
from .log import get

log = get("llm")

# 不可重试的 HTTP 状态：鉴权/权限/端点或模型不存在
_FATAL_CODES = {401, 403, 404}


class AuthError(RuntimeError):
    """鉴权或端点配置错误：重试无意义，必须让调用方看到。"""


def _key_hint():
    """key 是否就位的诊断线索（绝不打印 key 本身）。"""
    k = config.LLM_API_KEY
    if not k:
        return "LLM_API_KEY/DASHSCOPE_API_KEY 均未设置"
    return f"已设置（长度 {len(k)}）"


def _check_key():
    if not config.LLM_API_KEY:
        log.error("LLM 密钥缺失：%s；请在 .env 设 LLM_API_KEY 或系统环境变量 DASHSCOPE_API_KEY",
                  _key_hint())
        raise AuthError("LLM 密钥未配置")


def chat(messages, temperature=0.2, max_tokens=1600, timeout=150, retries=5, model=None):
    body = {"model": model or config.LLM_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(
        config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json"})
    import random
    last = None
    _check_key()
    mdl = model or config.LLM_MODEL
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            log.debug("chat ok model=%s attempt=%d elapsed=%.2fs", mdl, attempt, time.time() - t0)
            return d["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last = e
            if e.code in _FATAL_CODES:
                # 鉴权/端点是配置问题，重试只会浪费时间和掩盖原因
                log.error("LLM 不可重试错误 HTTP %s model=%s key=%s —— %s",
                          e.code, mdl, _key_hint(),
                          "检查密钥是否有效/是否过期" if e.code in (401, 403)
                          else "检查 LLM_BASE_URL 与 LLM_MODEL 是否存在")
                raise AuthError(f"LLM 配置错误 HTTP {e.code}") from e
            if e.code == 429:  # 限流：指数退避 + 抖动
                wait = min(40, 4 * (2 ** attempt)) + random.random() * 2
                log.warning("LLM 限流 429 model=%s attempt=%d/%d 等待 %.1fs",
                            mdl, attempt + 1, retries + 1, wait)
                time.sleep(wait)
            else:
                log.warning("LLM HTTP %s model=%s attempt=%d/%d 重试中",
                            e.code, mdl, attempt + 1, retries + 1)
                time.sleep(3)
        except Exception as e:
            last = e
            log.warning("LLM 调用异常 %r model=%s attempt=%d/%d 重试中",
                        e, mdl, attempt + 1, retries + 1)
            time.sleep(3)
    log.error("LLM 调用最终失败 model=%s 耗时 %.1fs 最后错误 %r key=%s",
              mdl, time.time() - t0, last, _key_hint())
    raise RuntimeError(f"LLM 调用失败: {last!r}")


def chat_stream(messages, temperature=0.3, max_tokens=1400, timeout=150, model=None):
    """SSE 流式：逐段 yield 增量文本（首 token 即回显，改善体感延迟）。"""
    _check_key()
    body = {"model": model or config.LLM_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": True}
    req = urllib.request.Request(
        config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json", "Accept": "text/event-stream"})
    mdl = model or config.LLM_MODEL
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in _FATAL_CODES:
            log.error("LLM 流式不可重试错误 HTTP %s model=%s key=%s", e.code, mdl, _key_hint())
            raise AuthError(f"LLM 配置错误 HTTP {e.code}") from e
        log.error("LLM 流式失败 HTTP %s model=%s", e.code, mdl)
        raise
    except Exception as e:
        log.error("LLM 流式连接失败 %r model=%s", e, mdl)
        raise
    with resp as r:
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
