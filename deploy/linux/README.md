# 部署到 Armbian / Linux 小主机

这是**最推荐的长期方案**。家里放一台 ARM 小主机（玩客云、斐讯 N1、香橙派、树莓派等），
功耗 2–10W，24 小时不关机，全家随时能访问，数据完全在自己手里。

## 一、为什么推荐它

| 对比 | Armbian 小主机 | 免费虚拟主机（serv00 等） |
|---|---|---|
| 会不会用到一半没了 | 不会，硬件在你手里 | **90 天不登录账号和数据永久删除** |
| 孩子的积分记录安全 | 自己掌控，可异地备份 | 依赖对方持续运营 |
| 家里访问速度 | 局域网直连，毫秒级 | 服务器在欧洲，延迟看运气 |
| 关机的数据后果 | 无 | 无（本就自己的） |
| 成本 | 一台二手盒子几十到一百多元，电费一年几块钱 | 免费，但代价是可靠性 |

**给每天都要打卡的孩子用的系统，最不能接受的是某天打开它发现数据是空的。**
这一点决定了虚拟主机只能当试验场，不能当正式环境。

## 二、什么机器能跑

要求很低，这套系统是单进程 Python + SQLite：

- CPU：任何 ARMv7 / ARM64 / x86 都行，单核足够
- 内存：**≥ 512 MB**，建议 1 GB
- 存储：≥ 512 MB 空闲（3 GB 的数据放十年也放不满）
- 系统：Debian / Ubuntu / Armbian 任一版本

实测开销：常驻内存约 60–90 MB，CPU 平时接近 0。

## 三、ARM 板必须注意的四件事（血泪经验）

**① 电源比什么都重要。** 玩客云、N1 这类盒子随机配送的电源往往刚好卡在临界值，
SD 卡随机写入时电压一抖就重启，长期下来文件系统直接损坏。
换成输出电流余量足够的品牌电源，这是最值得花的几十块钱。

**② 数据不要放在 SD 卡上。** SD 卡怕的就是 SQLite 这种持续小写。
优先用 eMMC 或 USB SSD；只能用 SD 卡的话，买 A2 / 高耐久（Endurance）型号，
并且**备份一定要放另一台设备**——同一张卡坏了，数据和备份一起没。

**③ 给它固定 IP。** 在路由器里做 **IP-MAC 绑定**（DHCP 静态分配），
否则某天路由器重启后地址变了，孩子平板上存的书签就打不开了。

**④ 加个散热片。** 盒子常年 24 小时跑，被动散热片十几块就能买到，能显著延长寿命。
放弱电箱里这种密闭空间的尤其要注意温度。

## 四、安装步骤

### 第 1 步 · 把项目传到服务器上

**方式 A · git clone（推荐，以后更新只要一条命令）**

服务器上执行：

```bash
sudo apt-get install -y git
sudo git clone https://github.com/<你的用户名>/kids-reward.git /opt/star-kids-src
```

代码放在 `/opt/star-kids-src`，只是个"代码仓库"，不跑服务；
安装脚本会把 `app/` `static/` 这些复制到 `/opt/star-kids` 去跑。
两个目录分开的原因见 `docs/GIT.md` 第四节 —— 简单说就是让 `git pull` 永远不会
跟家长端写回的 `rules.yaml` 打架。

**方式 B · 直接拷贝（没有 GitHub 仓库时用）**

在 Windows 本机（假设服务器 IP 是 192.168.1.50）：

```bash
scp -r "C:/WD/code/good study/kids-reward" root@192.168.1.50:/tmp/kids-reward
```

或者用 U 盘拷、用 WinSCP 拖拽，都行。这种方式以后更新得手动再传一次，
所以建议在 Windows 上把仓库建好之后改用方式 A。

### 第 2 步 · 执行安装脚本

SSH 登录服务器后（按方式 A 下载的代码）：

```bash
sudo bash /opt/star-kids-src/deploy/linux/install.sh
```

按方式 B 拷过来的话：

```bash
cd /tmp/kids-reward/deploy/linux
sudo bash install.sh
```

脚本会依次做完这些：安装系统依赖 → 建专用无 shell 账号 → 部署到 `/opt/star-kids` →
建虚拟环境装依赖 → **生成随机密钥**（不用默认那个了）→ 初始化数据 →
装 systemd 服务并设为开机自启 → 配置每日自动备份。

中途会问你一次访问方式：

```
1) 只有家里的手机/平板用（局域网直连）
2) 家里可用 + 外网也能访问（Cloudflare Tunnel）    ← 推荐
3) 只能通过本机代理访问（最安全，仅限配合隧道使用）
```

先不确定也没关系，后面一行命令就能改（见第六节）。

### 第 3 步 · 打开看看

浏览器访问脚本最后打印出来的地址，用 `dad` / `1234` 登录。

---

## 五、迁移现有数据（把 Windows 上的记录搬过来）

如果你已经在 Windows 上用了一段时间，孩子的积分和愿望**可以完整搬过来**。

**重要：两边绝对不能同时运行。** 两个进程各写各的数据库，会产生数据分裂，
最后你会发现孩子的分数对不上。**先停掉旧的，确认不再使用，再搬。**

### 步骤

1. **在 Windows 上生成快照。** 先关掉原来的黑窗口（停掉服务），再执行菜单里的备份，
   得到 `backups/某个时间/kids.db`——这已经是 `VACUUM INTO` 出来的一致性文件，可以直接用。

