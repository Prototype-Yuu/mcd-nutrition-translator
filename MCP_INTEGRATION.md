# MCP 集成说明

> 记录本项目**实际使用**的麦当劳 MCP Server、Tool、调用流程与业务价值。
> 所有验证结论标注来源：`实测` = 本仓库亲自调用；`文档` = 官方 README。

## 1. Server

| 项 | 值 | 来源 |
| --- | --- | --- |
| 名称 | 麦当劳中国 MCP 服务（mcd-mcp） | 文档 |
| 接入地址 | `https://mcp.mcd.cn`（根路径） | **实测** |
| 传输协议 | Streamable HTTP | 文档 |
| 鉴权 | `Authorization: Bearer <MCP_TOKEN>` | 文档 |
| 限流 | 600 次/分钟，超限 429 | 文档 |
| Token 申请 | https://open.mcd.cn/mcp → 手机号登录 → 控制台 → 激活 | 文档 |

### 接入地址的核实过程

官方 README 写的是 `https://mcp.mcd.cn`，但网络上流传的实测文章称该地址有误、应该用 `https://open.mcd.cn/mcp`。两处冲突，所以直接探测：

```
POST https://mcp.mcd.cn        -> 403    (服务存在，缺鉴权)
POST https://mcp.mcd.cn/mcp    -> 404    (路径不存在)
POST https://open.mcd.cn/mcp   -> 405    (GET 页面，不是 API 端点)
```

**结论**：官方 README 正确，端点是根路径 `https://mcp.mcd.cn`；`open.mcd.cn/mcp` 是申请 Token 的控制台网页，不是 MCP 端点。这一步省掉了照抄二手文章导致的 401/404 排查。

## 2. 客户端实现

`scripts/mcp_client.py`，纯标准库（`json` / `urllib` / `re`），无第三方依赖。

处理的三个实现细节：

1. **会话头**：`initialize` 返回的 `Mcp-Session-Id` 要在后续请求里回传，协议版本回传在 `MCP-Protocol-Version`。
2. **响应体形态不固定**：可能是纯 JSON、可能是 SSE（`data: {...}` 行）、也可能是说明文字与 JSON 混排。`parse_body()` 三种都能解析：先整体 `json.loads`，再拆 SSE，最后用 `JSONDecoder.raw_decode` 从每个 `{` 起尝试。
3. **错误分层**：401 是 Token 问题，重试无意义，直接失败并给出可执行的提示；429 与 5xx 才退避重试（1s → 2s → 4s → 8s，上限 16s）。

## 3. 使用的 Tool

| Tool | 调用位置 | 作用 | 验证状态 |
| --- | --- | --- | --- |
| `now-time-info` | 每次会话第一步 | 确定营业状态、早餐时段、活动有效期 | ✅ 已实测 |
| `list-nutrition-foods` | L0 / L1 / L2 全部 | 六项营养数值，项目唯一数据源 | ✅ 已实测（160 条） |
| `query-nearby-stores` | 找店 | 定位可下单门店 | ✅ 已实测 |
| `query-meals` | L1 / L2 | 取餐品编码、名称、价格 | ✅ 已实测（单店 129 个，一次调用含名称+价格） |
| `query-meal-detail` | 套餐拆解 | 按编码查套餐组成，拆默认组成求和 | ✅ 已实测（51 次） |
| `calculate-price` | L1 报价 | 计算组合实付价 | ✅ 已实测（价格单位为分） |
| `campaign-calendar` | 省钱 | 活动日历 | ✅ 已实测 |
| `available-coupons` | 省钱 | 可领券 | 按需 |
| `create-order` | 下单 | 返回支付链接，不代付 | 仅估价，未实付 |

> 已验证项均来自 2026-10-24 15:16–15:26（CST）的真实调用，原始字段与返回形态记在 `references/tool-contracts.md`。**没有被真实调用过的能力，本文档不会写成已验证。**

## 3.1 实测发现（对官方文档的三处修正）

