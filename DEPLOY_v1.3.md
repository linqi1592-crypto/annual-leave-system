# 年假查询系统 v1.3 部署配置指南

## 一、后端配置检查清单

### 1. 环境变量配置（backend/.env）

```bash
# 必填项
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_TOKEN=xxxxxxxxxxxxxxxxxxxx
EMPLOYEE_TABLE_ID=tblxxxxxxxxxxxxxx
LEAVE_TABLE_ID=tblxxxxxxxxxxxxxx
JWT_SECRET_KEY=your-strong-secret-key
HR_USERS=ou_xxxxxxxxxxxxxxxx,ou_yyyyyyyyyyyyyyyy
```

### 2. 飞书应用权限配置

在飞书开放平台 - 应用详情 - 权限管理，开通以下权限：

| 权限 | 用途 |
|------|------|
| `contact:user.base:readonly` | 获取用户 open_id |
| `auth:user.user_access_token:readonly` | 免登获取 user_access_token |
| `bitable:app:readonly` | 读取多维表格 |

### 3. 飞书免登配置

飞书开放平台 - 应用详情 - 安全设置：
- 添加「网页配置」H5 页面：填写应用首页 URL
- 开启「获取用户身份」能力

### 4. 多维表格字段检查

员工表（employee_table）必须包含以下字段：
- `发起人` - 员工姓名
- `工号` - 员工编号（可选）
- `入职时间` - 入职日期（用于自动计算司龄）
- `工龄(月)` - 社保工龄（月）
- `飞书Open ID` - 飞书用户唯一标识（v1.3 新增，用于免登匹配）

请假记录表（leave_table）必须包含：
- `申请人` - 请假人姓名（关联员工表）
- `请假类型` - 年假/事假/病假等
- `申请状态` - 已通过/已撤回/审批中
- `开始时间` - 请假开始日期
- `结束时间` - 请假结束日期
- `时长` - 请假天数
- `请假事由` - 请假原因（可选）

## 二、前端配置检查清单

### 1. API 基础地址配置

前端自动检测环境：
```javascript
const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000/api' 
    : '/api';
```

生产环境部署时，确保前端和后端在同一域名下，或配置正确的跨域。

### 2. 飞书 App ID 配置

在 `frontend/index.html` 中修改：
```javascript
const FEISHU_APP_ID = window.FEISHU_APP_ID || 'cli_xxxxxxxxxxxxxxxx';
```

或在 HTML 中注入：
```html
<script>
    window.FEISHU_APP_ID = 'cli_你的实际app_id';
</script>
```

## 三、API 接口对照表

| 前端调用 | 后端路由 | 权限 | 说明 |
|----------|----------|------|------|
| `POST /api/auth/login` | ✅ auth.py | 公开 | 飞书免登登录 |
| `GET /api/auth/me` | ✅ auth.py | 需登录 | 获取当前用户 |
| `GET /api/employees` | ✅ main.py | 需登录 | 获取员工列表 |
| `GET /api/leave/balance` | ✅ main.py | 员工/HR | 年假余额查询 |
| `GET /api/leave/history` | ✅ main.py | 员工/HR | 请假明细 |
| `GET /api/leave/rules` | ✅ main.py | 员工/HR | 计算规则 |
| `GET /api/admin/adjustments` | ✅ main.py | 仅 HR | 查询调整记录 |
| `POST /api/admin/adjustments` | ✅ main.py | 仅 HR | 创建调整记录 |
| `GET /api/admin/export` | ✅ export.py | 仅 HR | 导出年假数据 |
| `GET /api/admin/year-end/preview` | ✅ year_end.py | 仅 HR | 年终清算预览 |
| `POST /api/admin/year-end/confirm` | ✅ year_end.py | 仅 HR | 确认年终清算 |

## 四、部署步骤

### 1. 后端部署

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值

# 启动服务
python main.py
# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. 前端部署

前端是单文件 `index.html`，可直接部署到：
- Nginx 静态资源
- 飞书工作台 H5 应用
- CDN

```bash
# 如果使用 Nginx
cp frontend/index.html /var/www/html/leave/
```

### 3. 飞书工作台配置

飞书管理后台 - 工作台 - 应用管理：
- 添加「年假查询系统」应用
- 配置首页地址：`https://your-domain.com/leave/`
- 配置 PC 端首页地址（同上）
- 开启移动端适配

## 五、常见问题排查

### 问题1：飞书免登失败

**现象**：前端提示「获取授权码失败」

**排查**：
1. 检查 `FEISHU_APP_ID` 是否正确
2. 检查飞书应用是否开启「获取用户身份」权限
3. 检查当前页面域名是否在飞书应用的安全域名列表中

### 问题2：登录后显示「未找到员工信息」

**现象**：登录成功但提示找不到员工

**排查**：
1. 检查员工表的「飞书Open ID」字段是否已填写
2. 检查多维表格权限，应用是否有读取权限
3. 查看后端日志，确认 open_id 匹配逻辑

### 问题3：年假计算不正确

**现象**：年假余额与预期不符

**排查**：
1. 检查员工表的「入职时间」字段格式（支持时间戳或日期字符串）
2. 检查「工龄(月)」字段是否正确
3. 查看 `/api/leave/rules` 返回的计算规则详情

### 问题4：导出功能失败

**现象**：点击导出没有反应

**排查**：
1. 检查是否安装了 `openpyxl`（Excel 导出依赖）
2. 检查 HR 权限配置是否正确
3. 查看浏览器 Network 面板，检查接口返回

### 问题5：CORS 跨域错误

**现象**：浏览器控制台显示 CORS 错误

**解决**：
1. 开发环境：设置 `CORS_ORIGINS=*`
2. 生产环境：设置为实际域名 `CORS_ORIGINS=https://your-domain.com`

## 六、数据迁移（v1.1/v1.2 升级到 v1.3）

### 1. 数据库迁移

v1.3 自动执行，无需手动操作：
- `adjustments` 表自动添加 `created_by_open_id` 字段
- 新增 `year_end_settlements` 表
- 新增 `year_end_settlement_details` 表

### 2. 员工表数据迁移

需要为现有员工补充「飞书Open ID」：

```python
# 数据迁移脚本示例
# 运行一次即可
from feishu_client import feishu_client

employees = feishu_client.get_employee_records()
for emp in employees:
    name = emp.get("fields", {}).get("发起人")
    # 调用飞书 API 根据姓名查询 open_id
    # 然后更新员工表
```

## 七、联系方式

部署遇到问题？检查：
1. 后端日志输出
2. 浏览器开发者工具 Network 面板
3. 飞书开放平台 - 应用详情 - 日志查询
