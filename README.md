# Hourlink 时间有价

面向学习互助社区的需求与能力交易原型。平台根据本单需求及相关能力证据推荐人选，估计工时和小时参考价，并生成付费、时间互换或互换补差方案。用户确认完整协议后，分阶段交付、验收和结清。

界面使用繁体中文。全部账户、能力历史、基准、评分参数和资金均为演示数据，无真实支付或提现。核心流程不依赖 AI 或外部 API。

## 本地启动

需要 Node.js 22 或更新版本、Python 3.12 和 uv。依赖安装阶段需要网络；安装完成后应用只访问本机。

```bash
cp .env.example .env
./scripts/start.sh
```

打开 [本地应用](http://127.0.0.1:8000)。第一次访问自动进入周予安的演示会话。右上角切换需求者、服务者或复核员身份；演示登录不代表实名认证。

前后端分开开发：

```bash
uv sync --locked
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
# 另一个终端
cd frontend
npm ci
npm run dev
```

## 推荐规则

- 先过滤必需技能、任务难度、服务方式、地点、时间冲突与在途限制。
- 质量按正确性 50%、完整性 30%、自主完成 20%评分。相关证据取最近最多 20 项的中位数，同一对手限最近一笔，作品及测评合计最多两项。
- 推荐分为适配度 60%、质量 30%、证据充足度 10%。无有效证据的候选进入待验证组，不生成质量分或能力溢价。
- 小时参考价为类目演示基准乘能力系数。成果型工时在至少三名独立对手的同子类、难度、工作量样本足够时取中位数，否则采用模板估计。
- 本单建议、私人接受条件、实际成交条款和实际耗时分别保存。实际耗时不自动改价。

完整规则见 [规则 v0.3](docs/rules-v0.3.md)；API 见 [接口契约](docs/api-contract.md) 和 [本机 OpenAPI](http://127.0.0.1:8000/docs)。

## 时间价值、分歧与机制证据

平台先生成本单时间价值估计，再由双方确认或调整。[理论与数学模型](docs/contextual-value-model.md)以Becker时间配置、MCDA及Nash协商为依据，分列投入金额与目标帮助指标；不把帮助分换成现金。提案可确认目标、查看偏好敏感性，并带入合法的目标时长＋补差方案。[模型实验页](http://127.0.0.1:8000/value-model)展示“更多分钟未必增加本次帮助”的4组实验；[公开结果](docs/value-model-results.json)可复现。参数和权重是演示假设，真实效果待量测。

含双向服务的提案提供“这份服务，对你值多少”：本人判断收到的整份服务价值，与平台参考并列。只有本人勾选分享才对方可见，私人底线始终不公开；差异不自动改价，数量或范围变更后旧判断失效。

[本地机制实验](http://127.0.0.1:8000/mechanism)实际运行18组隔离控制案例，可调整能力、准备、时段和接受条件，展示无证据、无交集和无法合法分轮。使用生产规则，不改现有订单。另比较30／60分钟先行限制保护的投入与增加的验收操作。详见 [机制证据](docs/mechanism-evidence.md) 和 [官方资料支持的替代方案对照](docs/competitive-comparison.md)。

[匿名试用页](http://127.0.0.1:8000/study)提供十分钟任务及仅下载到本人装置的反馈表。真实试用证据尚待收集，不能将演示角色或自动化测试计为用户研究；[研究记录](research/README.md)明确区分发起人需求、合成实验和实际反馈。

本实现沿用原 CoValue 仓库历史；原赛题与模型规划文档保留供追溯，当前可执行规则以v0.3为准。

## 五个独立演示案例

| 案例 | 操作及预期 |
|---|---|
| 付费成功 | 比较三名候选。时薪 HK$300、250、200，工时 30、60、90 分钟，总价 HK$150、250、300。选择林知行，双签后逐阶段模拟预留、交付、验收。 |
| 没有可行方案 | 打开预置提案，计算辅助接受区间。结果为 NO_FEASIBLE_PLAN，不激活订单、不扣信用。 |
| 部分履约后退出 | 首阶段 HK$60 已验收释放，第二阶段 HK$90 已预留。申请退出，双方确认取消第二阶段、退回 HK$90。 |
| 时间互换 | 60 分钟表格辅导换 90 分钟英语交流，两轮 30↔45。先履约后退出，原 45 分钟回报义务仍保留。 |
| 互换补差 | 固定 60↔60 的服务组合，周予安模拟补差 HK$50。每轮双方服务均验收后才释放补差。 |

切换案例不会污染其他案例。重置和脱敏事件导出需要复核员身份。也可用 CLI 重置：

```bash
uv run python -m scripts.reset cash
```

数据库位于 `backend/data/`，不进入 Git。刷新页面保留状态。关闭演示模式会禁用演示登录、案例管理及事件导出；本原型未提供生产账号系统。

## 检查

```bash
uv run pytest -q
uv run ruff check backend scripts/reset.py scripts/audit_closed_loop.py
cd frontend && npm run build
# 服务运行时重新生成 API 类型
npm run contract
```

完整闭环验证使用独立临时数据库和服务，不会重置正在浏览的演示数据：

```bash
HOURLINK_TEST_PORT=8002 ./scripts/verify-closed-loop.sh
```

脚本执行后端测试、生产构建、浏览器完整交易流程和独立 SQLite 资金／时间对账。需要 Playwright 及 Chromium；默认使用本机 Codex 捆绑运行时，其他环境设置 `HOURLINK_PLAYWRIGHT` 为已安装的 Playwright 模块绝对路径。GitHub Actions 自动安装浏览器并执行相同验证。

浏览器覆盖发布、匹配、协商、双签、付费／互换／补差履约、退出、争议复核、证据评估更新、刷新和手机宽度。日志、截图及 trace 位于 `artifacts/browser/closed-loop/`，本地数据库快照位于 `tmp/closed-loop/snapshots/`，均不进入仓库。结果见 [测试报告](docs/test-report.md) 和 [闭环验收记录](docs/closed-loop-report.md)。

## 比赛材料

- [Pitch Deck 源文件](artifacts/pitch-deck.html) 与 [PDF](output/pdf/hourlink-pitch.pdf)
- [约三分钟操作演示](artifacts/hourlink-demo.webm)，包含讲解字幕，无语音
- [演示脚本](docs/demo-script.md)
- [六项补足状态与交付核对](docs/six-point-progress.md)

仓库只包含应用、模拟数据与生成的演示材料。原始赛事文件和运行中的会话数据库不进入提交包。

重新生成机制及Deck：`uv run python -m scripts.mechanism_experiments`、`uv run python -m scripts.build_deck`、`node scripts/render-deck.cjs`。后两步使用当前完整验收日志与录制截图，须先执行闭环验收。录制脚本使用独立8003端口与`tmp/recording/data`，按 [演示脚本](docs/demo-script.md)启动；不要将其指向正在浏览的演示数据库。

## 技术边界

后台是权限、金额和状态的唯一执行方。SQLite 开启外键，关键命令使用 BEGIN IMMEDIATE，并将状态、资金、事件与幂等结果放在同一事务内。重复请求不会重复记账，第二次签约原子检查需求锁、容量及时间。

公共候选响应不返回私人接受条件或证据正文。订单证据只供当事人与授权复核员读取。争议不自动形成全局违约；超时不自动验收、释放资金或豁免义务。

能力评分、预测区间和参考价尚未通过真实市场研究校准。分阶段规则增加验收次数，不能证明线下服务真实发生，不能保证追回损失。实际支付、身份核验、反欺诈和生产部署需后续设计。

## 项目结构

`backend/app/` 为 API、数据库、规则与种子模块；`backend/tests/` 为规则、交易和结清测试；`frontend/src/` 为 React 界面和生成契约；`fixtures/` 为案例定义；`docs/` 为规则、接口与演示说明。

开源框架依赖包括 React、Vite、TanStack Query、React Router、Lucide、FastAPI、Pydantic、SQLAlchemy 和 pytest；版本锁定于 npm 与 uv 锁文件。原创应用代码在本次工作区从零实现。
