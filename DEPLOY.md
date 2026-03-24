# 年假查询系统 - 部署指南

## 环境要求

- Python 3.8+
- pip
- 服务器（支持外网访问，用于飞书回调）

## 部署步骤

### 1. 服务器准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
# 或
sudo yum update -y  # CentOS

# 安装 Python 和 pip
sudo apt install python3 python3-pip python3-venv -y
```

### 2. 拉取代码

```bash
# 进入你想存放代码的目录
cd /opt  # 或 /home/username

# 克隆代码
git clone https://github.com/linqi1592-crypto/annual-leave-system.git
cd annual-leave-system/backend
```

### 3. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置文件
nano .env  # 或 vim .env
```

**修改以下内容：**

```bash
FEISHU_APP_ID=cli_a94b9cb9af39dccc
FEISHU_APP_SECRET=你的真实App_Secret    # ⚠️ 必须修改！
FEISHU_APP_TOKEN=DH8rbr0abakqOks4nGNcF8Jn6c
```

**获取 App Secret：**
1. 打开 https://open.feishu.cn/app
2. 找到「年假查询」应用
3. 进入「凭证与基础信息」
4. 点击「重新生成」获取新 Secret

### 4. 安装依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 5. 启动服务

```bash
# 方式1：直接启动（测试用）
python main.py

# 方式2：使用启动脚本
chmod +x start.sh
./start.sh
```

服务默认运行在 `http://0.0.0.0:8000`

### 6. 测试 API

```bash
# 测试根路径
curl http://localhost:8000/

# 测试年假查询（替换为真实员工姓名）
curl "http://localhost:8000/api/leave/balance?employee_name=张三"
```

### 7. 配置飞书应用（重要！）

**获取服务器公网 IP 或域名：**

假设你的服务器地址是 `http://your-server-ip:8000`

**在飞书开发者后台配置：**

1. 打开 https://open.feishu.cn/app
2. 找到「年假查询」应用
3. 进入「网页应用」配置：
   - 桌面端主页：`http://your-server-ip:8000`
   - 移动端主页：`http://your-server-ip:8000`

4. 进入「事件订阅」配置（如需事件回调）：
   - 请求地址：`http://your-server-ip:8000/api/webhook`

5. 保存并发布应用

### 8. 生产环境配置（推荐）

**使用 systemd 守护进程：**

创建服务文件：
```bash
sudo nano /etc/systemd/system/annual-leave.service
```

写入内容：
```ini
[Unit]
Description=Annual Leave System
After=network.target

[Service]
Type=simple
User=www-data  # 或其他用户
WorkingDirectory=/opt/annual-leave-system/backend
Environment="PATH=/opt/annual-leave-system/backend/venv/bin"
ExecStart=/opt/annual-leave-system/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable annual-leave
sudo systemctl start annual-leave
sudo systemctl status annual-leave
```

**使用 Nginx 反向代理（推荐）：**

```bash
sudo apt install nginx -y

sudo nano /etc/nginx/sites-available/annual-leave
```

配置内容：
```nginx
server {
    listen 80;
    server_name your-domain.com;  # 或 your-server-ip

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/annual-leave /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 目录结构

```
annual-leave-system/
├── backend/
│   ├── main.py              # FastAPI 主服务
│   ├── feishu_client.py     # 飞书 API 客户端
│   ├── leave_calculator.py  # 年假计算引擎
│   ├── adjustment_db.py     # HR 调整数据库
│   ├── config.py            # 配置文件
│   ├── requirements.txt     # Python 依赖
│   ├── start.sh             # 启动脚本
│   ├── .env                 # 环境变量（你需要创建）
│   └── .env.example         # 环境变量示例
├── frontend/
│   └── index.html           # 前端页面
├── docs/                    # 文档
└── README.md
```

## 常见问题

### 1. 端口被占用
```bash
# 查看 8000 端口占用
sudo lsof -i :8000

# 杀掉进程
sudo kill -9 <PID>

# 或修改 start.sh 使用其他端口
```

### 2. 防火墙问题
```bash
# 开放 8000 端口
sudo ufw allow 8000
# 或
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 飞书 API 返回 401
- 检查 `.env` 中的 `FEISHU_APP_SECRET` 是否正确
- 确认 Secret 未过期

### 4. 无法读取多维表格
- 确认 `FEISHU_APP_TOKEN` 正确
- 确认应用有权限访问该多维表格

## 更新代码

```bash
cd /opt/annual-leave-system
git pull origin main

# 如果依赖有更新
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# 重启服务
sudo systemctl restart annual-leave
```

## 备份数据

调整记录数据库在 `backend/data/leave_adjustments.db`，建议定期备份：

```bash
cp backend/data/leave_adjustments.db backup/leave_adjustments_$(date +%Y%m%d).db
```

---

有问题随时找犀甲！🦞
