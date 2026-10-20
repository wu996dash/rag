# -*- coding: utf-8 -*-
from pathlib import Path
p = Path("README.md"); s = p.read_text(encoding="utf-8")
s = s.replace('python -m app.eval_full                                  # 全量四维评测',
"""python -m app.eval_full                                  # 全量四维评测（65题约6分钟，3并发）
python -m app.eval_full --only 时效,J --workers 3        # 增量评测：按题目id/文件名过滤""")
s = s.replace("- chat 常驻会话热态单题 ~10s（大头变为 qwen-plus 生成 8-12s，流式首字 ~2-3s）；冷启动一次 ~25s",
"- chat 常驻会话热态单题 ~10s（大头变为 qwen-plus 生成 8-12s，流式首字 ~2-3s）；冷启动一次 ~25s\n- 全量评测（65 题）324s / 3 并发；评测引擎含模型预热、429 指数退避、失败重排队")
p.write_text(s, encoding="utf-8")
d = Path("DECISIONS.md"); s = d.read_text(encoding="utf-8")
s += """

## D12 评测吞吐（2026-10-20）—— 并行化 + 限流治理

- 定案：评测引擎 ThreadPool 并行（workers=3，GPU 前向加锁串行）+ 进程内模型预热 + 429 指数退避（retries=5）+ 失败题二轮重排队 + `--only` 增量过滤。全量 65 题 957s → 324s（2.9x）。
- 教训：判官模型曾尝试降级 qwen-turbo（快 3-5x），实测该账号 turbo 独立限速直接 429，判官保持 qwen-plus，模型名走 LLM_MODEL_JUDGE 可配置。
- 附带修复：REF 校验支持法律全称→简称映射（修 J-004 假阴性）。
"""
d.write_text(s, encoding="utf-8")
a = Path("eval/results/m5-v1-acceptance.md"); s = a.read_text(encoding="utf-8")
s += """

## M6 追加（2026-10-20，司法解释+案例入库后）
- 语料扩至 218+21 条条文页/26 制度页/2 案例页，65 题（+G-045 +J-001~006）
- R5b 全量（含两处修复复验）：正确率 100%、引用精确率 100%、无据拒答 100%、时效违规 0；评测 324s（并行引擎）
- 判定维持：**v1 验收通过**；时效制度组现为"法条+司法解释+传导更新"三层闭环（案例仍缺诉讼时效对口指导案例）
"""
a.write_text(s, encoding="utf-8")
import subprocess
subprocess.run(["git","add","-A"], cwd=".", check=True)
subprocess.run(["git","commit","-q","-m","评测引擎并行化（65题 957s→324s）：预热/429退避/重排队/--only 增量；修 REF 全称映射；D12 与验收报告更新"], check=True)
print(subprocess.run(["git","log","--oneline","-3"], capture_output=True, text=True).stdout)
print(subprocess.run(["git","status","--short"], capture_output=True, text=True).stdout or "工作树干净")
