#!/bin/sh
# MCMtools 一键启动（macOS / Linux）。
#
# 用法：./start.sh 或 sh start.sh —— 文件权限丢失时（从压缩包解出来、
# 从 U 盘拷过来）这个入口仍然可用，不需要先 chmod。
#
# 它只是找到同目录的 start 并交给 Python，不包含任何自己的逻辑。
HERE="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$HERE/start" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$HERE/start" "$@"
else
  echo ""
  echo "  没有找到 Python 3。"
  echo ""
  echo "  MCMtools 需要 Python 3.9 或更新版本："
  echo "    macOS:  brew install python@3.12"
  echo "    Ubuntu: sudo apt install python3 python3-pip"
  echo ""
  exit 1
fi