1. **`tools/list` 返回 35 个工具，不是官方 README 写的 33 个**。多出 `query-promotions`、`query-survey-coupon`；两个 party 工具实际命名是 `query-party-store-session` / `query-party-store-date`（README 写 `query-partystore-*`）。
2. **`query-meals` 一次就能拿到名称和价格**。README 暗示要先 `query-meals` 再逐个 `query-meal-detail` 取名——实测 `data.meals` 是 `code → {name, currentPrice, originalPrice}` 字典，单店 129 个餐品名称+价格一次调用齐全。
3. **`calculate-price` 的价格单位是分**（2790 = ¥27.9），展示前要 ÷100。
4. **`list-nutrition-foods` 返回的是压缩表字符串**（`[160]{字段}:` + 缩进 CSV），不是 JSON 数组，且 `nutritionDescription` 全 null（无份量说明，按"每份"理解）。

## 3.2 名称对齐与覆盖率

营养表（160 条）与菜单（129 条）之间没有共同键，且套餐无聚合值。单品靠名称对齐命中 31 条（24.0%），套餐靠 `query-meal-detail` 拆默认组成求和再补 32 个，**综合覆盖率 48.8%**，零猜值。匹配器默认关闭字符相似匹配——实测它只会把套餐错配成单品。完整数字与失败样例见 `data/alignment-coverage.md`。

## 4. 调用流程

### L0 即时报数（主流程）

```
now-time-info
  └─ list-nutrition-foods            # 一次拿全量，会话内缓存
       ├─ 单品：名称对齐（normalize.py）
       └─ 套餐：query-meal-detail 拆默认组成，逐项求和（decompose.py）
            └─ mealcard.py           # 合计 + 类比 + 外号 + 一句提醒
```

关键点：**营养表与菜单没有共同的键，且套餐没有聚合值**。单品靠名称对齐（命中层级 + 分数 + 三态，可审计）；套餐必须用 `query-meal-detail` 拆出 `isDefault=1` 的默认组成再求和——相似匹配在这两类上都会把套餐错配成单品。

### L1 配平

```
query-nearby-stores -> query-meals      # 一次拿 129 个餐品（含名称+价格）
  -> 对齐营养 -> 候选压到 15-25 个
  -> mealcard.py --solve            # 穷举 C(25,2)=300，确定性输出
  -> calculate-price                # 复核实付价（价格单位为分）
```

### 写操作

`create-order` / `delivery-create-address` / `auto-bind-coupons` / `mall-create-order` / `draw-lottery` 一律先复述后果、取得明确同意，再调用。`create-order` 只返回支付链接，不代付。

## 5. 业务价值

**解决的具体问题**：官方给了六个数字，但没给参照系。用户看到"1000 毫克钠"没有任何判断依据，于是这类信息实际是无效的。

本项目做的是补上参照系（几碗米饭 / 几个鸡蛋 / 几克盐），并且**把参照系本身也公开**（`references/analogy-basis.md` 写清哪些是官方数据、哪些是项目约定值、误差有多大）。

**对平台的价值**：

- 显著降低营养数据的理解门槛 —— 大学生群体不需要先学营养素参考值百分比
- 把"查询"变成"可执行决策" —— 从"这个多少卡"到"400 卡以内能吃什么"
- 边界明确，降低误导风险 —— 过敏原、配料、疾病建议一律拒答并转官方渠道，不给猜测

## 6. 不使用的部分

以下能力本项目**不调用**，写在文档里是为了让使用者知道边界在哪：

- 积分商城、抽奖、主题活动预约（与本项目定位无关）
- `query-meal-assistance`（仅企业团餐场景，容易被误当成通用客服问答）
- 一切写操作，除用户明确要求下单外

## 7. 配置示例

见 [`mcp-config.example.json`](mcp-config.example.json)。只使用 `${MCD_MCP_TOKEN}` 占位符，仓库内不含任何真实 Token。
