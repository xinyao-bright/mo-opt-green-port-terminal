# 泊位岸桥联合调度对比与绘图代码

本代码包配套《知识引导的泊位岸桥联合调度算法与系统》。只提供实验工具，不预写性能结论。`kernel.py` 是当前后端纯算法快照，不导入 Flask、不读取业务数据库；输入 CSV 由你指定。

## 安装与快速检查

```powershell
python -m pip install -r requirements.txt
python test_model.py
python run_experiments.py --csv "D:\HuaweiMoveData\Users\xuexi\Desktop\temperate\ship_data(S1).csv" --budget 100 --population 8 --seeds 2 --out smoke
python plot_results.py --results smoke
```

快速运行仅检查程序能否完成，不足以支持性能结论。正式实验示例：

```powershell
python run_experiments.py --csv "ship_data(S1).csv" --budget 12000 --population 60 --seeds 20 --seed-start 42 --out results_main
python plot_results.py --results results_main
```

将 CSV 放到代码目录，或传入绝对路径。不同实验使用不同 `--out` 目录，防止混合模型与参数。程序输出可能耗时较长，具体时间由硬件、规模和可行解分布决定。

## 七组对照的准确含义

| 方法 | 用途 | 说明 |
|---|---|---|
| NSGA2-Repair | 完整机制 | 两种可行锚点、领域修复、约束支配、精英选择 |
| NSGA2-NoRepair | 修复消融 | 保留相同锚点，关闭初始和每代修复 |
| NSGA2-NoAnchor | 锚点消融 | 保留修复，关闭两种可行锚点 |
| NSGA2-None | 双重消融 | 同时关闭领域修复与两种可行锚点，完成 2×2 因子设计 |
| WeightedGA | 单目标对照 | 固定权重 0.4/0.3/0.3，固定尺度，保留修复与锚点 |
| RandomSearch | 搜索对照 | 独立随机采样，使用 NSGA 环境选择维护精英，保留相同锚点，不修复 |
| FCFS | 简单业务基线 | 按到港顺序在单个泊位串行服务，使用最大岸桥数；不是优化后的强启发式 |

这些是本项目统一约束下实现的算法对照，不是对参考论文模型的完整复刻，也没有复现文献中的实验数值。实验 NSGA2 使用与系统相同的算子和纯内核，但改用统一评价预算与独立随机数生成器，不能期待与系统“同种群、同迭代”逐位一致。

每次目标评价都计入预算，包括修复后的再次评价和用于固定尺度的两个锚点评价。修复函数自身的冲突计算不作为额外目标评价，但其耗时计入总时间，并单列 `repairSeconds`。FCFS 是确定性单次基线，不能通过重复同一结果伪造随机实验样本量。

## 核算参数与敏感性

完整 2×2 消融与其他基线的可恢复并行运行：

```powershell
python run_study.py --csv "ship_data(S1).csv" --out results_main --budget 12000 --population 40 --seeds 20 --workers 4
```

每个方法、种子的结果单独保存，意外中断后用相同参数重跑可继续未完成任务。并行任务共享主机，耗时只作开销描述，不作为严格独占硬件速度排名。修复和锚点的作用必须分别解释，不能将锚点效果全部归功于修复。

```powershell
python run_experiments.py --csv "ship_data(S1).csv" --budget 12000 --population 60 --seeds 20 --coordination-cost 0 --out sensitivity_k0
python run_experiments.py --csv "ship_data(S1).csv" --budget 12000 --population 60 --seeds 20 --coordination-cost 40 --out sensitivity_k40
python run_experiments.py --csv "ship_data(S1).csv" --budget 12000 --population 60 --seeds 20 --service-aux-ratio 0.5 --out sensitivity_aux05
```

可调参数还包括 `--grid-factor`、`--electricity-price`、`--berths`、`--qcs`、`--max-qcs`。默认电网因子为 2023 年全国均值 0.5306；默认电价 0.8、协同单价 20、作业期辅机倍率 1 均为明确的场景假设。资源配置采用后端出厂成本系数 `auv_money=1`、`qc_money=3`，与截图中激活配置可能不同。所有方法必须使用同一实例和同一核算参数。

当前线性效率下，岸桥电量 `H*q*power*load` 与 `q` 无关。统一电网因子和统一电价改变常数基线；不要据此宣称调度减少了岸桥总电量。新增的岸桥对协同费用为代理项，需用 κ=0 等实验判断结论是否依赖该项。

## 输出与图形

- `metadata.json`：参数、环境、输入哈希和核算口径。
- `runs.json`：所有运行的真实前沿、编码、逐代轨迹、评价次数与修复统计。
- `solutions.csv`：每个方法、种子、方案的三项目标，便于自行作图。
- `metrics.csv`：HV、经验 IGD、耗时、可行评价率、修复成功率。
- `metric_definition.json`：全组共享的归一化范围、HV 参考点和经验参考集。
- `paired_statistics.json`：与完整方法之间的配对 HV 差值 bootstrap 区间；少于 5 个配对种子时不输出推断。
- `figures/`：三目标投影、质量分布、时间与可行率、收敛轨迹、修复消融，每张同时输出 PDF、SVG、300 dpi PNG。

绘图配色在 `plot_results.py` 的 `COLORS` 修改，标签默认英文，适合论文图。所有图读取真实数据，未预设谁更好。无可行解的运行 HV 为 0、IGD 留为缺失；禁止将失败运行删除后只报成功均值。

HV 的参考点统一为归一化后的 (1.1,1.1,1.1)，IGD 参考集是本组最终可行解的非支配并集，**不是真实 Pareto 前沿**。跨参数目录的归一化基准不同，不要直接比较各自 HV 数值。小预算只用于冒烟验证；正式比较建议至少 20 个种子，并增加不同规模和资源紧张程度的实例，单个 S1 算例无法证明普遍优势。

## 旧目标函数

```powershell
python run_experiments.py --csv "ship_data(S1).csv" --objective legacy --budget 12000 --population 60 --seeds 20 --out results_legacy
```

该模式只切换为原始目标函数，仍使用统一约束与修复后的真实可行性校验，**不是旧系统整体行为的逐字复现**。旧目标混合了电量与碳质量，成本范围也不同；不得把旧版与新版原始数值直接求百分比作为减排或节省率。若比较目标设计，应把双方选出的方案重新代入同一评价口径，或比较方案结构并清楚报告假设。

## 与现有系统的关系

当前项目已经直接使用 physical-v2 目标函数，前端加入核算参数和分项解释，历史与 Excel 导出带版本快照。`decode_solution` 和 `calculate_penalty` 保持不变。修复后的评价一致性、可行初始锚点和只输出可行方案的检查已同步更新。

旧的软著材料保留原文件；其中涉及旧目标公式和推荐规则的描述，不再代表本次修改后的计算口径。新的算法报告以当前代码为准。
