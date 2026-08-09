# Research Workspace V2 UX 审计

## 当前信息架构与用户路径

`app.py` 是单页应用：左侧历史选择，主区域依次出现 Scope 表单、状态、运行日志、Revision Center、Human Review、Data Coverage 以及多个报告 Tabs。主要路径是“填写长表单 → 在同页确认 → 等待 Agent → 在同页审核 → 在同页生成和修订”。

## 关键问题

- 页面同时承担创建、监控、审核、结果、质量、历史和修订，主要任务不清晰。
- Final 与多个中间 Markdown 以同级 Tabs 展示，审计材料淹没成果。
- “Revision Center / 人工审核”概念和输入区域混合；用户难以判断是在批准当前流程还是创建新版本。
- 1452 行页面代码直接处理文件、业务状态、Agent动作和渲染，复用与测试困难。
- 运行状态由大量 session state 字段推断，按钮可见性分散在页面判断中。
- Scope 不是分步向导；字段变更触发整页 rerun。
- 多处固定 columns、Tabs 和 expander，在窄宽度下密度高；专业 Dashboard 与控制台也有重复展示。

## 拟议信息架构

侧栏仅保留项目/run/revision选择与导航。主页面拆分为：项目、新建分析、运行概览、研究流程、人工决策、研究成果、数据与质量、修订与版本、设置。全局 Context Bar 只显示当前 topic、类型、地区、revision、状态和更新时间。

## 主要用户路径

新用户：项目 → 新建分析五步向导 → 运行概览 → 研究流程 → 人工决策 → 研究成果。质量阻塞自动指向数据与质量；报告完成后的修改进入修订与版本。V1 历史运行以 Legacy 只读方式打开。

## 设计原则

使用 Streamlit 1.61 原生 `st.navigation`、`st.Page`、`st.form`、bordered container、Material Symbols 和有界 `st.cache_data`。每页一个目标、最多一个 primary CTA；不嵌入专业 Dashboard，不使用多层 Tabs/Expanders，不把原始 JSON 默认暴露。

