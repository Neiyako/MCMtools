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
#
# 注意：复制 core/templates/web 进 app 包是**构建时**的事，写在 heredoc
# 外面。放进 heredoc 里会变成"每次启动都复制一遍"，既慢又会在用户
# 只拷了 .app 时因为源路径不存在而报错。
# ---------------------------------------------------------- 自包含：构建期复制
#
# 为什么复制而不是让 app 指向仓库：
#   原来生成的启动器靠"上溯三级"找到仓库根，于是有两种情况直接坏掉 ——
#     1. 把 MCMtools.app 拖到别处（比如从 Desktop 拖到 /Applications）；
#     2. 只想把 app 拷给队友，不拷整个仓库。
#   两种情况下启动器算出的仓库根都是错的，模板库和面板随之失效，
#   而报出来的现象是"模板没了"—— 很难联想到是路径问题。
#
#   复制一份进 Contents/Resources 之后就与仓库解耦：app 可以单独存在、
#   单独分发。体积代价约 1.5MB（模板是 YAML 加 render.py，很小）。
#
# 优先级仍然是"仓库优先，包内兜底"：
#   仓库在（本机开发）→ 用仓库，改 core/ 和 web/ 重启即生效，不用重建；
#   仓库不在（app 被拷走）→ 用包内副本，功能完整。
# ---------------------------------------------------------------------------
RES_DIR="${APP}/Contents/Resources"
mkdir -p "${RES_DIR}"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
    --exclude '.pytest_cache' \
    "${HERE}/core/" "${RES_DIR}/core/"
  rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
    "${HERE}/templates/" "${RES_DIR}/templates/"
else
  rm -rf "${RES_DIR}/core" "${RES_DIR}/templates"
  cp -R "${HERE}/core" "${RES_DIR}/core"
  cp -R "${HERE}/templates" "${RES_DIR}/templates"
  find "${RES_DIR}/core" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "${RES_DIR}" -name '*.pyc' -delete 2>/dev/null || true
  find "${RES_DIR}" -name '.DS_Store' -delete 2>/dev/null || true
fi

# 面板也带一份：仓库不在时 app 仍要有界面。web/ 只有四个文件，几十 KB。
rm -rf "${RES_DIR}/web"; mkdir -p "${RES_DIR}/web"
for f in index.html app.js app.css strings.js; do
  [ -f "${HERE}/web/${f}" ] && cp "${HERE}/web/${f}" "${RES_DIR}/web/${f}"
done
echo "  bundle: core/ templates/ web/ copied into Contents/Resources"

# 包内的 core 路径。仓库根存在时启动器仍优先用仓库（见 root.py 的解析顺序），
# 这个只是兜底。
CORE_DIR="${RES_DIR}/core"

