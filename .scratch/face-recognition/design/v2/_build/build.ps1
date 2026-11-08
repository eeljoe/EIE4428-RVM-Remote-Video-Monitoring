# Builds ../mock.html from mock.tpl.html plus the two base64 frames.
# Run from anywhere:  pwsh -File _build\build.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$v2 = Split-Path -Parent $here

$frame = (Get-Content (Join-Path $here "_frame.b64") -Raw).Trim()
$thumb = (Get-Content (Join-Path $here "_thumb.b64") -Raw).Trim()

$html = Get-Content (Join-Path $here "mock.tpl.html") -Raw
$html = $html.Replace("{{FRAME}}", $frame).Replace("{{THUMB}}", $thumb)

$out = Join-Path $v2 "mock.html"
[System.IO.File]::WriteAllText($out, $html, (New-Object System.Text.UTF8Encoding($false)))
"{0} bytes -> {1}" -f (Get-Item $out).Length, $out
