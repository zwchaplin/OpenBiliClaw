# 架构设计

> 详细的系统架构文档，将在开发过程中持续完善。

## 系统概览

OpenBiliClaw 采用分层架构设计，从上到下依次为：

1. **用户交互层** — Chrome 浏览器插件（行为采集 + 推荐展示 + 对话交互）
2. **Agent 核心层** — 自研编排器 + Soul Engine + Discovery Engine + Recommendation Engine + Skill System
3. **Bilibili 接入层** — API 优先 + agent-browser 浏览器操作
4. **多层网状记忆存储** — Core / Episodic / Semantic / Working Memory

详见 [项目 Spec](spec.md) 中的架构图。

## 模块职责

### Agent Orchestrator (`agent/`)
- 任务调度和策略决策
- 多步推理和自省优化
- Skill 注册、发现和调度

### User Soul Engine (`soul/`)
- 行为数据分析和画像构建
- 四层理解模型（行为→偏好→动机→人格）
- 苏格拉底式用户对话

### Memory System (`memory/`)
- 五层网状记忆管理
- 跨层关联和双向修正
- 自我编辑和遗忘机制

### Content Discovery (`discovery/`)
- 多策略内容发现
- 内容评估（基于用户 Soul）
- 两阶段候选供给（primary + backfill）
- 候选分层、去重和缓存写入

### Recommendation Engine (`recommendation/`)
- 推荐排序
- 朋友式推荐表达生成
- 缓存候选与实时候选统一排序
- 个性化专题生成

### Bilibili Client (`bilibili/`)
- B 站 API 封装
- agent-browser 集成
- 登录态 / Cookie 管理

### LLM Providers (`llm/`)
- 统一的多模型接口
- Provider 注册和切换
- 成本和性能监控

### Storage (`storage/`)
- SQLite 数据库管理
- 向量索引
- 候选质量信号持久化与数据迁移
