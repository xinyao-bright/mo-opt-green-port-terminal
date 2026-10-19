# EcoPort · 绿色低碳智能港口调度平台

基于 Flask 的船舶、泊位与岸桥联合调度系统，采用 NSGA-II、约束支配、领域修复与可行初始化锚点。当前核算版本为 `physical-v2`。

## 启动

Python 3.11 或更高版本；本次验证使用 Python 3.13。依赖文件固定为本机验证通过的版本。

在项目目录运行：

```powershell
python -m pip install -r requirements.txt
python start.py
```

启动后访问 http://localhost:5000，也可直接运行 `python app.py`。前端为 Flask 模板和原生 JavaScript，不需要运行 npm / Next.js。

## 新版界面

- 三套主题：云白（白底深字）、石墨黑（深灰底与薄荷绿）、深海蓝（蓝底与冰蓝）；文字、表单、图表和提示状态统一随主题切换。
- 登录与注册：港口插画、密码显示切换、中英文及窄屏布局。
- 调度工作台：CSV 导入预览与编辑、手动录入、船舶搜索、权重和算法参数设置。
- 调度结果：指标卡片、泊位作业时间线、Pareto 方案切换、运营指标和执行明细 CSV 导出。
- 泊位与资源：配置创建、编辑、激活、删除，以及泊位数量、岸桥效率和作业安全参数。
- 调度历史：日期筛选、详情查看、方案对比和原有 Excel 导出。

CSV 导入会追加到当前船舶池；需要替换时请先清空待调度船舶。首列为空表头的船舶文件会在预览时将首列标为 name，保持所有后续列的位置。

大数值指标以“万”为单位显示；悬停可查看完整数值。计算中进度仅表示等待状态，结果以服务端返回为准。

## 本地验证

使用独立临时数据库运行完整检查，不修改原数据库：

```powershell
python tools/theme_contrast.py
python tools/ui_smoke.py
python tools/ui_smoke.py --csv "你的船舶数据.csv"
```

使用测试数据预览新版界面：

```powershell
python tools/ui_smoke.py --serve --port 5001
```

预览账号：`qa_viewer`，密码：`Preview2026!`。这是独立测试环境，退出服务后不会写入正式数据库。

## 目录

- `app.py`、`auth.py`、`models.py`：后端算法、身份验证与数据模型。
- `scheduling_objectives.py`：有量纲的三目标、分项核算与偏好推荐。
- `competition/`：纯算法快照、七组对照与消融实验、绘图和核心测试。
- `templates/`：页面模板。
- `static/css/`：统一主题、布局与页面样式。
- `static/js/`：前端交互及接口调用。
- `static/i18n/`：语言资源。
- `tools/ui_smoke.py`：隔离验证和预览工具。

运行环境依赖见 requirements.txt，包含 Excel 导出使用的 openpyxl。工作台沿用 Bootstrap 及 Bootstrap Icons 的 CDN 资源。此项目无需安装 Next.js 或 React。

## 目标函数与边界

三个目标分别为 CO₂ 排放（kg）、船舶总在港时间（h）和模型调度成本（元）。约束违反度单独计算，不混入物理指标。界面显示等待辅机、作业辅机、岸桥购电的排放分项，以及等待、运行、电力和多机协同费用。

电价、辅机作业倍率和岸桥协同费用是可调整的场景参数；协同费用为待标定的代理项。在线性岸桥效率模型下，同一货量的岸桥总作业电量不随分配岸桥数量变化，不应据此声称增加岸桥直接节电。

原有解码与惩罚约束保持不变；当前空间顺序检查对所有异泊位船舶对生效，即使它们的作业时间不重叠。船长、潮汐、吃水和岸桥移动时间尚未进入约束。权重只作用于搜索后的候选推荐，不改变进化搜索目标。

## 实验复现

```powershell
python -m pip install -r competition/requirements.txt
python competition/test_model.py
python competition/run_study.py --csv "你的船舶数据.csv" --out results --budget 12000 --population 40 --seeds 20 --workers 4
python competition/plot_results.py --results results
```

完整方法与无修复、无锚点、双重消融构成 2×2 设计；另含固定权重 GA、随机搜索与 FCFS。详见 `competition/README.md`。数据库、个人申报证明、用户数据和临时构建文件不纳入公开源码。

