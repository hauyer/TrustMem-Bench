# 公开流先导完整性复核

请求路由gpt-6.1-sol/ultra，新上下文`/root/public_pilot_audit`。实际模型身份未独立核实，same-family/provisional；不是外部人工同行评议。下列为审阅回复原文。

**WARN — 当前有限结论通过完整性核查；没有发现阻断性造假、漏计或结果篡改问题。** 本批仍不足以支持正式确认或记忆系统排名。审查为 same-family/provisional；实际模型身份未核验。仅进行了只读检查，没有调用实验 API、执行策略或修改文件。

已独立核实：

- **数值与分母正确。** 重新读取两份原始 gzip，共 10,472,965 行，得到八项答案 `[7510527, 0, 7324894, 7324894, 6337276, 6337276, 2931100, 7324894]`；六分支合计确为 **48 执行、35 正确、2 错误提交、11 接口失败、0 暂缓**。96 原计划位置中的另48项是整条 GH 历史资源排除。证据：`analysis.json`第2–14行；`artifacts/research_decisions/20261113-confirmation-selection-v1/public-cases/wiki.case.json`第8–87行。
- **金标与行动分离。** 金标通过独立 SQL 解析器计算；运行器仅在全部行动停止后评分，没有把 reference 交给 reader。真实性检查比较原始来源对应的完整结构化内容，并保留未知自由文本。证据：`snapshot/trustmem_runtime/grading.py:8–72`；`snapshot/resume_models.py:100–115`；`snapshot/trustmem_diagnostics/authentication.py:7–45`。
- **费用没有漏掉失败请求。** 逐条重新计算三阶段原始调用账：v2为1次拒绝、usage未知，预留 USD0.0184866；v3为14次、USD0.071423088；v4为79次、USD0.334947876。合计 **94请求、93响应、已知估价 USD0.406370964，含预留 USD0.424857564**；角色计数 bootstrap4、reader89、writer1。冻结费率下算术一致，账单仍未观察。证据：三阶段`models/api/model_calls.jsonl`；`experiments/memory_lifecycle/confirmation_pilot_v1/analyze_all.py:26–43`；`snapshot/metered_deepseek.py:75–125`。
- **没有重试旧任务或替换首次失败。** v3前七项 event 与 v4前七项逐对象相同；原始73个文件除扩展后的聚合 events/score 外全部字节一致。89个实际 reader API 输入/输出与89个保存的调用完全匹配。续接从`len(events)`开始。证据：`snapshot/resume_models.py:48–49、84–96`；`models/results.json:2516–2528`。
- **分支隔离与来源公平条件成立。** 所有普通内存分支均与自己的初始库字节相同；Mem0初始、free、tool-first的四个存储文件分别完全一致。没有 save。检查全部输入档案目录，没有提前暴露未来未取得来源。资源门槛重新计算仍为 GH 5,800,569 B、Wiki 264,310 B，发生在首个模型请求前。证据：`snapshot/run.py:247–257`；`experiments/memory_lifecycle/confirmation_pilot_v1/resource_gate.py:7–38`。
- **代码版本可追溯。** v1/v2/v3/v4冻结分别69/70/102/209项哈希全部匹配；v2→v3的 AST 差异仅为 bootstrap 格式用语。三条历史路径解析记录均与所列 Git commit 的真实 blob 哈希一致。实际运行冻结`native-reader-2`，当前工作代码是 reader-3，两者没有混记。证据：本目录`freeze.json`；`artifacts/research_decisions/20261113-versioned-input-resolution/resolution.json:4`。

以下是**限制后续比较的 WARN，不是当前报告错误**：

- 冻结提示没有明确给出必需的`action`键与完整 schema；11项失败全部确为`type=query`、缺少`action`，对应实际 query 次数为0。不能归因于 Mem0 记忆能力。证据：`snapshot/trustmem_runtime/reader.py:18–38、128–132`。
- 原生 SDK writer 实际返回`{"facts":[]}`，两分支初始检索为空；这里只测到该输入条件下的空状态回退。证据：`models/api/model_calls.jsonl:22`；`models/g01-mem0/free/s00-read.json:3`。
- 所有分支选择 start、save=0，覆盖摘要与完整记录没有激活整理差异；不能把6/8与7/8解释为算法差异，也未检验修订或附带损失。
- 两次旧答案提交均发生于 **零起始索引4，即第五个请求**；实际提交7,324,894，当前真值6,337,276。当时恢复的是旧源观察，工具返回 null，不能仅凭数值吻合推断模型内部因果依赖。证据：`models/g00-coverage/free/s04/event.json:4`、`models/g02-verbatim/free/s04/event.json:4`。
- 额外旧源扫描的45,359,446 B差异真实，普通档案恢复足以解释；不是作者方法收益或全周期加速。仅一个合格历史、适应性资源筛选与两次恢复协议调整，不能作为独立样本显著性或总体排名依据。

当前主报告已经明确写出这些限制与结论边界，未发现必须阻止保留其局部描述性证据的问题。

路径以D:/study homework/trusted computing/为根；snapshot/models/analysis等简写以本结果目录为根。此存档统一了链接显示，未改变审阅判断；完整输入提示与路由保存在.aris/traces/experiment-audit/20261113_public_pilot。
