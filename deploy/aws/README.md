# 部署到 AWS EC2（亚马逊云）

先看第一节再动手。**AWS 的免费是有期限、有条件、并且有几个会悄悄扣钱的坑**
—— 这套系统是给孩子每天用的，选错方案，一年后要么掏钱，要么手忙脚乱地搬家。

## 一、先算清楚这笔账（2026 年版）

### 免费额度只给 12 个月

| 项目 | 免费额度 |
|---|---|
| 实例 | 每月 750 小时 `t3.micro` / `t2.micro`（1 核 1 GB 内存） |
| 硬盘 | 30 GB EBS（gp2 / gp3） |
| 流量 | 出网每月 100 GB |

**12 个月一到，这些全部按量收费**（t3.micro 大约每月 7～8 美元）。
对新注册的账号来说，这是个试用套餐，不是永久免费。

### 2026 年最容易被忽略的一条：公网 IPv4 要钱

自 2024-02-01 起，AWS 对**所有账号（包括免费套餐）**的公网 IPv4 地址按
**$0.005/小时** 收费 —— 一个月就是 **约 $3.6**，实例本身免费也照样收。

所以真正的成本取决于你怎么连它：

| 方案 | 月成本 | 需不需要域名 | 说明 |
|---|---|---|---|
| **A. 公网 IPv4 + 直接访问** | **≈ $3.6** | 不用 | 最省事，能用 IP 直接开，但要一直付 IPv4 钱 |
| **B. IPv6-only + Cloudflare Tunnel** | **$0**（12 个月内） | 需要，且要托管在 Cloudflare | 最省钱，也不暴露任何端口 |
| C. Lightsail 轻量服务器 | 固定价，含 IP | 不用 | 省心，但没有 12 个月免费 |

### 关于 12 个月后的现实选择

这套东西存的是孩子几个月的努力。一年后免费额度到期，你有三条路：

1. **继续付费** —— 每月大约 7～8 美元，加 IPv4 约 11 美元
2. **搬回家里的 ARM 小主机** —— 见 `deploy/linux/README.md`，一次搬完，之后零成本
3. **搬到 serv00** —— 免费，但有 90 天不登录就删号的条款，见 `deploy/serv00/README.md`

> 个人建议：如果家里有地方放小主机，**从一开始就该放在家里**。
> AWS 适合先拿它验证"全家在外面也能用"，等确定要长期用了再搬回去。

---

## 二、创建 EC2 实例

### 第 1 步 · 注册后立即设预算告警（重要）

注册 AWS 要绑信用卡。注册完马上去
**Billing → Cost Management → Budgets → Create budget**：

- 预算类型：成本预算
- 金额：**1 美元**
- 告警阈值：预测费用超过 80% 时发邮件

这样任何意外扣费，你会在当天就收到邮件，而不是月底看到账单。

### 第 2 步 · 启动实例

EC2 控制台 → **Launch instance**，按下面填：

| 选项 | 填什么 |
|---|---|
| Name | `star-kids` |
| AMI | **Amazon Linux 2023**（Ubuntu 24.04 也行，本文档两种都支持） |
| Instance type | **t3.micro**（页面必须显示"Free tier eligible"） |
| Key pair | 新建 .pem 密钥对，**下载后保管好，丢了就进不去了** |
| Storage | **30 GiB gp3**（免费额度上限，直接拉满） |
| Network settings | 见下面两种方案 |

#### 方案 A（要有公网 IPv4，多花 $3.6/月）

安全组放行：

- SSH `22` —— 来源选 **"My IP"**（只放行你家宽带 IP，别设 0.0.0.0/0）
- HTTP `80`、HTTPS `443` —— 来源 0.0.0.0/0（后面申请证书要用）

#### 方案 B（IPv6-only + 隧道，月成本 0）

1. 网络设置里点 **Edit**，取消勾选 **Auto-assign public IPv4**
2. 想登录，创建时展开 **Advanced details → IAM instance profile**，
   附加角色 **`AmazonSSMManagedInstanceCore`**
   （没有就先在 IAM 里建一个角色，选 EC2 + 该策略）
3. 装完后用控制台 **Connect → Session Manager** 直接进 shell ——
   不需要 22 端口、不需要公网 IP、不需要密钥文件，且免费

> 想省事就先用方案 A 建，装完确认能访问后，再决定是否释放 IPv4。
> 释放方式：Networking → Elastic IPs → 释放；注意**实例停止后未释放的弹性 IP 也会收费**。

### 第 3 步 · 连上去

