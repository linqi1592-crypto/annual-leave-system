# Code Review 修复记录

## Review 意见汇总与修复状态

### 🔴 必须修复的问题（已修复）

| 序号 | 问题 | 修复方案 | 状态 |
|------|------|----------|------|
| 1 | App Secret 硬编码泄漏风险 | `.env.example` 全部使用占位符，`config.py` 移除所有默认值，启动时强制检查 | ✅ |
| 2 | CORS 全开 | 支持从环境变量 `CORS_ORIGINS` 配置允许的域名，生产环境建议限制 | ✅ |
| 3 | HR 接口没有鉴权 | 添加 `verify_feishu_auth` 依赖，所有 `/api/admin/*` 接口需要 Authorization Header | ✅ |
| 4 | POST 接口参数用 Query 而非 Body | `create_adjustment` 改用 Pydantic Model `AdjustmentCreate`，通过 Body 传参 | ✅ |
| 5 | 员工查找用姓名匹配 | 新增 `/api/employees` 接口，其他接口改用 `employee_id`（飞书记录ID）查询 | ✅ |

### 🟡 建议优化（已修复）

| 序号 | 问题 | 修复方案 | 状态 |
|------|------|----------|------|
| 6 | 前端员工列表写死 | 新增 `/api/employees` 接口，返回所有员工列表（含 ID、姓名、部门） | ✅ |
| 7 | 请假明细和计算规则页面未实现 | API 已存在，前端需对接（非后端问题，已在 README 标注） | - |
| 8 | `calculate_previous_year_remaining` 递归风险 | 重写为 `calculate_previous_year_remaining_v2`，直接传入 employee 对象避免重复查询 | ✅ |
| 9 | 日期解析缺时区处理 | 新增 `parse_timestamp_year()` 和 `format_timestamp()` 函数，统一使用 UTC 转换本地时区 | ✅ |
| 10 | 缺少日志 | 全模块添加 `logging`，关键操作记录 INFO，错误记录 ERROR | ✅ |

---

## API 变更说明

### 新增接口
```
GET /api/employees              # 获取员工列表（用于下拉选择）
```

### 接口参数变更
```
# 之前（使用 employee_name）
GET /api/leave/balance?employee_name=张三

# 之后（使用 employee_id）
GET /api/leave/balance?employee_id=recXXXXXXXX
```

### HR 接口鉴权要求
所有 `/api/admin/*` 接口现在需要 Header：
```
Authorization: Bearer {user_access_token}
```

**注意**：当前鉴权为简化实现，生产环境应调用飞书 API 验证 token 有效性并检查用户角色。

---

## 环境变量变更

### 新增变量
```bash
# CORS 配置（生产环境必填）
CORS_ORIGINS=https://applink.feishu.cn,https://your-domain.com

# 时区设置
TIMEZONE=Asia/Shanghai

# 飞书安全凭证
FEISHU_ENCRYPT_KEY=your_encrypt_key_here
FEISHU_VERIFICATION_TOKEN=your_verification_token_here
```

### 修改要求
`.env` 文件中的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_APP_TOKEN` 不再提供默认值，必须手动配置，否则启动时报错。

---

## 待办事项

- [ ] 前端适配：使用 `/api/employees` 获取员工列表，改用 `employee_id` 查询
- [ ] 前端实现：对接请假明细和计算规则 API
- [ ] 生产鉴权：完善飞书 token 验证和用户角色检查
- [ ] 部署配置：设置 `CORS_ORIGINS` 限制允许的域名
