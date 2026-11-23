# P4 · 多家族原生 Tool-Calling 大模型反事实溢出审计预注册协议（ModelScope 零 API 经费执行版）

## 1. 研究目的与竞争解释（开跑前冻结）

当前主稿（C93、C96、P3）的核心发现——共享执行预算下，缺失单份仍有效的跨会话回执会通过**实付同值复查扣费**或**付费前派工重排**改变范围外目标交付，且单笔减费可能触发**非单调方向反转**——目前主要建立在确定性程序策略（`ordered` / `low_cost`）上；唯一的实测大模型试点（P0）只覆盖单一模型、受限编号菜单和连续护栏。

本协议（P4）利用 **ModelScope 免费 GPU（24GB CUDA × 36h + 192GB AMD HBM × 100h）** 本地部署 **3 个不同模型家族的开源原生 Tool-Calling 大模型**（API 费用 `USD 0.00`），在**不提供任何手写 `low_cost` 排序脚本**的前提下，直接检验真实大模型在共享预算下的同起点反事实溢出行为，并补齐同精确权重的 `menu vs native` 接口敏感性对照。

### 两个核心竞争解释与可证伪预测

| 竞争解释 | 具体预测 | 结果会如何改变论文判断 |
|---|---|---|
| **H-Script（审稿人反方假设：脚本产物论）** | 确定性主发现只是手写 `ordered` / `low_cost` 规则的副产品。换成真实多家族原生 Tool-Calling LLM 后，要么（a）模型始终按提示顺序执行，出现 `0` 例超过 `keep`/`sham` 噪声的自发付费前重排；（b）`remove` 相对 `keep_r0` 的范围外终态变化率与 `keep` 重复运行或 `sham` 扰动的噪声率无区别；（c）模型主要死于工具参数/格式/早停失败，无法形成干净的反事实归因信号。 | **诚实报告为适用边界**，绝不靠挑种子、改提示或加外挂启发式追阳性；明确界定实证结论适用于受控/规则化调度器，并把真实 LLM 的工具接口/规划失灵单独记账。 |
| **H-LLM-Spillover（机制泛化假设）** | 至少 **2 个不同模型家族** 通过资格验收后，在相同开局快照下：（a）`remove` 相对稳定重复的 `keep` 与 `sham` 对照，产生可复现的**范围外目标交付变化**；（b）真实 LLM 在**无手写排序规则**时，仍会在缺失回执后出现**自发付费前派工改序**（在触发指定复查前或未触发复查时改变首个/早期目标顺序）；（c）在触发同值复查的单元上，前缀锁定的 `fee_only` 单笔免除扣费验证纯费用溢出，并检验真实 LLM 下是否同样出现**非单调/方向反转**或**与总效应分歧**。 | 直接打掉“结论只适用于手写启发式脚本”的最致命审稿质疑，将论文证据链升级为**确定性全量基线 + 跨家族真实原生 Tool-Calling LLM 反事实审计**，并在高延迟真实大模型上实测前缀复用分叉的真实推理算力节省。 |

---

## 2. 严格边界声明与样本冻结

1. **样本性质声明（遵守 `MODEL_FAMILY_EXTENSION.md` 第 3 条）**：
   - 本批 3 个工作流共 **20 个变化后批次**（全部复用已封存的确定性热启动开局快照，零修改原产物）：
     - **`forms`（`oracle_clinical_one_data_collection`，上游 `released`，3 个原生工具，预算 17）**：`T11–T16`（6 批）。主机制复核 + 同精确权重 `menu vs native` 接口敏感性对照。
     - **`medical_appointment`（上游 `released`，4 个原生工具，预算 72）**：`T11–T16`（6 批）。跨领域正式发布工作流机制泛化。
     - **`api_reliability`（上游 `candidate_model_validation`，5 个原生工具，预算 57）**：`T09–T16`（8 批）。高单笔复查费（17/57）溢出泛化；**所有汇总表必须分别报告“2 个 `released` 工作流小计（12 批）”与“含 `api_reliability` 总计（20 批）”**，绝不混标发布状态。
   - **定位说明**：这 20 个窗口此前已在确定性实验中审查过，因此 P4 定位为**多家族真实原生 Tool-Calling 机制泛化与接口敏感性验证**（mechanism recheck & cross-family native generalization），不冒充未见历史的前瞻盲测。每张主表同时报告工作流数（历史数）与配对单元数，并完整报告零效应和失败案例。

