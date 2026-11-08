# Screenshots the mock at the two sign-off viewports, plus ?measure frames that
# print the geometry of every section so overflow is a number, not a guess.
#   pwsh -File _build\capture.ps1 [-m]
#
# Chrome sizes the *window*, and what that does to the layout viewport depends
# on window frame and scrollbar state, so the page is framed in an iframe of
# exactly the target size: the iframe's viewport is then 1440x1000 / 390x844 no
# matter what the window does. The frame sits at the wrapper's top-left corner,
# so cropping (0,0,w,h) yields exactly the page.
$ErrorActionPreference = "Continue"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$v2 = Split-Path -Parent $here
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$python = "C:\Users\joe\Desktop\工作学习\study 2026-2027 sem1\EIE4428-Multimedia-Communications\mini-project\EIE4428-RVM\EIE4428-RVM\.venv\Scripts\python.exe"

function Shot($w, $h, $file, $query) {
  $png = if ($file.StartsWith("_")) { Join-Path $here $file } else { Join-Path $v2 $file }
  if (Test-Path $png) { Remove-Item $png -Force }

  $wrap = Join-Path $here "_wrap.html"
  $html = "<!DOCTYPE html><meta charset='utf-8'><style>html,body{margin:0;background:#000;overflow:hidden}" +
          "iframe{display:block;width:${w}px;height:${h}px;border:0}</style>" +
          "<iframe src='../mock.html$query'></iframe>"
  [System.IO.File]::WriteAllText($wrap, $html, (New-Object System.Text.UTF8Encoding($false)))

  $uri = ([System.Uri]$wrap).AbsoluteUri
  & $chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
    --window-size="$($w + 40),$($h + 120)" --virtual-time-budget=5000 `
    "--user-data-dir=$(Join-Path $env:TEMP ("rvm-mock-" + [guid]::NewGuid().ToString("N").Substring(0,10)))" `
    "--screenshot=$png" "$uri" 2>&1 | Out-Null
  if (-not (Test-Path $png)) { throw "chrome produced no $file" }

  & $python -c "import sys,os;from PIL import Image;p=sys.argv[1];Image.open(p).crop((0,0,$w,$h)).save(p);im=Image.open(p);print('%s: %dx%d, %d bytes' % (sys.argv[2], im.width, im.height, os.path.getsize(p)))" $png $file
}

Shot 1440 1000 "mock-desktop.png" ""
Shot 390 844 "mock-mobile.png" ""
if ($args -contains "-m") {
  Shot 1440 1000 "_measure-desktop.png" "?measure"
  Shot 390 844 "_measure-mobile.png" "?measure"
}

