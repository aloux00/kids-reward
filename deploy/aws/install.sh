#!/usr/bin/env bash
# ============================================================
#  星星成长记 · AWS EC2 一键部署
#  适用于 Amazon Linux 2023 / Amazon Linux 2 / Ubuntu 22.04+ / Debian
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
warn() { printf '    \033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 sudo 运行：sudo bash install.sh"

# ---------------------------------------------------------------- 环境识别
ARCH="$(uname -m)"
OS_ID="$(. /etc/os-release 2>/dev/null && echo "${ID}" || echo unknown)"
OS_VER="$(. /etc/os-release 2>/dev/null && echo "${VERSION_ID:-}" || echo '')"
RAM_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))

log "环境识别"
info "架构：${ARCH}    系统：${OS_ID} ${OS_VER}    内存：${RAM_MB} MB"

# 包管理器分支：Amazon Linux 是 dnf，Debian 系是 apt
PKG=""
case "${OS_ID}" in
  amzn|fedora|rhel|centos|rocky|almalinux)
    PKG="dnf"
    command -v dnf >/dev/null 2>&1 || PKG="yum"
    info "包管理器：${PKG}（Amazon Linux / RHEL 系）" ;;
  ubuntu|debian)
    PKG="apt"; export DEBIAN_FRONTEND=noninteractive
    info "包管理器：apt（Debian 系）" ;;
  *)
    # 没认出来也别硬退，交互问一次
    if command -v dnf >/dev/null 2>&1; then PKG="dnf"
    elif command -v apt-get >/dev/null 2>&1; then PKG="apt"
    else die "没能识别包管理器。请手动安装 python3 / python3-venv / sqlite3 / curl 后重试"; fi
    warn "未识别的系统 ${OS_ID}，按 ${PKG} 处理" ;;
esac

if [[ ${RAM_MB} -lt 900 ]]; then
  info "内存 ${RAM_MB} MB（t2/t3.micro 级别）够用，但请不要在同一台上再跑别的重型服务"
fi

# ---------------------------------------------------------------- 依赖
log "安装系统依赖"
if [[ "${PKG}" == "apt" ]]; then
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip sqlite3 curl ca-certificates \
    || die "依赖安装失败，请检查软件源"
else
  ${PKG} install -y -q python3 python3-pip sqlite curl ca-certificates \
    || die "依赖安装失败，请检查软件源"
fi

PY_VER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
info "Python ${PY_VER}"
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' \
  || die "Python 需要 3.9 或更高版本，当前 ${PY_VER}。Amazon Linux 2 自带 3.7，请改用 Amazon Linux 2023"

# ---------------------------------------------------------------- 专用用户
log "准备运行账号"
if ! id -u "${SVC_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /sbin/nologin "${SVC_USER}"
  info "已创建系统账号 ${SVC_USER}（无登录权限）"
else
  info "账号 ${SVC_USER} 已存在，跳过"
fi

# ---------------------------------------------------------------- 代码就位
log "部署代码到 ${APP_DIR}"
mkdir -p "${APP_DIR}"
if [[ ! -f "${SRC_DIR}/app/main.py" ]]; then
  [[ -f "${APP_DIR}/app/main.py" ]] || die "没有找到源码（${SRC_DIR}/app/main.py 不存在）。请先把项目传上来"
else
  cp -a "${SRC_DIR}/app" "${APP_DIR}/"
  cp -a "${SRC_DIR}/static" "${APP_DIR}/"
  cp -a "${SRC_DIR}/rules.yaml" "${APP_DIR}/"
  cp -a "${SRC_DIR}/requirements.txt" "${APP_DIR}/"
  cp -a "${SRC_DIR}/run.py" "${APP_DIR}/"
  cp -a "${SRC_DIR}/seed.py" "${APP_DIR}/"
  [[ -f "${SRC_DIR}/smoke_test.py" ]] && cp -a "${SRC_DIR}/smoke_test.py" "${APP_DIR}/" || true
  # 教材 PDF 动辄几百 MB，别跟着代码一起传——到服务器上再下或直接不装
  info "已复制代码（未复制 data/textbooks 里的教材 PDF）"
fi

for _need in app/main.py app/config.py static/index.html rules.yaml requirements.txt run.py seed.py; do
  [[ -f "${APP_DIR}/${_need}" ]] || die "代码不完整，缺少 ${_need}。请重新上传项目"
done
mkdir -p "${APP_DIR}/uploads" "${APP_DIR}/data"
info "关键文件校验通过"

# ---------------------------------------------------------------- 虚拟环境
log "创建虚拟环境并安装依赖"
if [[ ! -x "${APP_DIR}/venv/bin/python" ]]; then
  python3 -m venv "${APP_DIR}/venv" \
    || die "创建虚拟环境失败。Amazon Linux 2023 若缺 venv 模块：dnf install -y python3-pip 后重试"
fi
"${APP_DIR}/venv/bin/pip" install -q --upgrade pip wheel
"${APP_DIR}/venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt" \
  || die "Python 依赖安装失败，通常是网络问题"

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

