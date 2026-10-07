param(
    [string]$PythonExecutable = ''
)

# 在项目虚拟环境中测试、编译并生成可分发的完整压缩包。
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw '请先创建虚拟环境并安装 requirements.txt 和 pyinstaller。'
}
$versionSource = Get-Content -LiteralPath (Join-Path $projectRoot 'app\version.py') -Encoding UTF8 -Raw
if ($versionSource -notmatch 'VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
    throw 'app/version.py 需要填写正式版本号。'
}
$releaseVersion = $Matches[1]
$buildId = 'local-v' + $releaseVersion + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$outputRoot = Join-Path $projectRoot ('dist\' + $buildId)
$workRoot = Join-Path $projectRoot ('build\' + $buildId)
$previousConsoleBuild = $env:JEV_BUILD_CONSOLE
$env:JEV_BUILD_CONSOLE = '0'
Push-Location -LiteralPath $projectRoot
try {
    & $PythonExecutable -X utf8 -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw '自动化测试失败，已停止编译。' }
    & $PythonExecutable -X utf8 -m core.draft
    if ($LASTEXITCODE -ne 0) { throw '候选解析检查失败，已停止编译。' }
    & $PythonExecutable -X utf8 -m PyInstaller --noconfirm --distpath $outputRoot --workpath $workRoot jev.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 编译失败。' }
    $packageRoot = Join-Path $outputRoot 'jev-chat-windows'
    $executablePath = Join-Path $packageRoot 'jev-chat-windows.exe'
    if (-not (Test-Path -LiteralPath $executablePath)) { throw '未生成可执行文件。' }
    Copy-Item -LiteralPath LICENSE, NOTICE, README.md -Destination $packageRoot
    $docsRoot = Join-Path $packageRoot 'docs'
    New-Item -ItemType Directory -Path $docsRoot | Out-Null
    Copy-Item -LiteralPath docs/ui_intent.png, docs/ui_openai_models.png, docs/ui_draft.png -Destination $docsRoot
    $archivePath = Join-Path $outputRoot ('jev-chat-windows-v' + $releaseVersion + '.zip')
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $archivePath
    Write-Output ('发布包：' + $archivePath)
    Get-FileHash -LiteralPath $archivePath -Algorithm SHA256 | Format-List
} finally {
    $env:JEV_BUILD_CONSOLE = $previousConsoleBuild
    Pop-Location
}
