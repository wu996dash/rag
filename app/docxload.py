"""官方 docx 原文抽取（零依赖：zipfile + ElementTree）。sources 只读，本模块不写回。"""
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
@lru_cache(maxsize=8)
def docx_text(relpath: str) -> str:
    from . import config
    path = config.REPO / relpath
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("word/document.xml"))
    paras = ["".join(t.text or "" for t in p.iter(NS + "t")) for p in root.iter(NS + "p")]
    return "\n".join(p for p in paras if p.strip())