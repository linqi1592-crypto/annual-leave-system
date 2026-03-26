# 年假查询系统 v1.3

飞书工作台年假查询应用，支持复杂计算规则（法定+福利+结转）、飞书免登自动识别、HR后台手工调整、批量导出、年终清算等功能。

## 功能特性

### 员工端（v1.3）
- ✅ **飞书免登** - 自动识别用户，无需手动选择
- ✅ **年假余额三栏展示** - 当年额度 | 上年结转 | 已使用
- ✅ **负数余额显示** - 透支额度红色标注
- ✅ **请假明细列表** - 按年份筛选
- ✅ **计算规则说明** - 展示自动计算的司龄
- ✅ **结转到期提醒** - 上年结转显示到期日期

### HR后台（v1.3）
- ✅ **员工切换查询** - HR可查看所有员工年假
- ✅ **手工调整额度** - 修正上年剩余年假（操作人自动记录）
- ✅ **调整记录查询** - 查看历史调整记录
- ✅ **批量导出** - CSV/Excel 格式导出全员数据
- ✅ **年终清算** - 年度结转与清零处理（预览+确认）

## 技术栈

- **后端**: Python 3.9+ + FastAPI
- **认证**: JWT + 飞书免登
- **数据库**: SQLite（调整记录 + 年终清算记录）
- **数据源**: 飞书多维表格（员工信息 + 请假记录）
- **前端**: HTML5 + JavaScript + 飞书 JSSDK

## 快速启动

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
# 编辑 .env 文件，填入正确的配置
```

必需配置项：
- `FEISHU_APP_ID` - 飞书应用 ID
- `FEISHU_APP_SECRET` - 飞书应用 Secret
- `FEISHU_APP_TOKEN` - 多维表格 Token
- `EMPLOYEE_TABLE_ID` - 员工表 ID
- `LEAVE_TABLE_ID` - 请假记录表 ID
- `JWT_SECRET_KEY` - JWT 签名密钥
- `HR_USERS` - HR 用户的飞书 Open ID

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
python3 main.py
```

服务将在 http://localhost:8000 启动

### 4. 前端配置

前端文件位于 `frontend/index.html`，部署到飞书工作台：

1. 修改飞书 App ID（文件内搜索 `FEISHU_APP_ID`）
2. 将文件部署到 Web 服务器或 CDN
3. 在飞书管理后台配置应用首页地址

## API 接口

### 认证接口

| 接口 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/auth/login` | POST | 飞书免登登录 | 公开 |
| `/api/auth/me` | GET | 获取当前用户信息 | 需登录 |

### 员工端

| 接口 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/employees` | GET | 获取员工列表 | 需登录 |
| `/api/leave/balance` | GET | 查询年假余额 | 员工/HR |
| `/api/leave/history` | GET | 查询请假明细 | 员工/HR |
| `/api/leave/rules` | GET | 查询计算规则 | 员工/HR |

### HR后台

