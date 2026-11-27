"""viki_rag 包入口：确保 torch 早于 pymilvus/pandas/pyarrow 加载。

原因（2026-11-02 实测）：pyarrow 包内自带 msvcp140.dll，一旦 pandas/pyarrow 先被
pymilvus 拉起来，Windows 会优先解析到 pyarrow 附带的这份运行库，随后 torch 加载
`torch/lib/c10.dll` 时报 [WinError 1114] 动态链接库初始化失败。反过来先 import torch
则一切正常（pymilvus 用在同一进程后续也没问题）。因为所有 `from app.x import y` 都会
先执行本模块，这里集中排一次序即可覆盖全部入口（CLI / API / 脚本）。

无 torch 的环境（只装轻量依赖）静默跳过，不影响不依赖向量层的命令。
"""
try:
    import torch  # noqa: F401  # 必须先于 pymilvus/pandas/pyarrow，勿调整位置
except Exception:  # pragma: no cover - 无 torch 环境下的降级
    pass