2. **工具面与无偏提示约束**：
   - 原生模式直接使用 ReScopeBench `world.public_tool_schemas()` / `driver.tools` 加上零费 `finish_session`（`archive` 臂额外提供零费内容寻址 `lookup_archive`），经由 `eval_ext.contracts.NativeToolSurface` 严格解码（每轮最多 1 次工具调用；截断、缺调用、多调用、非法 JSON、未提供工具均显式记错停止，**绝不自动兜底或重抽更好答案**）。
   - 系统提示与开局 JSON 只展示官方任务目标、公开工具单价、剩余预算与当前活动记忆，**严禁注入任何手写 `low_cost` 排序建议或预算地板提示**。

---

## 3. 同起点反事实臂与方差校准设计

对每个合格 `(model, workflow, day)`，均从完全相同的封存开局快照 `(W_0, M_full)` 分叉执行：

| 臂名 | 开局记忆与工具条件 | 检验目的 |
|---|---|---|
| `keep_r0`, `keep_r1`（`forms` 额外跑 `keep_r2`） | 完整活动记忆 `M_full`，`temperature=0`，不同显式 `seed`（`101`, `102`, `103`） | 量化同输入下本地推理/采样方差基线（目标集合一致性、首个派工目标一致性、完整派工顺序一致性） |
| `sham` | 删除封存的**无关非当前目标回执** `sham_key` | 排除“仅仅因为活动记忆少一条、提示变短”引起的无关扰动 |
| `remove` | 删除封存的**指定焦点回执** `focal_key`，不提供原档 | 测量单份跨会话回执缺失的总效应、自发付费前派工改序，以及是否发生同值复查 |
| `fee_only`（前缀锁定单笔免收费分叉） | 仅当 `remove` 实际发生**同值、正收费**焦点复查（步号 `k`）时准入；从 `(W_0, M_full \ {focal})` 恢复，确定性重放 `1..k-1`（断言每步非账目输出逐字一致），第 `k` 步原生免除实收（`charged=0`，断言非账目输出与 `remove` 完全一致），从 `k+1` 步起交给同一模型继续原生执行 | 严格隔离“单笔实付复查费”纯因果效应；消除前序随机飘移；直接检验真实 LLM 上的**非单调/方向反转**；同时量化前缀复用节省的模型推理调用与墙钟时间 |
| `archive`（`forms` + `medical_appointment`） | 活动记忆删除 `focal_key`，开放零费内容寻址 `lookup_archive` 工具 | 检验真实原生 LLM 是否会主动利用普通零费原档恢复，而不是直接重查或改序 |

### 同精确权重接口敏感性对照（Study 2，Slot A 专用）
- 在 **Slot A 的同一本地模型权重** 上，对 `forms` `T11–T16` 额外运行冻结的 `indexed_menu` 接口（`keep_r0`, `remove`, `archive`），与同一模型的 `native_tool_calling` 结果逐批配对比较，满足 `MODEL_FAMILY_EXTENSION.md` 第 2 条“同精确版本隔离接口敏感性”的要求。

---

## 4. 本地开源模型矩阵与 ModelScope 算力预算（API 费用 USD 0.00）

所有权重优先从 **ModelScope Hub（魔搭社区）** 内网高速下载，192GB AMD HBM 实例直接跑原生 BF16 权重（不做有损量化，消除量化混杂）。

