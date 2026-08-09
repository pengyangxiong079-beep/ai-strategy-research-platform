# Workspace V2 信息架构

Streamlit是控制平面，Professional Dashboard是展示平面。侧栏只含run/revision选择器和导航；全局Context Bar显示topic、类型、地区、版本、状态和更新时间。

页面职责：项目负责选择；新建分析负责五步Scope；运行概览负责状态和下一步；研究流程负责阶段；人工决策负责Human Review；研究成果负责Final、导出和打开Dashboard；数据与质量负责覆盖、来源、Issue和Claim审计；修订与版本负责影响预览和版本比较；设置只负责系统默认值。

成果按三层分级：Level 1 Final/Dashboard/Export默认展示；Level 2 Research/Review/Fact/Human/Quality主动展开；Level 3 原始JSON、Search Log、Observation和Claim Ledger仅在数据与质量或调试模式出现。

