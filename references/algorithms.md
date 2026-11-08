# `ethan-hold` 穿透合并与量化分析数学模型规范 (Mathematical Algorithms Spec)

本文档系统定义 `ethan-hold`（仓位罗盘）算法引擎的数学基础、矩阵穿透推导、板块归集逻辑及同质化冗余度量化公式。所有公式均在本地 Python 引擎中实现，实现 100% 确定性离线计算。

---

## 一、 组合总资产与资金权重模型

### 1. 基础符号定义
投资组合包含 $N$ 只公募基金或投资标的：
$$\mathcal{F} = \{F_1, F_2, \dots, F_N\}$$

对于每只基金 $F_i$：
- $C_i$：累计投入持仓成本（元）
- $V_i$：当前持仓市值（元）
- $P_i = V_i - C_i$：浮动盈亏绝对值（元）
- $R_i = \frac{V_i - C_i}{C_i}$：持仓收益率（浮亏率）

### 2. 组合总量聚合
- **组合总成本**：
  $$C_{\text{total}} = \sum_{i=1}^N C_i$$
- **组合总市值**：
  $$V_{\text{total}} = \sum_{i=1}^N V_i$$
- **组合总浮动盈亏**：
  $$P_{\text{total}} = V_{\text{total}} - C_{\text{total}} = \sum_{i=1}^N P_i$$
- **组合总收益率**：
  $$R_{\text{total}} = \frac{P_{\text{total}}}{C_{\text{total}}} = \frac{V_{\text{total}} - C_{\text{total}}}{C_{\text{total}}}$$

### 3. 基金资金权重 (Portfolio Weight)
第 $i$ 只基金在总组合中的市值权重定义为：
$$w_i = \frac{V_i}{V_{\text{total}}}, \quad \text{满足} \sum_{i=1}^N w_i = 1$$

---

## 二、 底层资产两级穿透合并模型 (Penetration & Consolidation)

### 1. 底层个股穿透矩阵
设全组合覆盖的所有底层资产（如个股、债券标的）的唯一集合为：
$$\mathcal{A} = \{A_1, A_2, \dots, A_M\}$$

第 $i$ 只基金在最新季度披露中，持有底层资产 $A_k$ 的持仓比例为 $f_{i, k} \in [0.0, 1.0]$。若基金未持有该标的，则 $f_{i, k} = 0$。

对于单一只基金内部：
$$\sum_{k=1}^M f_{i, k} \le 1.0$$
（未披露的剩余部分代表前十大重仓之外的长尾股票及现金流动性储备，不进行盲目膨胀折算，严格按已知实数计算真实敞口）。

### 2. 底层标的真实穿透金额 (Effective Market Value)
单一底层资产 $A_k$ 在全组合中的穿透合并金额 $E(A_k)$ 为各基金持仓金额的加权累加：
$$E(A_k) = \sum_{i=1}^N \left( V_i \times f_{i, k} \right)$$

### 3. 底层标的组合有效权重 (Effective Portfolio Weight)
单一底层资产 $A_k$ 占投资者总资产的真实有效暴露比例 $W(A_k)$ 为：
$$W(A_k) = \frac{E(A_k)}{V_{\text{total}}} = \sum_{i=1}^N \left( \frac{V_i}{V_{\text{total}}} \times f_{i, k} \right) = \sum_{i=1}^N \left( w_i \times f_{i, k} \right)$$

### 4. 基金来源贡献度归因 (Source Fund Attribution)
对于持有底层资产 $A_k$ 的任意一只基金 $F_i$，其对 $A_k$ 暴露的绝对金额贡献为：
$$\Delta V_{i, k} = V_i \times f_{i, k}$$
其在 $A_k$ 总敞口中的相对贡献度占比为：
$$\text{Attribution}(F_i \to A_k) = \frac{V_i \times f_{i, k}}{E(A_k)} \times 100\%$$

---

## 三、 行业与宏观大类板块归集模型 (Sector Roll-up)

### 1. 二级映射架构
`ethan-hold` 采用“细分赛道 $\to$ 宏观大类”的两级分类树：
1. **细分行业 $S_{\text{sub}}$**：如“美股科技”、“A股半导体与电子”、“软件与AI应用”、“医药生物”、“白酒食品”等；
2. **宏观大类 $S_{\text{macro}}$**：将高度相关的高贝塔赛道聚合（例如将美股科技、QDII纳指、A股芯片、消费电子统一聚合为“**泛科技大类**”）。

### 2. 行业敞口公式
设每只基金 $F_i$ 归属于宏观大类 $S_j$ 的资金映射为 $\text{Mapping}(F_i, S_j)$：
- **宏观板块有效敞口金额**：
  $$E(S_j) = \sum_{i \in \text{Domain}(S_j)} V_i$$
- **宏观板块有效百分比权重**：
  $$W(S_j) = \frac{E(S_j)}{V_{\text{total}}} \times 100\% = \sum_{i \in \text{Domain}(S_j)} w_i \times 100\%$$

---

## 四、 QDII 并联同质化与冗余指数 (Redundancy Index)

