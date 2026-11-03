#!/bin/sh
# 星星成长记 · 容器启动脚本
#
# 只负责三件事：
#   1. 兜住 Docker 挂载的坑，并给出能直接照抄的修复命令
#   2. 首次启动时补默认配置、建库
#   3. 把参数原样交给 Python（dev 模式覆盖 command 时走第 0 步）
#
# 端口、路径全部由环境变量决定，不写死在代码里。

set -e

DATA_DIR="${KIDS_DATA_DIR:-/app/data}"
UPLOAD_DIR="${KIDS_UPLOAD_DIR:-/app/uploads}"
RULES_PATH="${KIDS_RULES_PATH:-/app/rules.yaml}"
DEFAULT_RULES="${KIDS_DEFAULT_RULES:-/app/rules.yaml.default}"
PORT="${KIDS_PORT:-8777}"

say() { printf '  %s\n' "$*"; }

die() {
    printf '\n[启动失败] %s\n\n' "$*" >&2
    exit 1
}

# ---------------------------------------------------------------- 0. 显式命令
# docker-compose.dev.yml 会用 command 覆盖成 uvicorn --reload，走这条分支，
# 跳过下面所有初始化逻辑（数据早就初始化过了）。
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

say "星星成长记 · 容器启动"

# ------------------------------------------------------- 0.5 这份镜像有多旧
# 排查"改了代码怎么没生效"时，先看这一行：
#   时间没变 → 镜像没重建，容器跑的还是旧副本（用 docker compose watch 或 up -d --build）
#   时间变了 → 镜像没问题，去查代码本身
if [ -f /app/BUILD_INFO ]; then
    _built=$(sed -n 's/^built_at=//p' /app/BUILD_INFO)
    _fp=$(sed -n 's/^fingerprint=//p' /app/BUILD_INFO)
    say "镜像代码版本：${_built}　指纹 ${_fp}"
fi

# --------------------------------------------------- 1. rules.yaml 挂载的坑
# 宿主机上没有 rules.yaml 时，Docker 不报错，而是默默建一个同名空目录，
# 之后 App 读它会抛 IsADirectoryError —— 现场极难定位，所以提前拦。
if [ -d "${RULES_PATH}" ]; then
    die "${RULES_PATH} 是个目录，不是文件。
  原因：宿主机上对应的 rules.yaml 不存在，Docker 自动建了个空目录。
  修复：在项目目录执行
        touch rules.yaml
        docker compose down && docker compose up -d"
fi

if [ ! -f "${RULES_PATH}" ]; then
    [ -f "${DEFAULT_RULES}" ] || die "找不到默认规则文件 ${DEFAULT_RULES}，镜像不完整"
    cp "${DEFAULT_RULES}" "${RULES_PATH}"
    say "首次启动，已生成默认规则文件 ${RULES_PATH}"
fi

if [ ! -w "${RULES_PATH}" ]; then
    die "规则文件 ${RULES_PATH} 不可写（容器内 uid=$(id -u)）。
  家长在网页上保存规则、改品牌名都会写回这个文件，只读挂载会导致保存失败。
  修复：宿主机执行
        sudo chown 1000:1000 rules.yaml
  并确认 compose 里没有给这个文件加 :ro"
fi

# ------------------------------------------------------ 2. 数据目录可写性
# SQLite 打不开时只报 "unable to open database file"，看不出是权限问题。
for d in "${DATA_DIR}" "${UPLOAD_DIR}"; do
    mkdir -p "${d}" 2>/dev/null || die "无法创建目录 ${d}，请检查挂载路径"
    if [ ! -w "${d}" ]; then
        die "目录 ${d} 不可写（容器内 uid=$(id -u)）。
  多半是宿主机目录由 root 创建，容器内的 kids 用户进不去。
  修复：在【宿主机】的项目目录（有 docker-compose.yml 的那一层）执行
        sudo chown -R 1000:1000 data uploads"
    fi
done

# ------------------------------------------------------------ 3. 首次建库
# 只在数据库文件不存在时才写演示数据，绝不覆盖已有记录。
# KIDS_SEED=0 可以彻底关掉（正式上线后建议关掉，虽然它本来也不会重跑）。
if [ "${KIDS_SEED}" != "0" ] && [ ! -f "${DATA_DIR}/kids.db" ]; then
    say "数据库不存在，初始化演示数据"
    if ! python seed.py; then
        say "初始化失败 —— 服务照常启动，可在家长端手动创建成员"
    fi
fi

# -------------------------------------------------------------- 4. 起服务
# --lan 是必须的：容器内 127.0.0.1 只有容器自己能访问，端口映射进来的流量
# 目标地址是容器的 0.0.0.0，不监听 0.0.0.0 就一个请求都收不到。
set -- python run.py --lan --port "${PORT}"
if [ "${KIDS_PROXY}" = "1" ]; then
    set -- "$@" --proxy
fi
# KIDS_RELOAD=1 由 docker-compose.dev.yml 设置。走这里而不是覆盖 command，
# 是为了让开发模式也能享受上面那一整套挂载检查（rules.yaml 变成目录、
# 目录权限不对这些问题和是不是开发模式无关）。
if [ "${KIDS_RELOAD}" = "1" ]; then
    set -- "$@" --reload
fi

say "监听 0.0.0.0:${PORT}　数据目录 ${DATA_DIR}　反代模式 ${KIDS_PROXY:-0}"
if [ "${KIDS_RELOAD}" = "1" ]; then
    say "自动重载已开启：改 app/ 下的代码立即生效"
fi
exec "$@"
