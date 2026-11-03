# 通过 Cloudflare 外网访问

> **先看这一段再动手。**
> Cloudflare Tunnel 让我们不需要公网 IP、不开任何端口就能获得 HTTPS 域名，技术上是干净的方案。
> 但**中国大陆到 Cloudflare 的跨境链路质量不稳定**，晚高峰可能明显变慢或超时，这点没法回避。
>
> 所以正确的用法是：
> - **在家里** —— 直接用局域网地址 `http://192.168.x.x:8777`，又快又稳定，不要绕道 Cloudflare
> - **在外面（比如你在单位想给孩子的打卡点个通过）** —— 才用隧道
>
> 上线前请在自己手机用 4G 网络实测几次，确认能接受再长期依赖。

---

## 一、先分清两件完全不同的东西

很多人会把它们搞混，但它们不能互相替代：

| | Cloudflare **Tunnel** | Cloudflare **Workers / Pages** |
|---|---|---|
| 它是什么 | 一条从你的服务器到 Cloudflare 的**加密管道** | 运行代码的**无服务器平台** |
| 代码跑在哪 | 仍然跑在你自己的机器上 | 跑在 Cloudflare 的全球节点上 |
| 我们的系统能用吗 | ✅ **直接能用，一行代码都不用改** | ❌ **不能**，见下 |
| 需要付费吗 | 免费计划就够 | 免费额度有限 |

**为什么 Workers / Pages 跑不了这套系统？** 两个根本原因：

1. Workers 是无服务器函数，**没有持久进程**，每次请求都是独立的短生命周期调用。
2. **没有本地文件系统**，SQLite 这种单文件数据库无从存放；Workers 自己的数据库是 D1，
   数据模型要从 SQLAlchemy + SQLite 整套重写过去。

将来如果真的要做成千上百个家庭的多租户 SaaS，那确实应该迁移到 Workers + D1（或 DynamoDB），
那是**重写数据访问层**的工作量，不是部署能解决的。现阶段用 Tunnel 是成本最低的路径。

---

## 二、准备条件

- 一个域名（`.com` 或任意后缀均可，几十块一年）
- 域名 DNS 转到 Cloudflare 托管（在注册商那里改 NS 服务器）
- 服务器上一份正在运行的系统（见 `deploy/linux/`）

---

## 三、安装（推荐图形化方式，最省事）

1. 登录 Cloudflare 控制台 → 左侧 **Zero Trust** → **Networks** → **Tunnels**
2. 点 **Create a tunnel** → 选择 **Cloudflared** → 取个名字，比如 `home-kids`
3. Cloudflare 会生成一条安装命令（内含 token），在你的 Armbian 服务器上执行：

   ```bash
   curl -L --output cloudflared.deb \
     https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
   sudo dpkg -i cloudflared.deb
   sudo cloudflared service install <这里粘贴 Cloudflare 给你的 token>
   ```

   > ARMv7 老盒子用 `cloudflared-linux-armhf.deb`，x86 用 `-amd64.deb`。
   > 玩客云/N1 一般装 `armhf` 或 `arm64` 取决于你的 Armbian 版本，不确定就先 `uname -m`。

4. 回到网页，connector 显示绿色 **Healthy** 就说明隧道通了
5. 点 **Public Hostname** → **Add a public hostname**：

   | 字段 | 填什么 |
   |---|---|
   | Subdomain | `kids`（或你喜欢的） |
   | Domain | 选你的域名 |
   | Service → Type | `HTTP` |
   | Service → URL | `127.0.0.1:8777` |

6. 保存，用手机 4G 访问 `https://kids.你的域名.com` 试试

---

## 四、命令行方式（想写进配置文件管理就用这种）

