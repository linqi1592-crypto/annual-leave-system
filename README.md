# 年假查询系统

飞书工作台年假查询应用，支持复杂计算规则（法定+福利+结转），并提供HR后台手工调整功能。

## 功能特性

### 员工端
- ✅ 年假余额查询（剩余/已用/总额）
- ✅ 请假明细列表
- ✅ 计算规则说明
- ✅ 上年结转显示（含到期提醒）

### HR后台
- ✅ 手工调整上年剩余年假
- ✅ 调整记录查询
- ✅ 调整记录撤销

## 技术栈

- **后端**: Python + FastAPI
- **数据库**: SQLite（调整记录）
- **数据源**: 飞书多维表格（员工信息+请假记录）
- **前端**: HTML + JavaScript

## 快速启动

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
# 编辑 .env 文件，填入正确的 App Secret
```

### 2. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 3. 启动服务

```bash
./start.sh
```

或使用 Python 直接启动：

```bash
export FEISHU_APP_SECRET=your_secret
python3 main.py
```

### 4. 访问

- API 文档: http://localhost:8000/docs
- 前端页面: 打开 `frontend/index.html`

## API 接口

### 员工端

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/leave/balance` | GET | 查询年假余额 |
| `/api/leave/history` | GET | 查询请假明细 |
| `/api/leave/rules` | GET | 查询计算规则 |

### HR后台

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/adjustments` | GET | 查询调整记录 |
| `/api/admin/adjustments` | POST | 新增调整记录 |
| `/api/admin/adjustments/{id}` | DELETE | 撤销调整记录 |

## 年假计算规则

### 法定年假（按社保工龄）
- < 12个月：0天
- 12-180个月：5天
- 180-240个月：10天
- > 240个月：15天

### 福利年假（按司龄）
- < 12个月：6天（新人福利）
- 12-180个月：1天 + 司龄年数
- >= 180个月：司龄年数

### 封顶规则
- 一般员工：≤12天
- 老员工（工龄>240月）：≤15天

### 结转规则
- 上年剩余最多结转3天
- 有效期至次年3月31日
- 支持HR手工调整

## 项目结构

```
年假查询系统/
├── backend/              # 后端代码
│   ├── config.py         # 配置文件
│   ├── feishu_client.py  # 飞书API客户端
│   ├── leave_calculator.py # 年假计算引擎
│   ├── adjustment_db.py  # 调整记录数据库
│   ├── main.py           # FastAPI主服务
│   ├── requirements.txt  # 依赖
│   ├── start.sh          # 启动脚本
│   └── .env.example      # 环境变量模板
├── frontend/             # 前端代码
│   └── index.html        # 主页面
└── docs/                 # 文档
    └── 设计方案_v1.0.md  # 开发设计文档
```

## 注意事项

1. **App Secret 安全**: 请勿将 App Secret 提交到代码仓库，使用 .env 文件管理
2. **数据权限**: 员工只能查询自己的年假信息
3. **调整记录**: HR调整操作会记录日志，支持撤销

## 开发计划

- [x] Day 1: 环境搭建 + API联调
- [x] Day 2-3: 年假计算引擎
- [ ] Day 4: 前端页面完善
- [ ] Day 5: 集成测试
- [ ] Day 6: 上线试点

## 作者

犀甲 🦞
