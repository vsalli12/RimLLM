$ErrorActionPreference = 'Stop'
$condaPython = Join-Path $env:USERPROFILE 'miniconda3\envs\default\python.exe'
$receiverScript = Join-Path $PSScriptRoot 'receiver.py'
if (Test-Path -LiteralPath $condaPython) {
    & $condaPython -X utf8 $receiverScript
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -X utf8 $receiverScript
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -X utf8 $receiverScript
} else {
    throw 'Python 3.10 or later is required. Install Python, then run this script again.'
}
