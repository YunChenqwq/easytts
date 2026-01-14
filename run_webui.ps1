$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

# Use the system proxy (if present) but force an explicit scheme for Python.
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:NO_PROXY = ""

chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& .\.venv\Scripts\python .\app.py

