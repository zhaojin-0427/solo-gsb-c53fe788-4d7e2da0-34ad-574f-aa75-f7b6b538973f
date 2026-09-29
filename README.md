# 实验室化学品相容性审查台

本地 Web 应用：维护化学品台账（CAS 号、浓度、体积、温度、容器材质）与储存分区，登记待执行的**转移 / 混合 / 废弃**事件，并依据**可编辑、按版本管理**的相容性规则，对每个同区组合和事件前后状态逐项判定。

- 后端：Python + FastAPI + SQLite
- 前端：浏览器原生 JavaScript（无构建步骤）
- 部署：Docker Compose 一键启动

## 功能概览

| 模块 | 说明 |
| --- | --- |
| 化学品 | 维护名称、CAS 号、标签（酸/碱/氧化剂/易燃…）、浓度、体积、温度、容器材质、所在分区 |
| 储存分区 | 维护储存分区及其说明 |
| 事件登记 | 登记待执行的转移、混合、废弃事件，含目标分区/容器材质、计划时间与执行顺序号 |
| 规则管理 | 五类规则：酸碱、氧化还原、放气、放热、容器腐蚀；按标签、浓度阈值、温度阈值、材质、事件类型匹配；规则按版本保存，当前版本可编辑，封存后只读 |
| 相容性审查 | 逐项判定同区组合、各化学品容器、按顺序模拟的每个事件后状态；命中禁止条目即判「禁止」，缺少必填数据判「需人工复核」；输出触发条件、最早冲突、需隔离对象；结果连同规则快照入库，引用固定版本可复现 |

## 快速开始（Docker Compose）

```bash
docker compose up --build
```

启动后访问：<http://localhost:8000>

SQLite 数据保存在名为 `chem-data` 的 Docker 卷中，容器重建不丢数据。首次启动会自动建表并写入演示数据（分区、化学品、12 条内置规则 v1、4 个待执行事件）。

## 本地开发（不用 Docker）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问 <http://localhost:8000>。数据库文件默认在 `data/app.db`（可用环境变量 `DB_PATH` 覆盖）。

## 规则条件说明

每条规则带一个 JSON 条件对象，所有字段均可选：

| 字段 | 含义 |
| --- | --- |
| `tag_a` + `tag_b` | 成对规则：两化学品分别带有这两个标签（无序） |
| `tag_self` | 单化学品规则（容器腐蚀类）：化学品带该标签 |
| `min_concentration_pct` | 任一化学品浓度 ≥ 该阈值才命中 |
| `min_temperature_c` | 任一化学品温度 ≥ 该阈值才命中 |
| `materials` | 容器材质命中列表之一（腐蚀类） |
| `event_types` | 仅在指定事件类型（transfer/mix/dispose）场景下评估 |
| `action` | `forbid`（禁止）或 `review`（需人工复核） |

判定语义：

- 命中 `forbid` 规则 → **禁止**；
- 规则所需数据（浓度/温度/材质）缺失、无法判定是否越限 → **需人工复核**；
- 已知数据已满足阈值时即使其余数据缺失，仍按规则判定。

## 主要 API

```
GET/POST/DELETE        /api/zones[/{id}]
GET/POST/PUT/DELETE    /api/chemicals[/{id}]
GET/POST/PUT/DELETE    /api/events[/{id}]
GET                    /api/rule-versions
POST                   /api/rule-versions/seal          # 封存当前版本并新建可编辑版本
POST                   /api/rule-versions/{id}/activate
GET/POST/PUT/DELETE    /api/rules[/{id}]                # 仅当前未封存版本可写
POST                   /api/reviews                     # 运行审查（可指定 version_id）
GET                    /api/reviews[/{id}]              # 历史记录与完整结果（含规则快照）
```

## 项目结构

```
├── app/
│   ├── main.py        # FastAPI 路由
│   ├── db.py          # SQLite 建表与种子数据
│   ├── engine.py      # 相容性规则引擎
│   └── static/        # 原生 JS 前端（index.html / app.js / style.css）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
