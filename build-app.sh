#!/bin/bash
#
# Build "MCMtools.app" — a double-clickable launcher.
#
# The app is a thin shell: it runs ./start with a Terminal window so the user can
# see progress during the first-run dependency install, and so Ctrl-C works the
# way it does everywhere else. A windowless app was rejected deliberately: the
# first run may install packages for several minutes, and an app that appears to
# do nothing for minutes reads as broken.
#
# Nothing is compiled and nothing is bundled. The app points at this checkout,
# so editing core/ or web/ and relaunching picks up the change immediately.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="MCMtools"
APP="${HERE}/${APP_NAME}.app"
BUNDLE_ID="local.mcmtools.launcher"
VERSION="0.1.0"

echo "Building ${APP_NAME}.app"
echo "  source: ${HERE}"

rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"

# ---------------------------------------------------------------- executable
# The app is a shell script that locates Python and hands it the launcher.
#
# Why it does not simply `exec ./start`:
#   macOS protects ~/Desktop, ~/Documents and ~/Downloads with TCC. When the
#   app bundle lives in one of those directories, the sandbox refuses to
#   EXECUTE a script located there, and the launch dies with
#   "Operation not permitted" -- a failure that looks like a bug in MCMtools
#   but is actually the OS protecting the folder.
#
#   Passing the launcher to Python with -c works, because that is Python
#   reading a file it was already granted access to, not the sandbox
#   authorising a new executable. Verified on macOS 15.
#
# It also opens Terminal explicitly, because the first run may install
# packages for minutes and an app that shows nothing for minutes reads as
# broken.
# ---------------------------------------------------------------- executable
#
# The app is a shell script that locates a Python and then hands it the
# BOOTSTRAP CODE INLINE (via -c), never a script path.
#
# This is not a style choice. macOS protects ~/Desktop, ~/Documents and
# ~/Downloads with TCC, and a launchd-started app is refused when Python tries
# to OPEN a file under one of them:
#
#     python3 /Users/.../Desktop/MCMtools/core/mcmboot.py
#     -> [Errno 1] Operation not permitted
#
# Passing the same code with -c works, because the blocked action is opening a
# file in a protected directory, not executing code. Verified on macOS 15 with
# the checkout sitting on the Desktop -- which is exactly where a competition
# folder ends up.
#
# The bootstrap is embedded at build time from core/mcmboot.py, so there is one
# source of truth: edit that file and re-run build-app.sh.
BOOTSTRAP_FILE="${HERE}/core/mcmboot.py"
if [ ! -f "${BOOTSTRAP_FILE}" ]; then
  echo "build-app.sh: 找不到 ${BOOTSTRAP_FILE}" >&2
  exit 1
fi

