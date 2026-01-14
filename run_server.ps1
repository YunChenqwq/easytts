$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

# Avoid UnicodeEncodeError on non-UTF8 consoles.
chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Use the system proxy (if present) but force an explicit scheme for Python.
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
$env:NO_PROXY = ""

& .\.venv\Scripts\python -c "import genie_tts as genie; genie.start_server(host='0.0.0.0', port=8000, workers=1)"
