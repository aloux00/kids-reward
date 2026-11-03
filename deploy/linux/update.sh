#!/usr/bin/env bash
# ============================================================
#  星星成长记 · 更新已部署的服务（systemd 版）
#
#    sudo bash update.sh           从 git 拉最新代码并重启
#    sudo bash update.sh --check   只看有没有新提交，不动任何东西
#
#  前提（和 install.sh 的分工）：
#    /opt/star-kids-src     ← git clone 出来的【纯代码】，不跑服务
#    /opt/star-kids         ← 实际运行的目录，含 data/ uploads/ rules.yaml
#
#  为什么分成两个目录：
#    rules.yaml 会被家长端写回，data/ 天天在变。如果它们就在 git 仓库里，
#    工作区永远是脏的，git pull 迟早冲突。分开之后代码可以随便 pull，
#    数据安安稳稳躺在自己的目录里，谁也碰不到谁。
#
#  这个脚本永远不会覆盖 data/ uploads/ rules.yaml。
# ============================================================
set -Eeuo pipefail

APP_NAME="star-kids"
APP_DIR="/opt/${APP_NAME}"
SRC_DIR="${SRC_DIR:-/opt/${APP_NAME}-src}"
SVC_USER="${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}.env"
HEALTH_TIMEOUT=40

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    ! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 sudo 运行：sudo bash update.sh"

# 脚本自己就躺在会被更新的源码目录里，执行到一半被 git pull 换掉会读出乱码，
# 所以先把自己复制到 /tmp 再重新执行一次（只做一次，靠环境变量防死循环）。
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
if [[ "${UPDATE_REEXEC:-0}" != "1" && "${SELF}" == "${SRC_DIR}/"* ]]; then
  cp "${SELF}" /tmp/star-kids-update.sh
  export UPDATE_REEXEC=1
  exec bash /tmp/star-kids-update.sh "$@"
fi

# ---------------------------------------------------------------- 前置检查
log "环境检查"
[[ -d "${SRC_DIR}/.git" ]] || die "${SRC_DIR} 不是 git 仓库。
  这套更新方式要求代码来自 git clone。如果你还在用 scp 传文件，
  要么先用 deploy/linux/README.md 第六节的 git 方式重建一次部署目录，
  要么继续用 scp 覆盖 app/ 和 static/。"

[[ -f "${APP_DIR}/app/main.py" ]] || die "${APP_DIR} 不像已部署的目录（缺 app/main.py）。请先跑 install.sh。"

PORT="$(sed -n 's/^KIDS_PORT=//p' "${ENV_FILE}" 2>/dev/null | tr -d '[:space:]')"
PORT="${PORT:-8777}"
info "源码目录 ${SRC_DIR}"
info "运行目录 ${APP_DIR}　端口 ${PORT}"

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

# ---------------------------------------------------------------- 看有没有更新
cd "${SRC_DIR}"
git fetch --quiet origin || die "git fetch 失败，检查网络或远程仓库权限"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
UPSTREAM="origin/${BRANCH}"
PREV="$(git rev-parse --short HEAD)"

BEHIND="$(git rev-list --count "HEAD..${UPSTREAM}" 2>/dev/null || echo 0)"
if [[ "${BEHIND}" -eq 0 ]]; then
  info "已是最新（${BRANCH} @ ${PREV}），没有需要更新的内容"
  [[ ${CHECK_ONLY} -eq 1 ]] && exit 0
  log "仍然重启服务以应用可能的配置改动"
  systemctl restart "${APP_NAME}" || die "重启失败：journalctl -u ${APP_NAME} -n 50 --no-pager"
  exit 0
fi

info "有 ${BEHIND} 个新提交，即将更新：${PREV} → ${UPSTREAM}"
git --no-pager log --oneline "HEAD..${UPSTREAM}" | sed 's/^/      /'

if [[ ${CHECK_ONLY} -eq 1 ]]; then
  log "只检查不更新（--check）"
  info "要真正更新，去掉 --check 再跑一次"
  exit 0
fi

# ---------------------------------------------------------------- 记录旧状态
# 回滚要用：老提交号 + 依赖文件的哈希（决定要不要重装依赖）
PREV_FULL="$(git rev-parse HEAD)"
PREV_REQ="$(md5sum "${APP_DIR}/requirements.txt" 2>/dev/null | cut -d' ' -f1 || echo none)"