| 接口 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/admin/adjustments` | GET | 查询调整记录 | HR |
| `/api/admin/adjustments` | POST | 创建调整记录 | HR |
| `/api/admin/adjustments/{id}` | DELETE | 撤销调整记录 | HR |
| `/api/admin/export` | GET | 导出年假数据 | HR |
| `/api/admin/year-end/preview` | GET | 年终清算预览 | HR |
| `/api/admin/year-end/confirm` | POST | 确认年终清算 | HR |
| `/api/admin/year-end/history` | GET | 查询清算历史 | HR |

## 年假计算规则

### 法定年假（按社保工龄）
- < 12个月：0天
- 12-180个月：5天
- 180-240个月：10天
- > 240个月：15天

### 福利年假（按司龄，自动计算）
v1.3 根据「入职日期」自动计算司龄：
- < 12个月：6天（新人福利）
- 12-180个月：1天 + 司龄年数
- >= 180个月：司龄年数

### 封顶规则
- 一般员工：≤12天
- 老员工（工龄>240月）：≤15天

### 结转规则
- 上年剩余最多结转3天
- 有效期至次年3月31日
- v1.3 支持负数余额（透支），但结转为0

## 项目结构

```
年假查询系统/
├── backend/                    # 后端代码
│   ├── config.py              # 配置文件
│   ├── feishu_client.py       # 飞书API客户端
│   ├── leave_calculator.py    # 年假计算引擎（含司龄自动计算）
│   ├── adjustment_db.py       # 调整记录数据库
│   ├── auth.py                # 飞书免登 + JWT认证
│   ├── export.py              # 批量导出功能
│   ├── year_end.py            # 年终清算功能
│   ├── main.py                # FastAPI主服务
│   ├── requirements.txt       # 依赖
│   ├── start.sh               # 启动脚本
│   └── .env.example           # 环境变量模板
├── frontend/                   # 前端代码
│   └── index.html             # 主页面（飞书JSSDK免登）
├── docs/                       # 文档
│   ├── 开发计划_v1.3.md       # v1.3开发计划
│   ├── 设计方案_v1.1.md       # v1.1设计文档
│   └── ...
├── tests/                      # 测试
│   └── test_leave_calculator.py
└── DEPLOY_v1.3.md             # v1.3部署配置指南
```

## v1.3 更新日志

### P0 优先级（必须）
- ✅ 飞书免登自动识别用户 - 员工打开应用自动显示自己的年假信息
- ✅ 调整记录操作人身份验证 - 操作人信息从登录态自动获取，不可伪造

### P1 优先级（优化）
- ✅ 余额卡片分栏展示 - 当年额度/上年结转/已使用 三栏展示
- ✅ 负数余额兼容性 - 支持透支场景，负数红色显示
- ✅ 批量导出年假数据 - 支持 CSV/Excel 格式
- ✅ 年终清算流程 - 预览→确认→自动生成年结转记录
- ✅ 司龄递增自动化 - 根据入职日期自动计算司龄

## 部署检查清单

### 飞书后台配置
- [ ] 创建自建应用，获取 App ID 和 App Secret
- [ ] 开启「获取用户身份」权限
- [ ] 配置安全域名（前端部署地址）
- [ ] 配置工作台首页地址

### 多维表格准备
- [ ] 员工表添加「飞书Open ID」字段
- [ ] 填写现有员工的飞书 Open ID
- [ ] 确认「入职时间」字段格式正确

### 后端部署
- [ ] 配置 .env 环境变量
- [ ] 安装依赖 `pip install -r requirements.txt`
- [ ] 启动服务 `python main.py`
- [ ] 测试 API `curl http://localhost:8000/`

### 前端部署
- [ ] 修改 `FEISHU_APP_ID`
- [ ] 部署到 Web 服务器
- [ ] 配置飞书工作台首页地址
- [ ] 在飞书客户端测试免登功能

## 详细部署文档

详见 [DEPLOY_v1.3.md](DEPLOY_v1.3.md)

## 注意事项

1. **App Secret 安全**: 请勿将 App Secret 提交到代码仓库，使用 .env 文件管理
2. **JWT 密钥**: 生产环境请使用强随机字符串作为 JWT_SECRET_KEY
3. **HR 权限**: HR_USERS 配置为飞书用户的 Open ID，逗号分隔
4. **数据权限**: 普通员工只能查询自己的年假信息，HR 可查看全部
5. **年终清算**: 清算操作不可逆，请谨慎操作

## 开发计划

- [x] v1.0: 基础功能（查询+计算）
- [x] v1.1: Code Review + 回归测试
- [x] v1.3: 飞书免登 + HR后台 + 年终清算 ✅
- [ ] v1.4: 性能优化 + 缓存机制
- [ ] v2.0: 审批集成 + 自动请假扣除

## 作者

犀甲 🦞
