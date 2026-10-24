# Tool 契约（实测）

> 本文档记录本仓库以真实 Token 逐个调用得到的结果，字段名、单位、返回形态均来自实际响应，不是官方文档转述。实测时间：2026-10-24 15:16–15:26（CST）。

## 0. 通用响应信封

每个工具的 `structuredContent` 都携带上游 API 的统一信封：

```json
{"success": true, "code": 200, "message": "请求成功",
 "datetime": "2026-10-24 15:16:06", "traceId": "...", "data": ...}
```

- `data` 可能是 `dict`、`list`，也可能是**字符串**（压缩表，见 `list-nutrition-foods`）。
- 失败时 `code != 200`，`message` 给原因。

## 1. `now-time-info`（实测 ✅）

`data` 返回：

```json
{"timestamp": 1792826166591, "datetime": "2026-10-24T15:16:06.591",
 "formatted": "2026-10-24 15:16:06", "date": "2026-10-24", "year": 2026,
 "month": 10, "day": 24, "dayOfWeek": "SATURDAY",
 "timezone": "GMT+08:00", "offset": "+08:00", "utc": "2026-10-24T07:16:06.591Z"}
```

取 `formatted` 做展示，`dayOfWeek` 做营业/早餐时段判断。

## 2. `list-nutrition-foods`（实测 ✅，核心）

`data` 是**单行字符串**，不是 JSON 数组：

```
[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  猪柳麦满分,null,1288,308,16,16,24,781,213
  巨无霸,null,2147,513,27,26,42,961,171
  ...
```

- 首行 `[160]{字段列表}:`，随后每行缩进两格的 CSV，共 **160 行**。
- 字段：`productName, nutritionDescription, energyKj, energyKcal, protein, fat, carbohydrate, sodium, calcium`。
- **`nutritionDescription` 全部为 `null`** → 接口不返回份量说明。每行语义上是一个"每份"餐品，本项目据此把 `basis` 定为 `per_serving`，并在 `analogy-basis.md` 声明这一假设及证据。
- 无餐品编码 → 与菜单之间没有 join key，只能按名称对齐（见 `data-alignment.md`）。

解析函数：`normalize.parse_compact_table()`。

## 3. `query-nearby-stores`（实测 ✅）

入参：`beType=1`（到店自取）+ `searchType=2`（按位置）+ `city` + `keyword` 同时必填。

返回 `data` 是门店数组，关键字段：

```json
{"storeCode": "1450713", "storeName": "麦当劳上海黄浦华旭国际大厦餐厅",
 "address": "南京东路街道西藏中路336号", "distance": 144,
 "businessStatus": true, "businessStartTime": "00:00", "businessEndTime": "23:59",
 "reservation": true, "reservationTimeOptions": [...]}
```

- `beType=1` 的门店**无 `beCode`**，后续调用不传。
- `businessStatus=false` 的门店不能下单，`query-meals` 会报错，要过滤。

## 4. `query-meals`（实测 ✅，与官方文档不同）

入参：`storeCode` + `orderType=1` + `beType=1`。

返回 `data` 结构：

```json
{"categories": [{"name": "人气热卖", "meals": [{"code": "9900014838", "tags": ["全球爆款"]}]}],
 "meals": {"9900014838": {"name": "...", "image": "...", "currentPrice": "27.9", "originalPrice": "46", "canWithOrder": false}},
 "frequent": ...}
```

**关键发现**：`data.meals` 是一个 `code → {name, image, currentPrice, originalPrice, canWithOrder}` 的字典，**一次调用同时拿到名称和价格**。官方 README 暗示要先 `query-meals` 再逐个 `query-meal-detail` 才能取名，与实测不符。实测单店 **129 个餐品、15 个分类**，一次调用齐全。

## 5. `calculate-price`（实测 ✅）

入参：`storeCode` + `orderType` + `beType` + `items: [{productCode, quantity, ...}]`。

返回 `data`：

```json
{"productOriginalPrice": 2790, "productPrice": 2790, "originalPrice": 2790,
 "discount": 0, "price": 2790,
 "productList": [{"productCode": "...", "productName": "...", "quantity": 1, "subtotal": 2790}],
 "takeWayList": [{"code": "eat-in", "title": "堂食"}, {"code": "locker-out", "title": "外带"}]}
```

- **价格单位是分**（2790 = ¥27.9），展示前要 ÷100。
- `takeWayList` 给取餐方式 code（`eat-in` / `locker-out` 等），下单时要回传。

## 6. `campaign-calendar`（实测 ✅）

`data.dailyList` 是按日期分组的活动列表，每条含 `date`、`events[]`（`activityCode`、`activityStage`、`articleDto` 等）。`activityStage` 区分进行中/往期/未来，展示时过滤过期活动。

## 7. `tools/list`（实测 ✅）

返回 **35 个工具**，不是官方 README 写的 33 个。差异：

| 官方 README | 实测 `tools/list` |
| --- | --- |
| `query-partystore-session` | `query-party-store-session` |
| `query-partystore-date` | `query-party-store-date` |
| （无） | `query-promotions`（新增） |
| （无） | `query-survey-coupon`（新增） |

**结论**：tool 名一律以运行时 `tools/list` 为准，文档里的名字只能当参考。

## 8. 错误码

| code | 含义 | 处理 |
| --- | --- | --- |
| 401 | Token 无效/过期/缺失 | 不重试，提示检查 `MCD_MCP_TOKEN` |
| 429 | 超过 600 次/分钟 | 指数退避重试一次 |
| 上游业务 code ≠ 200 | 见 `message` | 门店打烊/无收藏等，据 `message` 提示用户 |
