# 独立只读完整性复核

请求路由：gpt-6.1-sol / ultra，新上下文 `/root/loss_attribution_audit`。实际模型身份未独立核实；同家族、provisional。局部证据完整性PASS，整体保留非阻断WARN；不等于外部同行评议。

以下为审阅回复：

**PASS（限定于当前开发回溯）；无阻断错误。审计身份为同系列 provisional，实际模型身份未核实。**

- 只读复算确认：2,290项冻结哈希前后均一致，12项控制结果完全一致，240行结果逐字段完全一致。证据：`artifacts/research_decisions/20261113-loss-attribution-v1/snapshot/run.py:68、112、262`。
- 重新核验192个脚本提交与独立SQL真值一致；444个脚本输入、75个模型输入均绑定正确任务/来源。模型输入中70次结构化receipt与原始源精确一致；39条缓存种子均来自较早会话。证据：同目录`trustmem_runtime/grading.py:55`，`snapshot/run.py:178、190、219、236`。
- 数字与报告一致：模型35项充分（27对、5错、3未完成），13项未知（6对、7错）；11项启发式漏计、3项未决；59/13项持久内容可支持但初始未直接送达；16项缓存可支持但初始未认证；16次已有依据的query。证据：`docs/mainline/LOSS_ATTRIBUTION_REPLAY_20261113.md:43、47、63、65、69`。
- 工具生成与实际送达分开；3个最后工具结果未送达，未冒充错误提交或成功完成。来源无关的`quality_check`不作证书。证据：`snapshot/run.py:101、146`，`snapshot/trustmem_diagnostics/support.py:44`。
- 因果和推广范围表述合格：没有把unknown当作不足，没有把阶段共现写成唯一因果，没有独立确认集、后端排名或算法收益主张。证据：报告`:53、69、71、75`。

**WARN（非阻断边界）**：当前“conflicting”检测不覆盖任意receipt之间的矛盾。`support.py:15`把全部匹配receipt交给一次`calculate`；`trustmem_runtime/evidence.py:13`会覆盖先前数值。确定性边界探针中，两份同源full receipt分别支持0/1，合并后随顺序返回`sufficient`，未返回`conflicting`。当前已核验数据未发现此情形；后续扩展需补充冲突检查，或明确限定该状态仅检测已收集支持值之间的冲突。

以上相对路径均位于`D:/study homework/trusted computing/`。未修改项目文件，未调用API，未新增模型语义金标。

## 审阅后记录

主报告随后补入上述冲突检测范围与本审阅链接；原冻结2,290输入、校准和240行结果没有改动。原代码未以修复名义覆盖，后续如扩到不受信写入需先补校准。
