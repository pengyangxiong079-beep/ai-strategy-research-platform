# Pipeline V2 迁移与兼容

- `PIPELINE_V2=1`（默认）使新运行创建canonical目录和`run_state.json`。
- `WORKSPACE_V2=1`（默认）启用`streamlit_app.py`多页面工作台。
- 既有`app.py`与所有V1输出保留，不执行批量迁移。
- 缺少`run_state.json`的历史目录由Legacy Adapter只读映射；界面显示Legacy标识并禁用写操作。
- 新运行仍双写旧根目录交付物，保证现有CLI、Revision和Dashboard兼容；同时投影到`rendered/`等canonical目录。
- 回滚Workspace只需运行`streamlit run app.py`；关闭新run V2可设置`$env:PIPELINE_V2='0'`。

