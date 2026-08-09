# Workspace V2 设计系统

采用8px间距、1360px最大内容宽度、8px圆角、中性背景与单一蓝色主色。状态只使用六类语义色，并始终同时显示文字。使用Material Symbols，不用Emoji作为核心导航。

优先使用Streamlit 1.61原生组件：`st.navigation`、`st.Page`、`st.form`、bordered container、`st.badge`、`st.segmented_control`、`st.dataframe`。横向KPI使用可换行horizontal container；固定对比才使用columns。自定义CSS集中在`ui/design_tokens.py`，只处理内容宽度、文本换行和窄屏布局。

每页最多一个primary CTA；危险、覆盖或高额度动作必须确认。技术错误使用error，研究限制使用warning/info。最终Dashboard不嵌入iframe，通过CCv2组件在新标签页打开自包含HTML。

