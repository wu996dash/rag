@echo off
cd /d %~dp0
rem Start viki_rag web server on port 8100 (frontend prebuilt into web/dist).
rem The LLM key is read only from the process env var DASHSCOPE_API_KEY.
rem A freshly opened console may not inherit the User-scope variable, so read it
rem back from the registry once and inject it here (never written to disk).
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY','User')"`) do set "DASHSCOPE_API_KEY=%%K"
if "%DASHSCOPE_API_KEY%"=="" echo [WARN] DASHSCOPE_API_KEY not found - Q&A will report a missing key; other features still work.
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Serving viki_rag at http://127.0.0.1:8100
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8100