# ---------------------------------------------------------------- 访问方式
log "选择访问方式"
echo
echo "  1) Cloudflare Tunnel 专用（只听 127.0.0.1）        ← 推荐，不用买公网 IP"
echo "  2) 本机 Nginx 反代（只听 127.0.0.1，Nginx 对外）"
echo "  3) 直接对外（听 0.0.0.0，需自己在安全组放行端口）"
echo
read -r -p "  请输入 1 / 2 / 3，回车默认 1：" MODE
MODE="${MODE:-1}"

NEED_NGINX=0
case "${MODE}" in
  1) RUN_ARGS="--proxy"
     info "只监听 127.0.0.1:${PORT}。外网访问全部走 Cloudflare Tunnel，暴露面最小。" ;;
  2) RUN_ARGS="--proxy"; NEED_NGINX=1
     info "只监听 127.0.0.1:${PORT}，由 Nginx 对外提供 80/443。" ;;
  3) RUN_ARGS="--lan --proxy"
     warn "应用直接听 0.0.0.0:${PORT}，请务必在 AWS 安全组里只放行你需要的来源" ;;
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
  # 用 if 而不是 [[ ]] && ：后者在条件为假时返回 1，会被 set -e 当成致命错误
  if [[ ${SEED_RC} -ne 0 ]]; then
    info "演示数据初始化未成功（退出码 ${SEED_RC}），首次启动会自动建库"
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
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/uploads
# t2/t3.micro 只有 1 GB，留一半给系统
MemoryMax=500M

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${APP_NAME}.service"

# ---------------------------------------------------------------- Nginx
if [[ ${NEED_NGINX} -eq 1 ]]; then
  log "安装并配置 Nginx"
  if [[ "${PKG}" == "apt" ]]; then
    apt-get install -y -qq nginx
  else
    ${PKG} install -y -q nginx
  fi
  cat > "/etc/nginx/conf.d/star-kids.conf" <<EOF
# 反向代理到本机 uvicorn。
# 教材 PDF 走分片读取（Range），这几行必须保留，否则阅读器会打不开。
server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 400m;      # 上传教材 PDF 用

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }
}
EOF
  # 两个 default_server 会让 nginx -t 直接失败。
  # Debian 系的默认站点是 sites-enabled/default，Amazon Linux 的却内嵌在 nginx.conf 里，
  # 两种都要让位，否则选了模式 2 的人会发现 nginx 起不来。
  rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
  sed -i 's/ default_server//g' /etc/nginx/nginx.conf 2>/dev/null || true

  # 注意别写成 `if nginx -t | tail`：管道的退出码是 tail 的，永远为真
  if nginx -t >/tmp/star-kids-nginx-t.log 2>&1; then
    systemctl enable --now nginx
    info "Nginx 已就绪（80 端口）"
  else
    warn "Nginx 配置未通过校验，输出如下："
    tail -5 /tmp/star-kids-nginx-t.log
    warn "应用本身已在 127.0.0.1:${PORT} 正常运行，可以直接用 IP 访问，或改走 Cloudflare Tunnel"
  fi
  info "Nginx 已就绪（80 端口），证书用：certbot --nginx -d 你的域名"
fi

# ---------------------------------------------------------------- 等待就绪
log "等待服务就绪"
for i in $(seq 1 30); do
  # 同样必须用 if：curl 在前几秒必然失败，写成 && 会被 set -e 直接终止脚本
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then
    break
  fi
  sleep 1
done

if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/health"; then
  info "健康检查通过"
else
  die "服务没能起来，请查看日志：journalctl -u ${APP_NAME} -n 50 --no-pager"
fi

# ---------------------------------------------------------------- 定时备份
log "配置每日自动备份"
cp -f "$(dirname "$0")/backup.sh" "${APP_DIR}/backup.sh" 2>/dev/null \
  || cp -f "$(dirname "$0")/../linux/backup.sh" "${APP_DIR}/backup.sh" 2>/dev/null \
  || warn "没找到 backup.sh，跳过自动备份配置（可从 deploy/linux/ 单独拷贝）"
chmod +x "${APP_DIR}/backup.sh"
mkdir -p "${APP_DIR}/backups"
chown "${SVC_USER}:${SVC_USER}" "${APP_DIR}/backups"
( crontab -l 2>/dev/null | grep -v 'star-kids.*backup.sh'; \
  echo "17 3 * * * ${APP_DIR}/backup.sh >> ${APP_DIR}/backups/cron.log 2>&1" ) | crontab -
info "每天 03:17 自动备份到 ${APP_DIR}/backups/"

# ---------------------------------------------------------------- 完成
cat <<EOF

============================================================
  部署完成
============================================================

  本机地址：      http://127.0.0.1:${PORT}

  常用命令
    systemctl status ${APP_NAME}        查看状态
    systemctl restart ${APP_NAME}       重启
    journalctl -u ${APP_NAME} -f       实时看日志
    ${APP_DIR}/backup.sh               立即备份一次

$(
  if [[ ${NEED_NGINX} -eq 1 ]]; then
    echo "  下一步：certbot --nginx -d 你的域名  申请免费 HTTPS 证书"
  else
    echo "  下一步：见 deploy/cloudflare/README.md 建隧道，"
    echo "          或 deploy/aws/README.md 第三节"
  fi
)

  首次登录后务必做的事
    1. 立刻改掉 dad / mom / 孩子的默认口令 1234
    2. 删掉演示任务，发布你家的真实任务
    3. 在 AWS 账单面板设一个 1 美元的预算告警，防止意外扣费

EOF
