---
title: Canary 健康矩阵记录目录
status: approved
owner: fable5
updated: 2026-07-26
---

# Canary 记录

本目录存放 `crawler canary --record` 生成的 adapter 健康矩阵快照，供追踪各 adapter 随时间的健康趋势。
文件名 `<YYYY-MM-DD>-canary.md`（本地日期，同日重复执行覆盖同名文件，不追加）；单个文件不带 front matter——见 [canary.py](../../../../src/paper_crawler/canary.py) `render_canary_record` docstring 的理由。

## 本地周跑自动化（launchd/cron 模板）

[test-plan.md §4](../../test-plan.md#4-canary站点漂移的哨兵t5-常态化) 早就写了"频率：周跑（cron）"，但在
post-phase5-audit（2026-07-24）之前，库内对此**零自动化载体**——无 CI、无 cron，本目录此前只有
一份手跑记录。以下两个文件是该缺口的模板化补齐（post-phase5-audit §3[S4]/§6 处置 4）：

| 文件 | 用途 |
|---|---|
| [`scripts/canary_weekly.sh`](../../../../scripts/canary_weekly.sh) | 实际执行的驱动脚本：`cd` 到仓库根 → `uv run crawler canary --record` → 按退出码留痕 / 尽力发一条本地失败通知。 |
| [`scripts/com.papercrawler.canary-weekly.plist.template`](../../../../scripts/com.papercrawler.canary-weekly.plist.template) | macOS launchd 的**模板**（含占位符，需手动替换后另存/安装）。 |

**红线声明**：这两个文件本身**不会**把自己装进 launchd/cron，也不修改任何 CI 配置——不常驻、
不自动安装。是否启用、何时启用，由你自己决定并手动执行下面的步骤。

### 手动演练（离线，验证脚本本身，不接触真实站点）

```bash
scripts/canary_weekly.sh --adapter mock_platform            # 只探测内置 mock adapter，零真实网络
scripts/canary_weekly.sh --adapter mock_platform --record    # 同上，额外验证 --record 落盘路径
```

`mock_platform` 的 `healthcheck()` 是纯 Python 桩（继承 `AdapterBase` 默认 `healthy=True`、
零 I/O），用它可以在不触碰任何真实网络的前提下确认脚本本身的逻辑（路径解析、退出码分支、
失败通知触发）工作正常。**省略 `--adapter` 时脚本会检查全部已注册 adapter**——这才是每周
真正要跑的形态，但会对多个真实站点发起请求（沿用各 adapter 自身已有的限速与 UA 身份声明，
非绕过；见各 adapter 设计文档），不建议在演练时使用。

### 手动接入 launchd（macOS）

1. 复制模板并替换占位符（`__REPO_ROOT__` 换成本机 clone 的绝对路径、`__LOG_DIR__` 换成你想
   存日志的目录，建议 `$PAPER_CRAWLER_HOME/logs`——D-032 后即仓库根 `.paper-crawler/logs`，
   需自行 `mkdir -p`）：

   ```bash
   mkdir -p "$PAPER_CRAWLER_HOME/logs"
   sed -e "s#__REPO_ROOT__#$(pwd)#g" -e "s#__LOG_DIR__#$PAPER_CRAWLER_HOME/logs#g" \
     scripts/com.papercrawler.canary-weekly.plist.template \
     > ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist
   ```

2. 加载：

   ```bash
   launchctl load ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist
   ```

   之后每周日本地时间 03:00（`test-plan.md §5`"避开工作日高峰"的保守选择；plist 里改
   `Hour`/`Minute`/`Weekday` 三个整数即可调整）自动跑一次。`RunAtLoad` 故意设为 `false`——
   不希望每次登录/重启都意外触发一次面向多个真实站点的请求。

3. 卸载：

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist
   rm ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist
   ```

### 手动接入 cron（Linux/macOS 均可）

`crontab -e` 加一行（同样是周日 03:00，按需调整）：

```cron
0 3 * * 0 /absolute/path/to/paper-crawler/scripts/canary_weekly.sh >> "$HOME/.paper-crawler/logs/canary-weekly.log" 2>&1
```

### 失败通知

脚本退出码非 0（发现 unhealthy，或用法错/环境故障）时：

- macOS 下会尽力弹一条本地桌面通知（系统自带 `osascript`，零额外依赖、不联网）；
- 非 macOS、或 launchd/cron 跑在无 GUI 会话下（例如无头 Linux 服务器）时该步骤静默跳过，
  只留 stdout/stderr 里清晰标记的失败行——如需邮件 / IM / webhook 通知，在
  `scripts/canary_weekly.sh` 的 `_notify_extra` 函数体内按注释接入你自己的通道；脚本默认
  不会代你向任何未经确认的第三方地址发起网络请求。

### 落盘后的记录文件

`--record` 生成的 `<今日>-canary.md` 会落在本目录（相对仓库根解析，故脚本必须先 `cd` 到仓库
根——`canary.py` `canary_record_path` 的既有语义）。**脚本不会自动 `git add`/`git commit`
该文件**——是否将其纳入版本历史、多久清理一次旧快照，由你 review 后自行决定（沿
[git-workflow.md §3](../../../process/git-workflow.md) 的一般原则：生成物不擅自入库，需人工过目）。
