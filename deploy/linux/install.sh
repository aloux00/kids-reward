#!/usr/bin/env bash
# ============================================================
#  星星成长记 · Linux / Armbian 一键部署
#  适用于 Debian / Ubuntu / Armbian 系（玩客云、N1、香橙派、树莓派等）
#
#    sudo bash install.sh [源码目录]
#
#  可重复运行。已存在的数据库和 rules.yaml 不会被覆盖。
# ============================================================
set -Eeuo pipefail

APP_NAME="star-kids"
APP_DIR="/opt/${APP_NAME}"
SVC_USER="${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}.env"
PORT="8777"

SRC_DIR="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\n\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 sudo 运行：sudo bash install.sh"

# ---------------------------------------------------------------- 环境识别
ARCH="$(uname -m)"
OS_NAME="$(. /etc/os-release 2>/dev/null && echo "$ID" || echo unknown)"
RAM_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))

log "环境识别"
info "架构：${ARCH}    系统：${OS_NAME}    内存：${RAM_MB} MB"

case "${ARCH}" in
  armv7l|aarch64|arm64|armhf) info "ARM 板 detected —— 部署后会额外做 SD 卡写入优化的建议提示" ;;
  x86_64) info "x86_64 主机" ;;
  *) ;;
esac

case "${OS_NAME}" in
  debian|ubuntu|armbian|raspbian) ;;
  *) info "注意：本脚本面向 Debian/Ubuntu/Armbian，其他发行版请自行调整包管理命令" ;;
esac

if [[ ${RAM_MB} -lt 380 ]]; then
  info "内存偏小（${RAM_MB} MB），单 worker 运行没问题，但请不要同时跑其他重型服务"
fi

# ---------------------------------------------------------------- 依赖
log "安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip sqlite3 curl ca-certificates \
  || die "依赖安装失败，请检查软件源是否可用"

PY_VER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
info "Python ${PY_VER}"
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' \
  || die "Python 需要 3.9 或更高版本，当前 ${PY_VER}"

# ---------------------------------------------------------------- 专用用户
log "准备运行账号"
if ! id -u "${SVC_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${SVC_USER}"
  info "已创建系统账号 ${SVC_USER}（无登录权限，即便被攻破也无法拿到 shell）"
else
  info "账号 ${SVC_USER} 已存在，跳过"
fi

# ---------------------------------------------------------------- 代码就位
log "部署代码到 ${APP_DIR}"
mkdir -p "${APP_DIR}"
if [[ ! -f "${SRC_DIR}/app/main.py" ]]; then
  [[ -f "${APP_DIR}/app/main.py" ]] || die "没有找到源码（${SRC_DIR}/app/main.py 不存在）。请把整个项目传上来后重试"
else
  cp -a "${SRC_DIR}/app" "${APP_DIR}/"
  cp -a "${SRC_DIR}/static" "${APP_DIR}/"
  cp -a "${SRC_DIR}/rules.yaml" "${APP_DIR}/"
  cp -a "${SRC_DIR}/requirements.txt" "${APP_DIR}/"
  cp -a "${SRC_DIR}/run.py" "${APP_DIR}/"
  cp -a "${SRC_DIR}/seed.py" "${APP_DIR}/"
  [[ -f "${SRC_DIR}/smoke_test.py" ]] && cp -a "${SRC_DIR}/smoke_test.py" "${APP_DIR}/" || true
  mkdir -p "${APP_DIR}/uploads" "${APP_DIR}/data"
  info "已从 ${SRC_DIR} 复制"
fi

# 关键文件校验：宁可在这里报错，也不要带着缺失的代码继续走下去
for _need in app/main.py app/config.py static/index.html rules.yaml requirements.txt run.py seed.py; do
  [[ -f "${APP_DIR}/${_need}" ]] || die "代码不完整，缺少 ${_need}。请重新上传项目"
done
info "关键文件校验通过"

# ---------------------------------------------------------------- 虚拟环境
log "创建虚拟环境并安装依赖"
if [[ ! -x "${APP_DIR}/venv/bin/python" ]]; then
  python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install -q --upgrade pip wheel
# ARM 板编译 argon2/cffi 之类容易失败，这里只装纯 Python 依赖，通常几秒完成
"${APP_DIR}/venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt" \
  || die "Python 依赖安装失败，通常是网络或编译环境问题"

# ---------------------------------------------------------------- 密钥
log "生成随机密钥"
if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET="$("${APP_DIR}/venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(48))')"
  cat > "${ENV_FILE}" <<EOF
# 星星成长记 运行环境
# 这个密钥用于签名登录令牌和小游戏答题，换掉它会让所有人重新登录。
KIDS_SECRET=${SECRET}
# 登录失败限流：10 分钟内错这么多次就锁定
KIDS_LOGIN_MAX_FAILS=6
KIDS_LOGIN_WINDOW=600
KIDS_LOGIN_LOCK=300
# 端口
KIDS_PORT=${PORT}
EOF
  chmod 600 "${ENV_FILE}"
  info "已写入 ${ENV_FILE}（权限 600）"
else
  info "密钥文件已存在，保留原值以免踢掉所有已登录设备"