```bash
# 本机（PowerShell / bash 都行），注意 .pem 权限必须是 600
chmod 600 ~/Downloads/star-kids.pem
ssh -i ~/Downloads/star-kids.pem ec2-user@你的公网IP      # Amazon Linux
ssh -i ~/Downloads/star-kids.pem ubuntu@你的公网IP        # Ubuntu
```

Amazon Linux 的默认用户是 `ec2-user`，Ubuntu 是 `ubuntu`，别用 root。

---

## 三、安装

### 第 1 步 · 上传代码

```bash
# 在本机执行（项目目录里）
scp -i ~/Downloads/star-kids.pem -r \
    "C:/WD/code/good study/kids-reward" \
    ec2-user@你的公网IP:/tmp/kids-reward
```

> **不要连 `data/textbooks` 一起传** —— 那是几百 MB 的教材 PDF，scp 会很慢。
> 装完在服务器上单独用 `tools/fetch_textbooks.py` 下载，或者干脆不装教材
> （t3.micro 的 30 GB 装得下，但每看一本要走一次流量）。

用 Session Manager 的话没有 scp，可以直接在服务器上：

```bash
git clone 你的仓库地址 /tmp/kids-reward
```

或者用面板里 File manager 上传 zip 后解压。

### 第 2 步 · 执行安装脚本

```bash
cd /tmp/kids-reward/deploy/aws
sudo bash install.sh
```

脚本会依次做完：识别发行版（dnf / apt）→ 装依赖 → 建专用无 shell 账号 →
部署到 `/opt/star-kids` → 建虚拟环境装依赖 → **生成随机密钥** → 初始化数据 →
装 systemd 服务并开机自启 → 配置每日自动备份。

中途会问一次访问方式：

```
1) Cloudflare Tunnel 专用（只听 127.0.0.1）     ← 推荐
2) 本机 Nginx 反代（只听 127.0.0.1，Nginx 对外）
3) 直接对外（听 0.0.0.0，需自己在安全组放行端口）
```

选 **2** 的话脚本会自动装 Nginx 并配好反代（含教材 PDF 分片读取需要的那几行）。

选完先用 `http://你的IP` 打开看看，能登录再去做 HTTPS。

### 第 3 步 · 打开看看

用 `dad` / `1234` 登录。**登录后第一件事是改掉这三个默认口令。**

---

## 四、让它能在外面访问

### 方案 1 · Cloudflare Tunnel（推荐）

这条路**不用在 AWS 上开任何入站端口**，也不需要公网 IPv4，配合免费 HTTPS 一步到位。

**完整步骤见 `deploy/cloudflare/README.md`** —— 里面推荐的是图形化方式：
在 Cloudflare 零信任面板建好隧道，拿到 token 后在服务器上执行一条 `cloudflared service install`，
不用手写任何配置文件。

EC2 是 x86_64 架构，装包这一条按你的系统选（那份文档给的是 ARM 的 .deb）：

```bash
# Amazon Linux 2023
curl -LO https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.rpm
sudo dnf install -y ./cloudflared-linux-amd64.rpm

# Ubuntu
curl -LO https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo apt install -y ./cloudflared-linux-amd64.deb

# 装好后用面板给的 token 注册为系统服务（会自动单元 + 开机启动）
sudo cloudflared service install <Cloudflare 面板给你的 token>
```

> 别用 `dnf install cloudflared` —— 默认源里没有这个包，会直接报"无法找到"。
> 也不要跳过 `service install` 直接 `nohup cloudflared tunnel run`，
> 那样机器一重启隧道就没了。

确认它在跑：

```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
```

- 需要域名，且 DNS 托管在 Cloudflare（免费）。
- **国外 IP + 国内访问**：Cloudflare 的线路在国内不稳定，速度时好时坏，
  请先用手机 LTE 试一次再决定要不要长期使用。
- 教材 PDF 每本 20 MB 左右，走隧道会算作出网流量，注意 100 GB/月的额度。

### 方案 2 · Nginx + Let's Encrypt（需要有公网 IPv4）

装的时候选了模式 2 的话，Nginx 已经装好了，只差证书：

