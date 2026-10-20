@echo off
cd /d %~dp0
echo 启动 viki_rag 服务（端口 8100，前端已构建到 web/dist）...
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8100
