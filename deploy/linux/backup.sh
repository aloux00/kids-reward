#!/usr/bin/env bash
# ============================================================
#  每日备份：数据库一致性快照 + 佐证照片 + 规则文件
#  可用 cron 定时执行，也被 install.sh 自动挂成每日任务
#
#  为什么不用 cp：SQLite 是 WAL 模式，进程运行中直接复制 .db
#  会丢掉尚未合并的事务，备份出来的是损坏状态。必须 VACUUM INTO。
# ============================================================
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/star-kids}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="${APP_DIR}/backups/${STAMP}"

mkdir -p "${DEST}"

# 1) 数据库快照
if [[ -f "${APP_DIR}/data/kids.db" ]]; then
    sqlite3 "${APP_DIR}/data/kids.db" \
        "VACUUM INTO '${DEST}/kids.db';" 2>/dev/null \
    || sqlite3 "file:${APP_DIR}/data/kids.db?mode=ro" \
        "VACUUM INTO '${DEST}/kids.db';"
    echo "[$(date '+%F %T')] 数据库快照完成"
else
    echo "[$(date '+%F %T')] 没有找到数据库，跳过" >&2
fi

# 2) 佐证照片与规则
[[ -d "${APP_DIR}/uploads" ]] && cp -a "${APP_DIR}/uploads" "${DEST}/" 2>/dev/null || true
[[ -f "${APP_DIR}/rules.yaml" ]] && cp -a "${APP_DIR}/rules.yaml" "${DEST}/" 2>/dev/null || true

# 3) 打包压缩，省空间（ARM 板存储往往不大）
tar -czf "${DEST}.tar.gz" -C "${APP_DIR}/backups" "${STAMP}" 2>/dev/null && rm -rf "${DEST}"

# 4) 清理旧备份
find "${APP_DIR}/backups" -name '20*.tar.gz' -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

# 5) 报告
SIZE="$(du -sh "${APP_DIR}/backups" 2>/dev/null | cut -f1)"
N="$(find "${APP_DIR}/backups" -name '20*.tar.gz' 2>/dev/null | wc -l)"
echo "[$(date '+%F %T')] 备份完成 → backups/${STAMP}.tar.gz  共 ${N} 份，占用 ${SIZE}"

# 6) 可选：同步到远程。把下面这行的注释去掉并改成你自己的目标即可。
#    建议至少有一份在另一台设备上，否则机器坏了数据也就没了。
# rsync -az --delete "${APP_DIR}/backups/" user@nas:/backup/star-kids/