# ---------------------------------------------------------------- 拉代码
log "拉取代码"
git pull --ff-only || die "git pull 失败。
  多半是 ${SRC_DIR} 里有本地改动（这个目录本该只读）。
  看看是什么：cd ${SRC_DIR} && git status
  确认可以丢弃后：git checkout -- . && git clean -fd"
NEW="$(git rev-parse --short HEAD)"
info "代码已更新到 ${NEW}"

# ---------------------------------------------------------------- 同步代码
# 用"整个目录换掉"而不是 rsync 覆盖：这样删掉的旧文件不会残留。
# 也不用额外装 rsync —— 树莓派/玩客云上少一个依赖少一份麻烦。
sync_dir() {
  local name="$1"
  [[ -d "${SRC_DIR}/${name}" ]] || return 0
  rm -rf "${APP_DIR}/.${name}.new"
  cp -a "${SRC_DIR}/${name}" "${APP_DIR}/.${name}.new"
  find "${APP_DIR}/.${name}.new" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "${APP_DIR:?}/${name}"
  mv "${APP_DIR}/.${name}.new" "${APP_DIR}/${name}"
  info "已同步 ${name}/"
}

log "同步代码到 ${APP_DIR}"
sync_dir app
sync_dir static
for f in run.py seed.py requirements.txt smoke_test.py; do
  [[ -f "${SRC_DIR}/${f}" ]] && cp -a "${SRC_DIR}/${f}" "${APP_DIR}/${f}"
done
info "已同步 run.py seed.py requirements.txt smoke_test*.py"
warn "data/ uploads/ rules.yaml 未改动（它们是数据，不是代码）"

# ---------------------------------------------------------------- 依赖
REQ_NOW="$(md5sum "${APP_DIR}/requirements.txt" | cut -d' ' -f1)"
if [[ "${REQ_NOW}" != "${PREV_REQ}" ]]; then
  log "依赖清单有变化，重装 Python 依赖"
  "${APP_DIR}/venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt" \
    || die "依赖安装失败，已停在此步。回滚：cd ${SRC_DIR} && git reset --hard ${PREV_FULL} && sudo bash update.sh"
  info "依赖已更新"
else
  info "依赖无变化，跳过 pip（省下 10~60 秒）"
fi

chown -R "${SVC_USER}:${SVC_USER}" "${APP_DIR}/app" "${APP_DIR}/static" "${APP_DIR}/venv" 2>/dev/null || true
chown "${SVC_USER}:${SVC_USER}" "${APP_DIR}/run.py" "${APP_DIR}/seed.py" 2>/dev/null || true

# ---------------------------------------------------------------- 重启 + 验证
log "重启服务"
systemctl restart "${APP_NAME}"

info "等待健康检查（最多 ${HEALTH_TIMEOUT} 秒）"
OK=0
for _ in $(seq 1 "${HEALTH_TIMEOUT}"); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then OK=1; break; fi
  sleep 1
done

if [[ ${OK} -eq 1 ]]; then
  cat <<EOF

============================================================
  更新完成  ${PREV} → ${NEW}
============================================================

  当前提交：$(git -C "${SRC_DIR}" --no-pager log -1 --pretty='%h %s')
  健康检查：通过

  有问题时
    journalctl -u ${APP_NAME} -f        看日志
    cd ${SRC_DIR} && git reset --hard ${PREV_FULL}
    sudo bash update.sh                 回滚到上一版

EOF
  exit 0
fi

# ---------------------------------------------------------------- 失败回滚
log "健康检查失败，开始回滚"
systemctl status "${APP_NAME}" --no-pager -n 20 || true

cd "${SRC_DIR}"
git reset --hard "${PREV_FULL}" >/dev/null
sync_dir app
sync_dir static
for f in run.py seed.py requirements.txt; do
  [[ -f "${SRC_DIR}/${f}" ]] && cp -a "${SRC_DIR}/${f}" "${APP_DIR}/${f}"
done
chown -R "${SVC_USER}:${SVC_USER}" "${APP_DIR}/app" "${APP_DIR}/static"
systemctl restart "${APP_NAME}"
sleep 5

if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then
  die "新版本起不来，已回滚到 ${PREV}（服务正常）。
  排查方向：journalctl -u ${APP_NAME} -n 80 --no-pager"
else
  die "回滚后仍然不健康，需要人工介入。
  看日志：journalctl -u ${APP_NAME} -n 100 --no-pager
  数据没被动过：${APP_DIR}/data 原样还在"
fi
