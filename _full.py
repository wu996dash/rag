from app.pages import render
print("条文页生成:", render("民法典", 205, 1260))
from app.vectors import upsert_articles
print("向量嵌入:", upsert_articles("民法典", 205, 1260), "行")