fi

# ---------------------------------------------------------------- 运行模式
log "选择访问方式"
echo
echo "  1) 只有家里的手机/平板用（局域网直连）"
echo "  2) 家里可用 + 外网也能访问（Cloudflare Tunnel）    ← 推荐"
echo "  3) 只能通过本机代理访问（最安全，仅限配合隧道使用）"
echo
read -r -p "  请输入 1 / 2 / 3，回车默认 2：" MODE
MODE="${MODE:-2}"

case "${MODE}" in
  1) RUN_ARGS="--lan"
     info "监听 0.0.0.0:${PORT}，家里所有设备直连。不信任转发头。" ;;
  2) RUN_ARGS="--lan --proxy"
     info "监听 0.0.0.0:${PORT}，既能局域网直连，也能配合反向代理拿到真实 IP。"
     info "提示：同为局域网的设备理论上可伪造 X-Forwarded-For，仅适用于可信的家庭网络。" ;;
  3) RUN_ARGS="--proxy"
     info "只监听 127.0.0.1:${PORT}，外网访问必须走 Cloudflare Tunnel。暴露面最小。" ;;
  *) die "没有这个选项" ;;
esac

# ---------------------------------------------------------------- 初始化数据
log "初始化数据"
cd "${APP_DIR}"
if [[ -f "${APP_DIR}/data/kids.db" ]]; then
  SIZE="$(du -h "${APP_DIR}/data/kids.db" | cut -f1)"
  info "发现已有数据库（${SIZE}），保留现有积分和愿望"
else
  set +e
  "${APP_DIR}/venv/bin/python" seed.py
  SEED_RC=$?
  set -e
  if [[ ${SEED_RC} -ne 0 ]]; then
    info "演示数据初始化未成功（退出码 ${SEED_RC}），首次启动时会自动建库"
  fi
fi
chown -R "${SVC_USER}:${SVC_USER}" "${APP_DIR}"
chmod 700 "${APP_DIR}/data" "${APP_DIR}/uploads"

# ---------------------------------------------------------------- systemd
log "安装 systemd 服务"
cat > "/etc/systemd/system/${APP_NAME}.service" <<EOF
[Unit]
Description=Star Kids Reward (儿童成长激励系统)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/venv/bin/python run.py ${RUN_ARGS} --port \${KIDS_PORT}
Restart=always
RestartSec=3
# 崩溃后不要太快反复重启把 SD 卡写坏
StartLimitIntervalSec=60
StartLimitBurst=5

# 安全加固：即使代码被攻破也难以横向移动
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
# 数据目录需要写权限，显式放行
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/uploads
MemoryMax=400M

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${APP_NAME}.service"

# 限制 journald 占用，SD 卡设备上尤其重要
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/10-star-kids.conf <<'EOF'
# ARM 板的 SD 卡 / eMMC 写入寿命有限，限制日志占用
[Journal]
SystemMaxUse=200M
SystemKeepFree=512M
MaxRetentionSec=14day
EOF

# ---------------------------------------------------------------- 等待就绪
log "等待服务就绪"
for i in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then
    info "服务已就绪"
    break
  fi
  sleep 1
done

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

log "检查可用性"
if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then
  info "健康检查通过"
else
  die "服务没能起来，请查看日志：journalctl -u ${APP_NAME} -n 50 --no-pager"
fi

# ---------------------------------------------------------------- 定时备份
log "配置每日自动备份"
cp -f "$(dirname "$0")/backup.sh" "${APP_DIR}/backup.sh"
chmod +x "${APP_DIR}/backup.sh"
mkdir -p "${APP_DIR}/backups"
chown "${SVC_USER}:${SVC_USER}" "${APP_DIR}/backups"
( crontab -l 2>/dev/null | grep -v 'star-kids.*backup.sh'; \
  echo "17 3 * * * ${APP_DIR}/backup.sh >> ${APP_DIR}/backups/cron.log 2>&1" ) | crontab -
info "每天 03:17 自动备份，保留最近 14 份"

# ---------------------------------------------------------------- 完成
cat <<EOF

============================================================
  部署完成
============================================================

  本机地址：      http://127.0.0.1:${PORT}
$( [[ "${RUN_ARGS}" == *--lan* && -n "${IP}" ]] && echo "  家里设备：      http://${IP}:${PORT}" )

  常用命令
    systemctl status ${APP_NAME}        查看状态
    systemctl restart ${APP_NAME}       重启
    journalctl -u ${APP_NAME} -f        实时看日志
    ${APP_DIR}/backup.sh                立即备份一次
    sudo bash ${SRC_DIR}/deploy/linux/update.sh   拉取新代码并重启（需 git 部署）

  首次登录后务必做的事
    1. 立刻改掉 dad / mom / 孩子的默认口令 1234
    2. 删掉演示任务，发布你家的真实任务
    3. 让孩子自己选愿望（这一步对动力的影响比任何配置都大）

  下一步
    想在 LTE/外面也能访问 —— 见 deploy/cloudflare/README.md
    想把数据搬到这台机器 —— 见 deploy/linux/README.md 的"迁移数据"

EOF
