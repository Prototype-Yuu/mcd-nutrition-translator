# Tool 目录

> 来源：麦当劳中国官方仓库 `M-China/mcd-mcp-server` README（2026-10-01 更新）。
> 状态标记：`doc` = 仅据官方文档；`verified` = 本仓库以真实 Token 调用成功。逐个工具的实际验证结果记在 `tool-contracts.md`。

## 1. 门店与菜单（7）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `query-nearby-stores` | 查附近可用门店 | doc |
| `delivery-query-stores` | 查收货地址附近可配送门店 | doc |
| `delivery-query-addresses` | 查已保存的配送地址 | doc |
| `delivery-create-address` | 新增配送地址（**写操作**） | doc |
| `query-meals` | 查门店可售餐品（分类、编码、标签；**不含名称与价格**） | doc |
| `query-meal-detail` | 按编码查餐品详情与套餐组成 | doc |
| `query-meal-assistance` | 查助餐服务（**仅企业团餐场景**，不是通用问答） | doc |

## 2. 营养（1）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `list-nutrition-foods` | 餐品营养信息列表：能量、蛋白质、脂肪、碳水、钠、钙 | doc |

**这是本项目的核心数据源，也是最大的短板**：它只有六项指标，没有餐品编码，因此与菜单之间没有 join key，只能靠名称对齐。详见 `data-alignment.md`。

## 3. 算价与订单（5）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `calculate-price` | 按商品列表（可带券）计算金额、配送费、优惠、应付 | doc |
| `create-order` | 创建订单，返回订单详情与支付链接（**写操作**） | doc |
| `cancel-order` | 取消订单（**写操作**） | doc |
| `query-order` | 查订单状态与内容 | doc |
| `order-list` | 查近期到店/外送历史订单 | doc |

## 4. 券、积分与商城（13）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `campaign-calendar` | 当月营销活动日历 | doc |
| `available-coupons` | 麦麦省可领券列表 | doc |
| `auto-bind-coupons` | 一键领取全部可领券（**写操作，不可撤回**） | doc |
| `query-my-coupons` | 我账户下的券 | doc |
| `query-store-coupons` | 当前门店可用券 | doc |
| `query-my-account` | 积分账户（可用、累计、冻结、即将过期） | doc |
| `mall-points-products` | 积分商城商品列表 | doc |
| `mall-product-detail` | 商城商品详情 | doc |
| `mall-create-order` | 积分兑换下单（**写操作**） | doc |
| `mall-order-list` | 商城订单列表 | doc |
| `mall-order-detail` | 商城订单详情 | doc |
| `query-lottery-info` | 积分抽奖活动信息 | doc |
| `draw-lottery` | 执行抽奖（**写操作**） | doc |
| `query-my-prizes` | 我的奖品记录 | doc |

## 5. 主题活动（5）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `query-party-city` | 主题活动可参与城市 | doc |
| `query-party-store` | 指定城市的主题活动门店 | doc |
| `query-partystore-date` | 指定门店的可预约日期 | doc |
| `query-partystore-session` | 指定日期可预约场次 | doc |
| `party-order-create` | 主题活动下单（**写操作**） | doc |

## 6. 工具类（1）

| Tool | 用途 | 状态 |
| --- | --- | --- |
| `now-time-info` | 返回当前完整时间 | doc |

## 本项目实际用到哪些

| Tool | 用在哪 | 必要性 |
| --- | --- | --- |
| `now-time-info` | 每次会话第一步 | 必需 |
| `list-nutrition-foods` | 全部三层 | 必需 |
| `query-nearby-stores` | 找店 | 高频 |
| `query-meals` / `query-meal-detail` | L1/L2 取候选、取名 | 必需 |
| `calculate-price` | L1 报价 | 高频 |
| `campaign-calendar` / `available-coupons` | 省钱 | 中频 |
| `create-order` | 下单 | 低频，需双确认 |

其余工具本项目不调用，但保留在目录里，方便使用者知道接口边界在哪里。

## 命名注意

官方 README 里的拼写就是 `campaign-calendar`、`query-my-coupons`。**不要凭记忆写 tool 名**——运行时一律以 `tools/list` 实际返回为准，文档里出现的名字也不能当成常量。