| 槽位 | 角色 | 首选 ModelScope 权重（原生 BF16 显存） | vLLM Tool Parser | 备选同家族权重 |
|---|---|---|---|---|
| **Gate 1（24G CUDA）** | 工程与协议联调资格验收（仅跑 `forms` T11） | `Qwen/Qwen2.5-7B-Instruct`（~15GB） | `hermes` | `Qwen/Qwen3-8B`（`hermes`） |
| **Slot A（192G AMD）** | 家族 1（Qwen）+ `menu vs native` + 思考/非思考对照（`forms`） | `Qwen/Qwen3-32B`（~65GB，`enable_thinking=False` 主跑；另跑 `enable_thinking=True` `forms` T11–T16 切片，`max_output_tokens=1024`） | `hermes` | `Qwen/Qwen2.5-72B-Instruct`（~144GB，`hermes`） |
| **Slot B（192G AMD）** | 家族 2（Meta Llama） | `LLM-Research/Llama-3.3-70B-Instruct`（~140GB） | `llama3_json` | `LLM-Research/Meta-Llama-3.1-70B-Instruct` |
| **Slot C（192G AMD）** | 家族 3（Mistral / GLM 独立第三家族） | `mistralai/Mistral-Small-24B-Instruct-2501`（~48GB） | `mistral` | `ZhipuAI/GLM-4-32B-0414`（~65GB，`glm4`） |

### 算力与调用上限预算（硬封顶）
- **单模型主矩阵规模（20 批）**：
  - `keep` 重复：`6×3 + 14×2 = 46` 轮次
  - `sham`：`20` 轮次
  - `remove`：`20` 轮次
  - `fee_only`：`≤20` 轮次（且前缀复用节省约 35%–55% LLM 调用）
  - `archive`（`forms` 6 批 + `medical_appointment` 6 批）：`12` 轮次
  - 合计约 **118 个分叉回合 / 模型 ≈ 1,000–1,200 次本地模型调用 / 模型**；硬调用上限设为 `2,000 calls / slot`。
- **预计 GPU 耗时**：
  - Gate 1（24G CUDA）：**≤ 1.5 小时**（总配额 36h）
  - Slot A（32B 非思考主矩阵 + `menu` 18 回合 + 思考 `forms` 切片）：**~3–4 小时**
  - Slot B（70B 主矩阵）：**~3–5 小时**
  - Slot C（24B–32B 主矩阵）：**~2–3 小时**
  - **总计约 10–14 小时 AMD GPU（仅占 100h 免费配额的 10%–14%）+ ≤1.5 小时 CUDA GPU，API 费用 `USD 0.00`**。

---

## 5. 硬停止关口（防止无效烧卡）

1. **Gate 0（本机离线验收，0 GPU）**：
   - `python -m unittest tests/test_eval_ext.py tests/test_native_llm_audit.py -v` 全部通过；
   - `python experiments/memory_correctability/run_p4_modelscope_audit.py pack --out p4_modelscope_bundle.zip` 打包并校验所有文件 SHA-256。
2. **Gate 1（24G CUDA 联调关口，≤1.5h）**：
   - 在 24G CUDA 起 `Qwen2.5-7B-Instruct` vLLM 服务，执行 `qualify --slot Q0`。
   - **通过条件**：0 次 HTTP/harness 崩溃，所有录制磁带（`model_calls.jsonl`）离线 `replay` 100% 逐字节复现原生终态与扣费。未通过则先修代码，**严禁直接启动 192G AMD**。
3. **Gate 2（192G AMD 单模型资格关口，每模型 ≤0.5h）**：
   - 每个槽位（A/B/C）正式开跑前只跑 `forms` `T11`（`keep_r0`, `keep_r1`, `remove`, `sham`, `fee_only`）。
   - **淘汰（Disqualify）停止条件**：若该模型在 `T11` 上原生工具调用格式/解析失败率 `> 25%`，或 `keep_r0` / `keep_r1` 的合法完成数均为 `0`，立即停止该模型扩量，保留完整失败记录并标注 `disqualified_interface`（若需替换备选模型须先记日志，不删失败记录）。
4. **Gate 3（每工作流中断安全与完整保留）**：
   - 运行器支持按 `(case_id, arm)` 断点续跑（已完成分支不重跑），每轮调用实时落盘 `model_calls.jsonl` 与 `attempt_ledger.jsonl`；跑完立刻执行零 GPU `replay` 校验，再把结果目录打包拷回本地做最终汇总。

---

## 6. ModelScope 实操命令清单（可直接复制）

