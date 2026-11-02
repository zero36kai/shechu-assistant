param(
    [Parameter(Mandatory)]
    [ValidateSet('Install', 'Remove')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$startupFolder = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder 'WaterAssistantV2.lnk'
$oldShortcutPath = Join-Path $startupFolder 'WaterPetReminder.lnk'

if ($Action -eq 'Remove') {
    foreach ($path in @($shortcutPath, $oldShortcutPath)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
    $dataFolder = Join-Path $projectRoot 'data'
    if (Test-Path -LiteralPath $dataFolder) {
        Set-Content -LiteralPath (Join-Path $dataFolder 'heartbeat.stop') -Value 'autostart disabled' -Encoding utf8
    }
    Write-Output '已取消 V2 开机自启并停止心跳；当前助手可从托盘退出。'
    exit 0
}

$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$entryPath = Join-Path $projectRoot 'run_v2.py'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $entryPath)) {
    throw 'V2 环境或入口缺失，请先按 README.md 配置环境。'
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '-B "{0}" --heartbeat' -f $entryPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = '社畜小助手 · 60秒心跳保活'
$shortcut.WindowStyle = 7
$shortcut.Save()
if (Test-Path -LiteralPath $oldShortcutPath) { Remove-Item -LiteralPath $oldShortcutPath }
Write-Output '已设置 V2 开机自启与60秒心跳，下次登录后安静留在托盘。'