2. **上传到服务器。**

   ```bash
   scp "C:/WD/code/good study/kids-reward/backups/某个时间/kids.db" \
       root@192.168.1.50:/tmp/kids.db
   # 如果有孩子上传的佐证照片
   scp -r "C:/WD/code/good study/kids-reward/uploads" root@192.168.1.50:/tmp/uploads
   ```

3. **在服务器上替换。**

   ```bash
   sudo systemctl stop star-kids
   sudo cp /tmp/kids.db /opt/star-kids/data/kids.db
   # WAL 模式的配套文件必须一并删掉，否则会和新的主库冲突
   sudo rm -f /opt/star-kids/data/kids.db-wal /opt/star-kids/data/kids.db-shm
   sudo cp -r /tmp/uploads/* /opt/star-kids/uploads/ 2>/dev/null || true
   sudo chown -R star-kids:star-kids /opt/star-kids/data /opt/star-kids/uploads
   sudo systemctl start star-kids
   ```

4. **验证。** 登录家长端，看 thumb 孩子的星星币和等级跟原来一致。

> 密钥换了，所有人需要重新登录一次，这是正常的。

---

## 六、日常运维

```bash
# 状态（最重要的一条，出问题先看它）
systemctl status star-kids

# 实时日志 Ctrl+C 退出
journalctl -u star-kids -f

# 重启 / 停止 / 启动
systemctl restart star-kids
systemctl stop star-kids
systemctl start star-kids

# 立即备份一次
/opt/star-kids/backup.sh

# 查看备份
ls -lh /opt/star-kids/backups/
```

### 改访问方式（比如后来加了隧道）

```bash
sudo systemctl edit star-kids
```

填入：

```ini
[Service]
ExecStart=
ExecStart=/opt/star-kids/venv/bin/python run.py --lan --proxy --port ${KIDS_PORT}
sudo systemctl daemon-reload && sudo systemctl restart star-kids
```

> `ExecStart=` 那行空置是 systemd 的写法要求，用来先清空原值，不要删掉它。

### 改端口

编辑 `/etc/star-kids.env` 里的 `KIDS_PORT`，然后 `sudo systemctl restart star-kids`。

### 更新代码

**代码是 git clone 下来的（方式 A，推荐）** —— 一条命令搞定：

```bash
# 从 GitHub 拉最新代码 → 同步到运行目录 → 重启 → 健康检查
sudo bash /opt/star-kids-src/deploy/linux/update.sh

# 只想看看有没有新版本，不动服务
sudo bash /opt/star-kids-src/deploy/linux/update.sh --check
```

`update.sh` 的保证：依赖清单没变就跳过 `pip`；新版本起不来会在 40 秒内
**自动回滚到上一个提交**；`data/`、`uploads/`、`rules.yaml` 从头到尾不会被碰。
完整流程见 `docs/GIT.md` 第四节。

**还是直接拷贝代码的（方式 B）**：

```bash
# 传新版代码到服务器后
sudo systemctl stop star-kids
sudo cp -a /tmp/kids-reward-new/app /tmp/kids-reward-new/static /opt/star-kids/
sudo chown -R star-kids:star-kids /opt/star-kids
sudo systemctl start star-kids
```

> `data/`、`uploads/`、`rules.yaml` 都不要覆盖，那是你的数据。

---

## 七、故障排查

**服务起不来：**

```bash
journalctl -u star-kids -n 50 --no-pager
```

最常见的两个原因：Python 依赖没装好（看 pip 报错）、端口被占用（换端口）。

**端口被占用：**

```bash
ss -tlnp | grep 8777
```

**手机上打不开：**

```bash
# 先看服务本身通不通
curl http://127.0.0.1:8777/health
# 再看有没有监听在正确的地址上
ss -tlnp | grep 8777
```

如果本机通、局域网不通，检查 `run.py` 是否带了 `--lan`（没带就只监听 127.0.0.1）。
Debian 10 以后如果开了 nftables/ufw：

```bash
sudo ufw allow 8777/tcp comment 'star-kids'
```

**数据库报错 "database is locked"：**
通常是把数据放在了 NFS/SMB 网络挂载上。SQLite 的锁依赖真实文件系统，
网络文件系统上锁语义不可靠——**把数据目录挪回本地磁盘**。

**运行一段时间变慢：**
每月执行一次 `VACUUM` 整理碎片即可（服务不用停）：

```bash
sqlite3 /opt/star-kids/data/kids.db "VACUUM;"
```

---

## 八、这个 systemd 配置做了哪些安全加固

安装脚本写入的 service 文件里包含下面这些，不是为了显得专业，
而是为了**万一有漏洞被人利用，危害也限制在最小范围**：

- `User=star-kids` —— 用没有 shell 登录权限的系统账号运行
- `NoNewPrivileges` —— 进程无法提权
- `ProtectSystem=strict` —— 系统分区只读，只有 `ReadWritePaths` 指定的数据目录可写
- `ProtectHome` —— 读不到其他用户的家目录
- `PrivateTmp` —— 独立的 /tmp
- `MemoryMax=400M` —— 万一内存泄漏也不会拖垮整台盒子
- `Restart=always` + `StartLimitBurst` —— 崩溃自动拉起，但连续失败会限速，避免写坏 SD 卡

另外 `KIDS_SECRET` 在安装时随机生成并存在 `/etc/star-kids.env`（权限 600），
不再使用代码里那个公开的默认值。