### 步骤 0：在本地 Windows 打包便携实验包（0 GPU）
```powershell
python "experiments\memory_correctability\run_p4_modelscope_audit.py" pack --out "artifacts\p4_modelscope_bundle.zip"
```
将生成的 `p4_modelscope_bundle.zip` 上传到魔搭 Notebook 工作目录（如 `/mnt/workspace/`）并解压：
```bash
mkdir -p /mnt/workspace/p4_audit && unzip -o /mnt/workspace/p4_modelscope_bundle.zip -d /mnt/workspace/p4_audit
cd /mnt/workspace/p4_audit
python3 run_p4_modelscope_audit.py verify-bundle
```

### 步骤 1：在 24G CUDA 实例跑 Gate 1 联调（终端 1 起服务，终端 2 跑验收）
```bash
# 终端 1：从魔搭下载并启动 OpenAI 兼容原生工具调用服务
pip install -q modelscope vllm
modelscope download --model Qwen/Qwen2.5-7B-Instruct --local_dir /mnt/workspace/models/Qwen2.5-7B-Instruct
vllm serve /mnt/workspace/models/Qwen2.5-7B-Instruct \
  --served-model-name Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 --port 8000 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --max-model-len 16384 --gpu-memory-utilization 0.90
```
```bash
# 终端 2：执行 Gate 1 资格验收 + 零 GPU 磁带复放验收
cd /mnt/workspace/p4_audit
python3 run_p4_modelscope_audit.py qualify \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-7B-Instruct \
  --slot Q0 --with-menu \
  --out /mnt/workspace/p4_runs/Q0_cuda_qualify

python3 run_p4_modelscope_audit.py replay \
  --run-dir /mnt/workspace/p4_runs/Q0_cuda_qualify \
  --out /mnt/workspace/p4_runs/Q0_cuda_qualify_replay_check
```

### 步骤 2：在 192G AMD ROCm 实例依次跑 Slot A / B / C 主矩阵
> 注：魔搭 AMD 实例已预装 ROCm 7.2.3 + PyTorch 2.12；先用 `python3 -c "import vllm; print(vllm.__version__)"` 检查镜像是否已预装 vLLM（若未预装则按魔搭 ROCm 文档装 ROCm 版 vLLM 或 SGLang；所有服务只要暴露 `http://127.0.0.1:8000/v1/chat/completions` 均可无缝对接）。

```bash
# Slot A 示例：Qwen3-32B（非思考主矩阵 + 同权重 menu vs native 对照）
modelscope download --model Qwen/Qwen3-32B --local_dir /mnt/workspace/models/Qwen3-32B
vllm serve /mnt/workspace/models/Qwen3-32B \
  --served-model-name Qwen/Qwen3-32B \
  --host 127.0.0.1 --port 8000 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --max-model-len 16384 --dtype bfloat16

# 终端 2：先过 Gate 2，再跑完整三工作流主矩阵
python3 run_p4_modelscope_audit.py qualify \
  --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-32B --slot A \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --with-menu --out /mnt/workspace/p4_runs/slotA_qwen3_32b_qualify

python3 run_p4_modelscope_audit.py run \
  --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-32B --slot A \
  --suite all --with-menu \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --out /mnt/workspace/p4_runs/slotA_qwen3_32b_nothink

# 可选思考模式对照（仅 forms T11-T16，max_output_tokens=1024）
python3 run_p4_modelscope_audit.py run \
  --base-url http://127.0.0.1:8000/v1 --model Qwen/Qwen3-32B --slot A_think \
  --suite forms --max-output-tokens 1024 \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}' \
  --out /mnt/workspace/p4_runs/slotA_qwen3_32b_think

# Slot B（Llama-3.3-70B-Instruct）：把 --tool-call-parser 换为 llama3_json，去掉 extra-body
# Slot C（Mistral-Small-24B-Instruct-2501）：把 --tool-call-parser 换为 mistral，去掉 extra-body
```

### 步骤 3：全量零 GPU 离线复放验收并打包带回本地
```bash
python3 run_p4_modelscope_audit.py replay \
  --run-dir /mnt/workspace/p4_runs/slotA_qwen3_32b_nothink \
  --out /mnt/workspace/p4_runs/slotA_qwen3_32b_nothink_replay_check

tar -czf /mnt/workspace/p4_results_slotA.tar.gz -C /mnt/workspace/p4_runs slotA_qwen3_32b_nothink
```
