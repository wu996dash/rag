# -*- coding: utf-8 -*-
from app.pages import render
from app.vectors import upsert_articles
tot = {}
for k, lo, hi in [("劳动法",1,107),("调解仲裁法",1,54),("劳动争议解释一",1,54),("劳动争议解释二",1,21),("工伤保险条例",1,67)]:
    tot[k] = (render(k, lo, hi), upsert_articles(k, lo, hi))
    print(k, "pages:", tot[k][0], "rows:", tot[k][1], flush=True)
from app.concepts import generate_one
TOPICS = [
 {"title":"工时与加班费","slug":"gongshi-jiabanfei","ranges":[("劳动法",36,44)]},
 {"title":"带薪年休假权利","slug":"dai-xin-nian-xiujia","ranges":[("劳动法",45,45)]},
 {"title":"劳动争议处理程序","slug":"laodong-zhengyi-chengxu","ranges":[("调解仲裁法",2,10)]},
 {"title":"劳动仲裁时效","slug":"laodong-zhongcai-shixiao","ranges":[("调解仲裁法",27,27),("劳动争议解释一",3,3)]},
 {"title":"竞业限制补偿与效力","slug":"jingye-xianzhi-buchang","ranges":[("劳动合同法",23,24),("劳动争议解释一",36,40),("劳动争议解释二",13,15)]},
 {"title":"工伤认定","slug":"gongshang-rending","ranges":[("工伤保险条例",14,17)]},
 {"title":"工伤保险待遇","slug":"gongshang-daiyu","ranges":[("工伤保险条例",30,45)]},
]
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=4) as ex:
    for t, r in zip(TOPICS, ex.map(generate_one, TOPICS)):
        print("制度页:", t["title"], "->", r[1], flush=True)
from app.conceptnav import build
print("导航重建:", build(), "页")