{
  cat <<'LAUNCHER_HEAD'
#!/bin/bash
set -uo pipefail

# 仓库根目录：可执行文件位于 <root>/MCMtools.app/Contents/MacOS/ 下，上溯三级。
# 这个值由 build-app.sh 烘在下面（MCMTOOLS_HOME），这里只是给人看的兜底。
HERE="$(cd "$(dirname "$0")/../../.." && pwd)"

# 起手目录。优先用传入的项目目录；否则**不要**默认桌面 ——
# macOS 保护 ~/Desktop，项目建在那里会踩 TCC。用 ~/mcm 更好，
# README 也是这么建议的。
if [ $# -ge 1 ] && [ -d "$1" ]; then
  PROJECT="$1"
else
  PROJECT="${HOME}/mcm"
fi
mkdir -p "$PROJECT" 2>/dev/null || PROJECT="${HOME}"

# ---- TCC 预检 ------------------------------------------------------------
# 包内已经有 core 和 templates，所以**不再需要**读取受保护目录里的仓库。
# 这一检查因此从"必须搬走"降级为"顺便提示"：只有 app 自己落在
# ~/Desktop、~/Documents、~/Downloads 时才会被内核拒绝读取包内文件。
case "$HERE" in
  "$HOME"/Desktop*|"$HOME"/Documents*|"$HOME"/Downloads*)
    osascript -e 'display alert "建议把 MCMtools 移出桌面" message "macOS 会保护桌面、文稿和下载文件夹。app 放在这些位置时，系统偶尔会拒绝它读取自己的文件。如果双击没反应，请把 MCMtools.app 移到 ~/Applications 或主目录下再试。" as warning' >/dev/null 2>&1 || true
    ;;
esac

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

LAUNCHER_HEAD

  # 把构建时确定的路径烘进启动脚本。这些是**明确的告知**，
  # 而不是让 Python 去猜 —— 猜正是原来失效的原因。
  #
  # ⚠️ 这一段必须排在读取这些变量的逻辑**前面**。之前它在后面，
  # 于是配着 `set -u`，第 175 行读 $MCMTOOLS_HOME 时变量还不存在，
  # 脚本当场以 "unbound variable" 退出 —— 拷到别的机器上双击
  # 完全没反应，而且因为 app 是在仓库原地构建的、报错又被
  # Finder 吞掉，本机测试时看不出来。
  printf 'export MCMTOOLS_HOME=%s\n' "'${HERE}'"
  printf 'export MCMTOOLS_BUNDLE_CORE=%s\n' "'${RES_DIR}/core'"
  printf 'export MCMTOOLS_BUNDLE_TEMPLATES=%s\n' "'${RES_DIR}/templates'"
  printf 'export MCMTOOLS_BUNDLE_WEB=%s\n' "'${RES_DIR}/web'"
  printf 'export MCMTOOLS_APP_BUNDLE=%s\n' "'${APP}'"

  cat <<'LAUNCHER_BODY'
cd "$PROJECT" || exit 1

# 代码用哪一份：**仓库优先，包内兜底**。
#   仓库在   → 用它，改 core/、web/ 之后重启即生效（本机开发的工作方式没变）
#   仓库不在 → 用包内副本，app 可以单独拷走
# 这正是 core/mcmcore/root.py 的解析顺序，这里只是把两个候选都告诉它。
if [ -d "$MCMTOOLS_HOME/core/mcmcore" ]; then
  MCM_CORE="$MCMTOOLS_HOME/core"
else
  MCM_CORE="$MCMTOOLS_BUNDLE_CORE"
fi
export MCMTOOLS_CORE="$MCM_CORE"

# 版本号：包内副本没有 .git，git_revision() 会返回 None 而不是报错。
# 明确告诉它别去试，省一次每进程 3 秒的超时。
[ -d "$MCMTOOLS_HOME/.git" ] || export MCMTOOLS_NO_GIT=1

# 引导代码内联传给 -c：见上面 TCC 的说明，脚本文件本身也可能被拦。
LAUNCHER_BODY

  printf 'exec "$PY3" -c "$(cat <<%sMCMBOOT%s\n' "'" "'"
  cat "${BOOTSTRAP_FILE}"
  printf 'MCMBOOT\n)" "$MCM_CORE" "$PROJECT"\n'
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
  if codesign --force --deep --sign - "${APP}" 2>/tmp/mcmtools-codesign.log; then
    echo "  signed: ad-hoc"
  else
    # 报出真实原因而不是一句"失败了"。上一次这里吞掉了 stderr，
    # 结果是"签名失败"和"为什么失败"都看不到。
    echo "  signed: skipped (the app still runs locally)"
    sed 's/^/          /' /tmp/mcmtools-codesign.log | head -5
  fi
  rm -f /tmp/mcmtools-codesign.log
fi

echo
echo "Built ${APP}  ($(du -sh "${APP}" | cut -f1))"
echo
echo "Use it:"
echo "  open '${APP}'                              # double-click equivalent"
echo "  open '${APP}' --args ~/some/project        # start on a specific project"
echo
echo "  (--args matters: 'open APP /path' silently drops the path)"
echo
echo "This bundle carries its own copy of core/, templates/ and web/"
echo "under Contents/Resources, so it can be moved or copied to another"
echo "machine on its own."
echo
echo "While the checkout at ${HERE} exists, the app runs THAT copy, so"
echo "edits to core/ and web/ take effect on the next launch with no"
echo "rebuild. Re-run build-app.sh to refresh the bundled fallback copy."
