"""日志系统：logs/app.log（INFO 运行流水）+ logs/error.log（ERROR 及以上含堆栈）。
按天轮转、保留 14 天、UTF-8；uvicorn 日志并入同一目录。rid 用于串联单次问答全链路。"""
import logging
from logging.handlers import TimedRotatingFileHandler
from . import config
LOGDIR = config.REPO / "logs"
_FMT = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s", "%Y-%m-%d %H:%M:%S")
_ready = False
class _Scrub(logging.Filter):
    """脱敏：日志里的 token=xxx 一律打码（访问日志会带 WS query）。"""
    import re as _re
    _pat = _re.compile(r"(token=)[0-9a-fA-F]{8,}")
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if self._pat.search(msg):
            record.msg = self._pat.sub(r"\1***", msg)
            record.args = ()
        return True
def _handler(name, level):
    h = TimedRotatingFileHandler(LOGDIR / f"{name}.log", when="midnight", backupCount=14, encoding="utf-8")
    h.suffix = "%Y-%m-%d"
    h.setFormatter(_FMT)
    h.setLevel(level)
    return h
def setup():
    global _ready
    if _ready:
        return
    LOGDIR.mkdir(exist_ok=True)
    root = logging.getLogger("viki")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(_handler("app", logging.INFO))
    root.addHandler(_handler("error", logging.ERROR))
    root.addFilter(_Scrub())
    root.propagate = False
    for n in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(n)
        lg.handlers = root.handlers
        lg.addFilter(_Scrub())
        lg.propagate = False
    _ready = True
def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger("viki." + name)