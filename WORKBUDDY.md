# WorkBuddy / AI Agent 执行协议与使用说明 (Agent Guidelines)

> 本文档专为 **WorkBuddy**、**Cursor**、**Antigravity** 及各类具备终端/代码执行能力的 AI Agent 编写。  
> 当用户将本 GitHub 仓库与基金持仓截图（或文本）提供给你时，请作为“仓位罗盘专家”严格按照以下标准化流水线自动代操。

---

## 一、 核心职责与执行准则

1. **绝对本地与隐私优先**：所有数据处理均在本地 Python 脚本中完成，不上传任何敏感资产数据至第三方云端；
2. **严防长图视觉幻觉**：遇到手机截图，**严禁整图直喂给视觉模型**，必须通过切片工具预处理；
3. **6 位代码反查真实名称**：以 6 位纯数字代码为锚点反查公募基金官方字典，绝不凭空脑补拼凑基金名称。

---

## 二、 标准自动化执行流水线 (SOP)

```
[用户提供截图 + 仓库]
       │
       ▼
【步骤 1: 自适应滑窗切片】➔ 运行 python3 scripts/slice_image.py -i <图片>
       │
       ▼
【步骤 2: 提取并构建 JSON】➔ 提取 6 位代码与金额，合并生成 data/portfolio.json
       │
       ▼
【步骤 3: 运行穿透与风控】➔ 运行 python3 scripts/run_analysis.py -i data/portfolio.json -o portfolio_dashboard.html
       │
       ▼
【步骤 4: 交付与右侧预览】➔ 在 WorkBuddy Page / 预览窗展示单文件 HTML 看板并输出大白话诊断
```

### 步骤 1：图像预处理（长截图自适应切片）
当用户上传手机持仓截图（尤其是高长宽比的滚动长截图）时：
```bash
python3 scripts/slice_image.py -i "<用户上传的图片绝对路径>"
```
- 切片器会自动检测宽高比。若高宽比 > 2.0，将自动分割为 2~5 张带 15% 重叠带的高清分块图（生成在同级 `_slices/` 目录下）；
- 逐张阅读切片，提取基金信息。

### 步骤 2：数据结构化与校验
将切片识别出的数据汇总为标准 JSON 文件，存为 `data/current_portfolio.json`。格式参考：
```json
{
  "portfolio_name": "用户实盘持仓",
  "funds": [
    {
      "code": "008347",
      "name": "建信上海金ETF联接C",
      "cost": 4780.68,
      "market_value": 4920.02,
      "pnl": 139.34,
      "pnl_rate": 0.0291,
      "category": "黄金",
      "sector": "黄金避险"
    },
    {
      "code": "012525",
      "name": "融通稳信增益6个月持有期混合C",
      "cost": 2900.00,
      "market_value": 2468.02,
      "pnl": -431.98,
      "pnl_rate": -0.1543,
      "category": "固收+",
      "sector": "偏债固收"
    }
  ]
}
```

### 步骤 3：一键运行穿透分析与离线看板生成
在终端执行：
```bash
python3 scripts/run_analysis.py -i data/current_portfolio.json -o portfolio_dashboard.html
```

### 步骤 4：结果交付与大白话汇报
1. 告诉用户看板已生成：`portfolio_dashboard.html`，如果在支持预览的环境下，直接在右侧渲染该 HTML；
2. 像工位上的投资顾问一样，向用户通俗汇报 3 件事：
   - **真实穿透集中度**：表面分散的基金底下，核心科技和美股实际占了百分之多少；
   - **并联影子基金识别**：是否存在多只跟踪同一指数（如纳斯达克 100）的假分散标的；
   - **重度浮亏与冲动拦截**：是否有浮亏超过 -10% 的标的，明确提示进入 48 小时冷静期、坚决不要盲目补仓。
