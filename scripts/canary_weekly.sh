#!/usr/bin/env bash
# canary 周跑本地驱动脚本（post-phase5-audit §3[S4]/§6 处置 4）。
#
# 背景：test-plan.md §4 早就写了"频率：周跑（cron）"，但库内此前零自动化载体
# （无 CI、无 cron、`records/canary/` 只有 1 份手跑记录，见 post-phase5-audit）。
# 本脚本 + 同目录 com.papercrawler.canary-weekly.plist.template 是**模板**：
# 不常驻、不改 CI、不会自己把自己装进 launchd/cron——真正的定时调度需要你自己手动
# 接线（见下方"定时接入"或 docs/testing/records/canary/README.md 对应小节）。
#
# 做什么：cd 到仓库根 → `uv run crawler canary --record` → 按退出码留痕/尽力通知。
# `--record` 把健康矩阵落盘到 docs/testing/records/canary/<今日>-canary.md
# （canary.py `canary_record_path` 的既有语义：相对当前工作目录解析，故必须先 cd
# 到仓库根，不能假设调用者的 CWD）。本脚本**不会**自动 `git add`/`git commit`
# 该记录文件——是否入库、何时入库由你自己 review 决定（沿 docs/process/git-workflow.md
# §3 的一般原则：生成物不擅自入库，需人工过目）。
#
# 用法：
#   scripts/canary_weekly.sh                                   # 全部注册 adapter（真实网络）
#   scripts/canary_weekly.sh --adapter mock_platform            # 离线演练：零真实网络，
#                                                                 # 只验证本脚本自身逻辑
#   scripts/canary_weekly.sh --adapter mock_platform --record    # 离线演练 + 落盘路径也一并验证
#   scripts/canary_weekly.sh --home /path/to/alternate/home      # 覆盖 PAPER_CRAWLER_HOME
#
# 除 --record 由本脚本固定带上外，其余参数原样透传给 `crawler canary`（见
# `crawler canary --help`）。
#
# 退出码：原样沿用 `crawler canary`——0 全部 healthy（SKIP 不影响）；1 至少一个
# unhealthy；2 用法错（如 --adapter 给了未注册 id）；其余非 0 视为异常（如 uv/环境
# 故障）。cron/launchd 均以本脚本最终退出码判定这次运行是否"成功"。
#
# 定时接入（手动二选一——本脚本不会替你自动安装）：
#   - launchd（macOS）：复制同目录 com.papercrawler.canary-weekly.plist.template，
#     把里面的 __REPO_ROOT__/__HOME__ 占位符换成你的真实路径后另存为
#     ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist，
#     再 `launchctl load ~/Library/LaunchAgents/com.papercrawler.canary-weekly.plist`。
#     完整步骤见 docs/testing/records/canary/README.md。
#   - cron（Linux/macOS 均可，crontab -e 里加一行）：
#       0 3 * * 0 /absolute/path/to/paper-crawler/scripts/canary_weekly.sh \
#         >> "$HOME/.paper-crawler/logs/canary-weekly.log" 2>&1
#     （周日 03:00 本地时间——test-plan.md §5"auth 族 canary 每周一次且避开工作日
#     高峰"的保守选择；改成任何你喜欢的时间都可以，cron 语法自理。）
#
# 失败通知：退出码非 0 时，macOS 下尽力弹一条本地桌面通知（系统自带 `osascript`，
# 零额外依赖、无需联网）；非 macOS 或无 GUI 会话（如无头 Linux 服务器跑 cron）时
# 该步骤静默跳过，只留 stdout/stderr 里的失败标记行——如需邮件/IM/webhook 通知，
# 请在下方 `_notify_extra` 函数体内按注释接入你自己的通道；本脚本默认不会代你向
# 任何第三方服务发起网络请求。

set -uo pipefail
# 注意：故意不加 `set -e`——下面需要在不中断脚本的前提下捕获 `crawler canary`
# 的真实退出码（0/1/2 都是"正常"的业务结果，只有捕获后才能分支处理/透传）。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

_ts() {
  date '+%Y-%m-%d %H:%M:%S%z'
}

_notify_extra() {
  # 在此接入你自己的失败通知通道（缺省不做任何事——不假设你有 mail/webhook 可用，
  # 也不代你向任何未经确认的第三方地址发请求）。参考写法：
  #
  #   mail -s "paper-crawler canary 周跑发现异常" you@example.org <<<"$1"
  #
  #   curl -fsS -X POST -H 'Content-Type: application/json' \
  #     -d "{\"text\": \"$1\"}" "${CANARY_WEBHOOK_URL:?set CANARY_WEBHOOK_URL first}"
  :
}

_notify() {
  local message="$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"paper-crawler canary\" with title \"canary 周跑\"" \
      >/dev/null 2>&1 || true
  fi
  _notify_extra "${message}"
}

if ! command -v uv >/dev/null 2>&1; then
  echo "[$(_ts)] [canary-weekly] 找不到 uv 命令——请先安装 uv（https://docs.astral.sh/uv/），" \
    "或改本脚本直接调用已安装的 crawler 可执行文件。" >&2
  exit 127
fi

echo "[$(_ts)] [canary-weekly] 开始（repo: ${REPO_ROOT}）"

(cd "${REPO_ROOT}" && uv run crawler canary --record "$@")
exit_code=$?

case "${exit_code}" in
  0)
    echo "[$(_ts)] [canary-weekly] 完成：全部 healthy（SKIP 不影响判定），退出码 0。"
    ;;
  1)
    echo "[$(_ts)] [canary-weekly] 完成：发现 unhealthy adapter，退出码 1——请查看上方健康矩阵" \
      "与 docs/testing/records/canary/ 下新落的记录文件。" >&2
    _notify "canary 周跑发现 unhealthy adapter（退出码 1），请查看记录文件。"
    ;;
  *)
    echo "[$(_ts)] [canary-weekly] 异常退出码 ${exit_code}（非 0/1，可能是用法错或环境故障）。" >&2
    _notify "canary 周跑异常退出（退出码 ${exit_code}），请查看日志。"
    ;;
esac

exit "${exit_code}"