```bash
# 1. 授权（会打开一个网址让你在浏览器里确认）
cloudflared tunnel login

# 2. 创建隧道
cloudflared tunnel create home-kids

# 3. 配置 /etc/cloudflared/config.yml
sudo mkdir -p /etc/cloudflared
sudo cp "$(dirname "$0")/config.yml.example" /etc/cloudflared/config.yml
sudo sed -i "s/CHANGE-ME/你的域名.com/" /etc/cloudflared/config.yml
```

改完配置文件里的 tunnel 名 UUID 和凭据路径后：

```bash
cloudflared tunnel route dns home-kids kids.你的域名.com
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

> **配置文件最后必须有一条兜底规则**（示例里那条 `http_status:404`），
> 否则 cloudflared 直接拒绝启动。这是它最常让人卡住的地方。

> **Dashboard 和配置文件模式不要混用。** 如果在网页控制台建的隧道，
> 改本地 `config.yml` 是**没有任何效果**的，路由以控制台为准。

---

## 五、三条重要设置

**① 让系统拿到真实访客 IP。**
不加处理的话，系统看到的所有请求都来自 `127.0.0.1`，登录限流会把所有人当一个人。
所以启动时要带 `--proxy`（`install.sh` 选模式 2 或 3 时已经带上了）：

```bash
/opt/star-kids/venv/bin/python run.py --proxy --port 8777
```

**② 用 Cloudflare Access 加一道前置口令（建议）。**
即使在太空隧道后面，把 `kids.域名.com` 放到公网以后任何人都能尝试登录。
在 Zero Trust → **Access** → **Applications** 里加一条策略，
限制只有**你自己的邮箱**（用一次性验证码登录）才能打开这个域名。
这样连登录界面都不会暴露给陌生人，是最省事的一层加固。

**③ 开启 WAF/机器人防护可选。** Zero Trust 里可以对这个 hostname 加简单的速率限制。

---

## 六、Windows 上也能用（先在现有电脑上试）

你不必等服务器到货，Windows 也有 cloudflared：

1. 从 <https://github.com/cloudflare/cloudflared/releases> 下载 `cloudflared-windows-amd64.msi` 安装
2. 管理员打开命令提示符：

   ```bat
   cloudflared service install <你在 Cloudflare 建的隧道 token>
   ```

3. 然后在现在的命令模式下启动服务（因为隧道要从本机转发）：

   ```bat
   python run.py --proxy
   ```

> 注意 Windows 版本的服务名称也叫 cloudflared，`sc query cloudflared` 可查状态。

---

## 七、效果如何，自己这样测

```bash
# 隧道健康状态
sudo systemctl status cloudflared

# 实时日志
sudo journalctl -u cloudflared -f

# 从外部能否访问（用手机热点或让朋友帮你试）
curl -I https://kids.你的域名.com
```

**关键测试：用手机断掉 WiFi、切到 4G 网络**打开几次，分别在早高峰、晚上八点、深夜各试一次。
如果经常转圈超过 3 秒，就不建议把这个域名作为日常入口，家里还是直接用局域网地址。

---

## 八、如果 Cloudflare 在国内确实不行，还有什么选择

按推荐顺序：

1. **IPv6 + DDNS** —— 现在宽带基本都有 IPv6，运营商给的 IPv6 地址通常是公网可达的。
   在路由器开放 IPv6 转发 + 用一个免费的 DDNS（如 dynv6），配置稍复杂但没有跨境。
2. **国内 VPS 中转（frp / Caddy 反向代理）** —— 一台最便宜的国内 VPS（几十块一年），
   用 frp 把家里的服务映射出去，全程国内链路，速度稳定，代价是一点点服务器费用。
3. **Tailscale / ZeroTier** —— 组网型 VPN，手机上装个小 App，不需要域名和公网 IP。
   痛点是你和家人每个人的设备都要装客户端，给 7 岁的孩子用不合适；
   另外其协调服务器在海外，国内首次连接有时也不稳定。

对这个产品最务实的做法其实是：**家里用局域网，爸爸妈妈在外面分别用 Cloudflare 远程审批就行**——
孩子并不会在外面使用这个系统。