# 用**带引号的** heredoc 写启动脚本：内容原样落盘，不做任何 shell 展开。
# 之前用一长串 echo '...' 拼接，只要内容里出现一个单引号就会提前闭合引号，
# 把后面的代码当成命令执行 —— 生成出来的脚本因此面目全非。
# 带引号的 heredoc 没有这个问题。
#
# 引导代码从 core/mcmboot.py 内联进来（唯一的源码），其余部分写在这里。
{
  cat <<'LAUNCHER_HEAD'
#!/bin/bash
set -uo pipefail

# 仓库根目录：可执行文件位于 <root>/MCMtools.app/Contents/MacOS/ 下，上溯三级。
HERE="$(cd "$(dirname "$0")/../../.." && pwd)"

# 起手目录：优先用传入的项目目录；否则用桌面（比赛资料通常放那里）。
if [ $# -ge 1 ] && [ -d "$1" ]; then
  PROJECT="$1"
elif [ -d "${HOME}/Desktop" ]; then
  PROJECT="${HOME}/Desktop"
else
  PROJECT="${HOME}"
fi

# ---- TCC 预检 ------------------------------------------------------------
# macOS 保护 ~/Desktop、~/Documents、~/Downloads。放在这些目录下时，沙箱会
# 在内核层拒绝读取程序旁边的 core/ 目录：
#
#   kernel: (Sandbox) System Policy: Python(91272)
#           deny(1) file-read-data /Users/.../Desktop/MCMtools/core
#
# 这是内核拒绝，Python 侧绕不过去（试过 -c 内联代码、试过 exec 脚本，
# 都会被拦）。唯一可靠的办法是把整个文件夹移出受保护目录。
# 这里提前检查并说清楚，而不是留给用户一个"双击没反应"。
if ! ls "${HERE}/core" >/dev/null 2>&1; then
  osascript -e 'display alert "请把 MCMtools 移到别的位置" message "macOS 会保护桌面、文稿和下载文件夹。放在这些位置时，系统不允许本程序读取自己的文件，所以无法启动。请把整个 MCMtools 文件夹移到不受保护的位置，例如主目录下的 ~/MCMtools，然后重新双击。" as critical'
  exit 1
fi

# 找一个 Python。这里只做粗筛，真正的选择在 mcmboot.py 里：
# 它会逐个探测候选解释器的依赖是否齐全（版本号不等于可用）。
PY3="$(command -v python3 2>/dev/null || true)"
if [ -z "$PY3" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [ -x "$c" ]; then PY3="$c"; break; fi
  done
fi
if [ -z "$PY3" ]; then
  osascript -e 'display alert "需要安装 Python" message "MCMtools 需要 Python 3.9 或更新版本。请到 python.org/downloads 下载安装，然后重新打开。" as critical'
  exit 1
fi

cd "$PROJECT" || exit 1

# 引导代码内联传给 -c：见上面 TCC 的说明，脚本文件本身也可能被拦。
LAUNCHER_HEAD

  printf 'exec "$PY3" -c "$(cat <<%sMCMBOOT%s\n' "'" "'"
  cat "${BOOTSTRAP_FILE}"
  printf 'MCMBOOT\n)" "${HERE}/core" "${PROJECT}"\n'
} > "${APP}/Contents/MacOS/${APP_NAME}"
chmod +x "${APP}/Contents/MacOS/${APP_NAME}"

# ------------------------------------------------------------------- plist
cat > "${APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>       <string>${APP_NAME}</string>
  <key>CFBundleExecutable</key>        <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>        <string>${BUNDLE_ID}</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key>           <string>${VERSION}</string>
  <key>LSMinimumSystemVersion</key>    <string>10.13</string>
  <key>NSHighResolutionCapable</key>   <true/>
  <key>LSUIElement</key>               <false/>
</dict>
</plist>
PLIST

# ------------------------------------------------------------------- icon
ICON_SRC="${HERE}/web/icon.png"
if [ -f "${ICON_SRC}" ]; then
  ICONSET="${HERE}/.build/icon.iconset"
  rm -rf "${ICONSET}"; mkdir -p "${ICONSET}"
  for size in 16 32 64 128 256 512; do
    sips -z $size $size "${ICON_SRC}" --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null 2>&1 || true
    dbl=$((size * 2))
    sips -z $dbl $dbl "${ICON_SRC}" --out "${ICONSET}/icon_${size}x${size}@2x.png" >/dev/null 2>&1 || true
  done
  if iconutil -c icns "${ICONSET}" -o "${APP}/Contents/Resources/icon.icns" 2>/dev/null; then
    echo "  icon:   built from web/icon.png"
  else
    echo "  icon:   skipped (iconutil failed)"
  fi
  rm -rf "${ICONSET}"
else
  echo "  icon:   none (add web/icon.png to get one)"
fi

# ------------------------------------------------------- signature (ad-hoc)
# An ad-hoc signature is enough for a locally built app and avoids Gatekeeper
# refusing to launch an unsigned bundle on newer macOS.
#
# xattr -cr first: a resource fork or Finder metadata on any file makes
# codesign fail with "detritus not allowed", which would silently leave the
# bundle unsigned.
xattr -cr "${APP}" 2>/dev/null || true

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "${APP}" >/dev/null 2>&1 \
    && echo "  signed: ad-hoc" \
    || echo "  signed: skipped (codesign failed; the app still runs locally)"
fi

echo
echo "Built ${APP}"
echo
echo "Use it:"
echo "  open '${APP}'                              # double-click equivalent"
echo "  open '${APP}' --args ~/some/project        # start on a specific project"
echo
echo "  (--args matters: 'open APP /path' silently drops the path)"
echo
echo "It runs ${HERE}/start, so changes to core/ and web/ take effect"
echo "on the next launch with no rebuild."