```bash
# Amazon Linux 2023
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
# Ubuntu
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

> 前提条件：域名 A 记录指向这台机器的公网 IP（或 IPv6 的 AAAA 记录）。
> 注意 **80 端口必须放行**，Let's Encrypt 的验证要用到。

### 方案 3 · 直接用 IP:端口

选模式 3，然后在 AWS 安全组放行 8777/TCP。

**不建议长期使用** —— 全明文 http，口令在路上裸奔。临时调试可以。

---

## 五、数据安全

### AWS 的持久性 ≠ 你的备份

EBS 硬盘本身很可靠（多副本），但它防的是硬件故障，防不了这些：

- 你自己在控制台误删实例
- 手滑执行了 `rm -rf /opt/star-kids`
- 12 个月后忘了处理，或者把实例 terminate 了（**terminate 会连带删除硬盘**）

### 本地备份已经在跑

安装脚本挂了每日 03:17 的自动备份，保留 14 份：

```bash
ls -lh /opt/star-kids/backups/
sudo -u star-kids /opt/star-kids/backup.sh      # 想立刻来一份
```

### 必须再同步一份到别处

同一台机器上的备份不算备份。**在你自己的电脑上**加一条定时任务：

```bash
# 本机 crontab（Linux / macOS / WSL），每天 6:10 拉回家
10 6 * * * rsync -az -e "ssh -i ~/Downloads/star-kids.pem" \
    ec2-user@你的IP:/opt/star-kids/backups/ ~/star-kids-backup/
```

Windows 用任务计划程序 + WinSCP 命令行，或者手动隔几天下载一次。

> EBS 快照也行，但因为快照会占空间并单独计费，
> 对这点数据量来说，拉回家是更省也更稳的做法。

---

## 六、12 个月免费到期前

在日历里设两个提醒：**到期前 60 天** 和 **到期前 15 天**。

到时的选择见第一节。要搬回家的话：

1. 在服务器上执行一次备份，把 `backups/最新.tar.gz` 拉回本机
2. 按 `deploy/linux/README.md` 第五节把数据塞进新机器
3. **确认新机器能正常打开、数据完整，再去 terminate 旧实例**

两边**绝对不能同时运行** —— 两个进程各写各的数据库会造成数据分裂，
最后孩子的分数对不上。

---

## 七、常见费用陷阱

| 陷阱 | 后果 | 怎么避 |
|---|---|---|
| 开了第二台实例 | 750 小时是**所有区域合计**，两台就超 | 只开一台 |
| 硬盘超过 30 GB | 超出部分按量收费 | 就按 30 GB 建 |
| 公网 IPv4 一直挂着 | 每月约 $3.6 | 不用了就释放（第一节方案 B） |
| 实例停止但弹性 IP 没释放 | **照样收费** | 不用 IP 就释放掉 |
| 出网流量超 100 GB | 超出部分收费 | 教材 PDF 是流量大头，注意用量 |
| 12 个月后继续开着 | 每月 7～8 美元 | 提前在日历设提醒 |

---

## 八、常见问题

**服务起不来。**

```bash
journalctl -u star-kids -n 50 --no-pager
```

最常见的三个原因：Python 版本太低（Amazon Linux **2** 自带 3.7，必须换 Amazon Linux 2023）、
依赖没装上、端口被占用。

**本机 curl 通，外网打不开。**

```bash
curl -s http://127.0.0.1:8777/health     # 先看服务本身
```

本机通、外网不通，**八成是 AWS 安全组没放行**（AWS 有两层墙：安全组 + 系统内防火墙）。
EC2 控制台 → 实例 → Security → 入站规则。
如果用的是 Cloudflare Tunnel，则不需要任何入站规则，去查 `systemctl status cloudflared`。

**SELinux 拦住了。** Amazon Linux 2023 默认开启 SELinux enforcing。
真被拦时先临时关闭验证是否为它引起：

```bash
sudo setenforce 0
```

确认是 SELinux 的问题后别直接关掉，改用放行规则：

```bash
sudo ausearch -m AVC -ts recent | audit2allow -M star-kids
sudo semodule -i star-kids.pp
```

**上传教材 PDF 失败。** Nginx 的 `client_max_body_size` 脚本里已设成 400 MB，
如果走 Cloudflare Tunnel，注意 Cloudflare 免费版对单文件上传有 100 MB 限制
—— 这种情况让教材直接下到服务器本地（用 `tools/fetch_textbooks.py`）更省事。

**内存不足进程被杀。**

```bash
sudo dmesg | grep -i 'killed process'
```

t3.micro 只有 1 GB。系统里 `MemoryMax=500M` 已经限制了应用，
如果还是被 OOM，说明机器上还跑了别的东西，或者在同时处理多个大 PDF。

**想省事不折腾。** 直接买 Lightsail 或接受每月 $3.6 的 IPv4 费用，
比起处理 IPv6 + Session Manager + 隧道这三件套，时间成本上可能更划算。
