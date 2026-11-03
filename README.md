# 社畜小助手

Windows 桌面上的喝水、提肛提醒伙伴。八位 Q 版角色轮流出现，可以移动、缩放，分别打卡，并查看本机记录。

![提醒预览](docs/evidence/V2提醒动作预览.webp)

预览由实际控件和动画帧离屏导出。

## 启动

需要 Windows、Python 3.13 和 PowerShell 7（`pwsh`）。在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

双击 `启动社畜小助手.bat` 打开控制面板并启用心跳。关闭面板后仍留在托盘；托盘菜单可以显示提醒、查看历史、暂停或退出。重复启动会打开已有实例。

`install_startup.bat` 设置登录自启，登录后安静留在托盘；`remove_startup.bat` 取消自启并停止心跳。移动项目目录后需重新设置自启。

## 使用

- 每轮提醒随机出场，八位角色一轮不重复；「角色与外观」可点击预览。
- 拖动角色移动提醒，滚轮或 `＋ / −` 调整大小。左上方气泡、文字和按钮与角色一起缩放，位置与大小会保存。
- 「喝好了」「提肛了」分别记录喝水和提肛，同一轮可以先后完成两项。再次点击已完成项可以撤销。
- 关闭、稍后和暂停不会生成完成记录。提醒可随时关闭，没有全屏遮罩。
- 历史页按实际完成日期显示明细；撤销保留痕迹，不计入完成次数。
- 可设置提醒间隔、时段、工作日、稍后和自动收起时间。自动收起设为 0 时不自动收起，仍可随时关闭。
- 锁屏、离开电脑、时段外或使用全屏应用时暂停自动计时。手动预览不受时段限制。

心跳每 60 秒通过本机 IPC 检查助手是否响应，进程异常退出后重新拉起；现有进程未响应时记录警告并重试。托盘主动「退出」会同时停止心跳，下次明确启动或登录后重新启用。

## 数据

设置和记录保存在项目内 `data/`：`settings.json`、`history.sqlite3`、日志和心跳状态。没有账号、云端同步或打卡上传。启用节假日识别时会请求在线日历服务；断网使用缓存或周一到周五规则。

备份前请从托盘退出，或使用 SQLite 备份接口。运行中数据库可能还有 WAL 文件，不要只复制主数据库。

## 开发与检查

入口为 `run_v2.py`，代码在 `water_assistant/`。使用独立目录检查，避免影响日常记录：

```powershell
.\.venv\Scripts\python.exe -B run_v2.py --data-dir .cache/manual-check --isolated --show
.\.venv\Scripts\python.exe -B run_v2.py --data-dir .cache/manual-check --command quit
```

自动化测试：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
New-Item -ItemType Directory -Path .cache -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp=.cache/test-first-run
```

每次测试使用新的 `--basetemp` 目录。真实进程与心跳验证需清除 `QT_QPA_PLATFORM`，然后运行：

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -B -m tools.verify_runtime .cache/runtime-first-run
.\.venv\Scripts\python.exe -B -m tools.verify_heartbeat .cache/heartbeat-first-run
```

心跳测试在隔离实例中使用 1 秒间隔，生产间隔为 60 秒。验证覆盖单实例、独立打卡、撤销留痕、存储故障、关闭退出、整体缩放及气泡与全部角色帧的像素碰撞。短时测试不代表长期常驻稳定性；真实多屏混合 DPI 和所有锁屏、休眠组合仍需观察。

## 许可与美术来源

源码采用 [MIT](LICENSE)。角色美术、气泡及其预览的许可说明见 [assets/v2/NOTICE.md](assets/v2/NOTICE.md)，其中角色衍生素材沿用 **CC BY-NC-SA 4.0**，不适用 MIT。依赖库遵循各自许可证。
