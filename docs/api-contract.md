# API 契约

完整请求类型见 [OpenAPI JSON](openapi.json)，本机交互文档为 `http://127.0.0.1:8000/docs`。业务路由前缀 `/api/v1`。前端生成请求类型位于 `frontend/src/contract.d.ts`；动态聚合响应按以下协议及后端实现返回。

Cookie `hour_session` 为12小时演示会话，HttpOnly/SameSite=Strict；`hour_case`选择独立数据库。授权身份只能由后端会话解析。金额为整数HKD分，时间为整数分钟，日期必须带时区。命令输入禁止未知字段。

除演示登录和演示专用重置外，写入命令必须提供唯一 `Idempotency-Key`。携带 Origin 时必须为当前来源。更新须提交 `expected_version`；合同确认另提交 `terms_version`，结清确认另提交 `agreement_version`。

## 主要接口

| 方法／路由 | 用途／权限 |
|---|---|
| GET /templates | 公开模板、参数、规则版本 |
| GET /listings | 市场；kind/category/q/owner_id/service_mode/location/time_start/time_end筛选 |
| POST /listings | 会话用户发布结构化需求或能力 |
| PATCH /listings/{id} | 发布者编辑，不能编辑激活中的需求 |
| POST /listings/{id}/analyze | 发布者分析缺失字段与任务要求 |
| GET /listings/{id}/matches | 三类排序、候选依据与预计投入，脱敏 |
| POST /capability-evidence | 本人提交作品／测评，不允许伪造交易历史 |
| POST /capability-evidence/{id}/review | 授权复核员审核及三项结构化评分 |
| POST /proposals | 双方之一建立提案，供给来自匹配或服务能力单 |
| POST /proposals/{id}/recommend | 双方之一生成推荐快照、默认方案 |
| POST /proposals/{id}/revise | 协商金额、模式、反向分钟、付款方、范围 |
| PUT/GET /proposals/{id}/preference | 只写／读自己的私人接受条件 |
| POST /proposals/{id}/calculate | 辅助协商，可返回NO_FEASIBLE_PLAN |
| POST /proposals/{id}/select | 原子选用当前候选，保留同服务接受条件并记录可执行轮数 |
| GET/PUT /proposals/{id}/perspectives | 当事人的价值判断；本人可见或自愿向对方分享，不改成交条款 |
| GET /mechanism | 演示18组隔离控制实验与取舍计数 |
| POST /mechanism/simulate | 有界参数实验，不写入现有业务案例 |
| POST /agreements | 按当前提案创建分轮合同 |
| POST /agreements/{id}/confirm | 本人双签，第二签原子激活 |
| POST /stages/{id}/fund | 本轮付款方模拟预留 |
| POST /obligations/{id}/submit | 原义务提供者交付及时间明细 |
| POST /obligations/{id}/accept | 原义务接收者验收、评分、确认贡献 |
| POST /agreements/{id}/withdraw | 当事人申请退出 |
| POST /agreements/{id}/disputes | 当事人发起订单／具体义务争议 |
| POST /disputes/{id}/review | 授权复核：恢复、验收、重做、结清、未解决 |
| POST /disputes/{id}/remedy | 授权复核补救结果 |
| POST /agreements/{id}/closeouts | 当事人逐项提出原义务及资金安排 |
| POST /closeouts/{id}/confirm | 双方确认同版本结清 |
| GET /me/orders /me/proposals | 仅本人参与的订单／提案 |
| GET /me/mock-account /me/time-summary | 本人模拟资金及时间 |
| GET /agreements/{id}/time-ledger | 当事人／复核员读取原义务时间 |
| GET /users/{id}/credit | 分类、角色履约事实及保护规则 |
| GET /review/queue | 仅复核员的作品／争议待办 |
| POST /demo/reset | 复核员重置当前案例 |
| GET /demo/events | 复核员导出脱敏事件，无私人条件或证据正文 |

匹配响应为 `candidates`、`excluded`、`recommended_id`、`budget_id`、`fastest_id`，每位候选有质量分、适配分、证据充足度、参考单价／范围、预计分钟／范围、总价、证据摘要、工时来源、证据摘要散列。提案 `data.recommendation` 保存规则及快照；订单 `data` 为签约条款快照，附阶段、义务、支付及结清等聚合。

## 命令示例

```http
POST /api/v1/proposals/{id}/recommend
Idempotency-Key: 9c153745-unique-command
Content-Type: application/json

{"expected_version": 1}
```

```json
{"expected_version": 1, "terms_version": 1}
```

以上为合同确认请求体。交付请求体包含 `expected_version`、`evidence`、`execution_minutes`、`preparation_minutes`、`travel_minutes`；验收包含 `expected_version`、`scores`的correctness/completeness/independence三项。

错误统一为 `{"code":"VERSION_CONFLICT","message":"内容已更新…","details":{"current_version":2}}`。422为输入错误，401缺会话，403权限，404不存在，409为状态／版本／业务限制。重要业务代码包含 `NO_FEASIBLE_PLAN`、`LISTING_TAKEN`、`POLICY_BLOCKED`、`RECOMMENDATION_STALE`、`INVALID_STATE`、`IDEMPOTENCY_CONFLICT`。前端以错误message展示具体拒绝依据。

候选选择请求为 `{"expected_version": 2, "value": 20000}`。互换 value 使用分钟，付费／补差使用港仙。选用候选提升提案及范围版本，将同服务私人接受条件迁移到新版本，在 `data.selected_rounds` 保存可执行轮数；手工修改清除此轮数和旧条件。ASSISTED 路径在建单及每次签署时检查当前共同接受范围。DIRECT 路径以明确双签为准。