### 1. 并联基金成因与定义
国内投资者因外汇额度吃紧，单只纳指 100 联接基金遭遇每日限购（如 100~1000 元/天）。投资者为了放大每日买入额度，并联买入多只不同公募发行的跟踪同一标的的基金。

设跟踪同一标的基准（如 `NDX.GI` 纳斯达克 100）的基金集合为：
$$\mathcal{G}_{\text{clone}} = \{F_c \mid \text{Benchmark}(F_c) = \text{TargetIndex}\}$$
并联数量为 $M_{\text{clone}} = |\mathcal{G}_{\text{clone}}|$。

### 2. 同质化冗余指数 (Redundancy Index, $RI$)
为了量化持仓中“假分散、真重合”的严重程度，定义持仓插槽冗余指数：
$$RI = 1 - \frac{|\mathcal{A}_{\text{unique}}|}{\sum_{i=1}^N |\text{Holdings}(F_i)|}$$

- **数值边界**：$RI \in [0.0, 1.0]$；
- **$RI \to 0$**：持仓完全不重叠，各基金底层资产独立；
- **$RI \ge 0.5$**：存在大量并联基金重复持有相同龙头股票，分散化为表面假象。

---

## 五、 加仓前 What-If 模拟试算数学模型 (Pre-Trade Simulation)

当投资者拟向基金 $F_{\text{target}}$ 增发买入指令，金额为 $\Delta V$ 时：

### 1. 模拟总资产与权重重构
- 模拟后总市值：$V'_{\text{total}} = V_{\text{total}} + \Delta V$
- 模拟后总成本：$C'_{\text{total}} = C_{\text{total}} + \Delta V$
- 若 $\Delta V \le 0$（减仓/卖出）：
  $$V'_{\text{total}} = \max(0, V_{\text{total}} - |\Delta V|)$$

### 2. 宏观板块新敞口
若 $F_{\text{target}}$ 归属于宏观板块 $S_{\text{target}}$：
$$E'(S_{\text{target}}) = E(S_{\text{target}}) + \Delta V$$
$$W'(S_{\text{target}}) = \frac{E'(S_{\text{target}})}{V'_{\text{total}}} = \frac{E(S_{\text{target}}) + \Delta V}{V_{\text{total}} + \Delta V}$$

### 3. 底层重仓股新敞口
对于 $F_{\text{target}}$ 包含的每一只底层成分股 $A_k$（权重为 $f_{\text{target}, k}$）：
$$E'(A_k) = E(A_k) + \Delta V \times f_{\text{target}, k}$$
$$W'(A_k) = \frac{E'(A_k)}{V'_{\text{total}}} = \frac{E(A_k) + \Delta V \times f_{\text{target}, k}}{V_{\text{total}} + \Delta V}$$

### 4. 熔断判定不等式
若满足以下任意条件，系统触发强制拦截：
$$W'(S_{\text{macro}}) \ge \text{Cap}_{\text{macro}} \quad (50.0\%)$$
$$W'(S_{\text{sub}}) \ge \text{Cap}_{\text{sub}} \quad (35.0\%)$$
$$W'(A_k) \ge \text{Cap}_{\text{stock}} \quad (15.0\%)$$

---

## 六、 经典 25 只基金基准组合实测推导验算

在标准基准数据集中：
- $C_{\text{total}} = 100,000.00$ 元
- $V_{\text{total}} = 87,000.00$ 元
- $P_{\text{total}} = -13,000.00$ 元（$R_{\text{total}} = -13.00\%$）

### 泛科技大类敞口拆解：
- 8 只并联美股纳指基金市值：$31,400.00$ 元（占比 $36.09\%$）
- 4 只 A 股半导体芯片基金市值：$19,790.00$ 元（占比 $22.75\%$）
- 2 只计算机软件与消费电子市值：$5,850.00$ 元（占比 $6.72\%$）
- **泛科技大类总敞口**：
  $$E(\text{泛科技}) = 31,400.00 + 19,790.00 + 5,850.00 = 57,040.00 \text{ 元}$$
  $$W(\text{泛科技}) = \frac{57,040.00}{87,000.00} \approx 65.56\% \quad (\text{超出 } 50\% \text{ 硬顶 } +15.56\%)$$

### 底层核心个股穿透验算 (Top 3)：
1. **NVDA (英伟达)**：
   由 8 只纳指基金共同持有，平均权重约 8.8%，穿透市值：
   $$E(\text{NVDA}) = 31,400 \times 0.088 = 2,763.20 \text{ 元} \quad (W = 3.18\%)$$
2. **AAPL (苹果)**：
   $$E(\text{AAPL}) = 31,400 \times 0.082 = 2,574.80 \text{ 元} \quad (W = 2.96\%)$$
3. **MSFT (微软)**：
   $$E(\text{MSFT}) = 31,400 \times 0.078 = 2,449.20 \text{ 元} \quad (W = 2.82\%)$$
4. **北方华创 (002371)**：
   由 4 只半导体基金重仓：
   $$E(\text{北方华创}) = 603.68 + 486.64 + 476.28 + 317.52 = 1,884.12 \text{ 元} \quad (W = 2.17\%)$$
