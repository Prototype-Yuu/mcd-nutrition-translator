# 麦门翻译官 · mcd-nutrition-translator

> **别给我毫克，给我几碗饭。**
>
> 麦当劳只给六个营养数字，我把它们翻译成你立刻能懂的东西。不劝你少吃，只帮你把这一单看明白。

你点了一单巨无霸套餐，官方给了你六个数：513 千卡、27 克蛋白、961 毫克钠……

**然后呢？** 961 毫克钠是多少？多还是少？

这个 Skill 的答案是把数字翻成人话（下面这张卡用的是**真实接口数据**，2026-10-24 门店 `1450713`）：

---

### 巨无霸 + 中薯条 + 中可乐

**换成你能感知的：** 约 4.5 碗米饭 ｜ 约 5 个鸡蛋的蛋白质 ｜ 约 3 克盐

| 指标 | 数值 |
| --- | --- |
| 热量 | 949 千卡 |
| 蛋白质 | 31 克 |
| 脂肪 | 38 克 |
| 碳水化合物 | 116 克 |
| 钠 | 1126 毫克 |
| 钙 | 199 毫克 |

**这一单是：** `碳水主力` · `顶饱型`

**一句提醒：** 这顿份量不小，下一顿轻一点刚好平衡。

<sub>以上为麦当劳官方营养标注值；生活类比为本项目约定的参照换算，不构成营养或医疗建议。</sub>

---

**想自己试？不用申请 Token，clone 下来一条命令就出上面这张卡：**

```bash
git clone https://github.com/Prototype-Yuu/mcd-nutrition-translator.git
cd mcd-nutrition-translator
python3 scripts/mealcard.py --input tests/fixtures/real-bigmac.json --format md
```

零第三方依赖，Python ≥ 3.9。

## 它解决什么问题

**官方给了数据，没给参照系。** "1000 毫克钠""513 千卡"对没有营养学基础的人来说就是没有意义。于是这类信息实际上等于无效。

三个真实的困境：

- **看不懂**：想吃麦当劳但不知道"这数字算多还是算少"
- **懒得算**：设目标、打卡、算百分比，坚持不过三天
- **被教育**：不想听"要健康饮食"，只想快速知道"我这一单是什么构成"

所以这个 Skill 的设计前提是：**默认用户没有营养学基础，也不想学。** 不填表单、不设目标、不要求连续使用。

## 真实案例

> 一个大学生，下午上完课想吃麦当劳，纠结"巨无霸套餐热量是不是太高了"。
>
> 他对 AI 说：**我想吃巨无霸 + 中薯 + 中可乐，这套怎么样？**
>
> AI 调 `list-nutrition-foods` 对齐三个单品、拆解套餐组成，回一张餐卡：
> 「约 4.5 碗米饭 · 5 个鸡蛋的蛋白 · 3 克盐，碳水主力、顶饱型。这顿份量不小，下一顿轻一点刚好平衡。」
>
> 全程他没填一个数字，看完就懂了。

## 三层能力，懒人停在第 0 层就够

| 层 | 用户说什么 | 你得到什么 | 需要设目标吗 |
| --- | --- | --- | --- |
| **L0 即时报数** | "我想吃巨无霸加中薯" | 一张餐卡：生活类比 + 六项数值 + 中性外号 + 一句提醒 | 不用 |
| **L1 一句话目标** | "想吃 600 卡以内，蛋白多点" | 2–5 个符合条件的组合 + 最划算的一单 | 一句话 |
| **L2 全天累计** | "早上吃了碗面，晚上还能吃啥" | 已摄入 + 剩余额度 + 组合建议 | 一句话 |

大部分场景停在第 0 层。第 1、2 层是给想多走一步的人准备的，不是必选项。

## 能做什么，不能做什么

这张表是这个项目最重要的部分。

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 六项营养数值（能量/蛋白/脂肪/碳水/钠/钙） | ✅ 官方数据 | `list-nutrition-foods` |
| 换算成米饭/鸡蛋/盐 | ✅ 本项目约定值，已公开基准 | [references/analogy-basis.md](references/analogy-basis.md) |
| 套餐营养（拆默认组成求和） | ✅ 官方数据 | `query-meal-detail` |
| 按热量/蛋白/钠/预算凑组合 | ✅ 确定性穷举，可复现 | `scripts/mealcard.py --solve` |
| 门店、菜单、算价、优惠券、下单 | ✅ 走官方 MCP | 见 `references/tools-catalog.md` |
| 过敏原 / 配料表 | ❌ **接口没有这个数据** | 35 个 Tool 里零字段 |
| 素食 / 清真判定 | ❌ 无配料、无认证标识 | 同上 |
| 糖分细分 / 升糖指数 | ❌ 只有总碳水 | 同上 |
| 疾病饮食建议 | ❌ 非医疗产品 | 只给数值，不给结论 |
| 政策 / 退款 / 发票 | ❌ 无知识库 | 转官方渠道 |
| 跨品牌比较 | ❌ 明确不做 | 赛事内容合规要求 |

**为什么把"不能做"写在这么显眼的地方**：因为一个说"我查不到"的助手，比一个敢猜的助手有用。这类工具最容易犯的错，是拿常识把缺失的数据补成一个看起来合理的数。

它不是"健康助手"：不给判词、不打分、不说教、不比别的品牌。外号只描述**构成**（`碳水主力`、`蛋白担当`），提醒只指向**动作**（"晚上挑清淡一点的就行"）。判断留给你自己。

## 快速开始

```bash
git clone https://github.com/Prototype-Yuu/mcd-nutrition-translator.git
cd mcd-nutrition-translator

# 1. 申请 Token：https://open.mcd.cn/mcp 手机号登录 → 控制台 → 激活 → 复制
export MCD_MCP_TOKEN="你的 token"

# 2. 看接口通了没（应返回 35 个工具）
python3 scripts/mcp_client.py list | head -40

# 3. 抓真实数据快照（营养表 + 菜单 + 门店）
python3 scripts/fetch_snapshot.py --city 上海 --keyword 人民广场

# 4. 跑测试（42 项，含"故意错配"反例）
python3 -m unittest discover -s tests
```

## 命令行快速体验（无需 Token）

不用申请 Token 也能先看效果，fixture 已内置真实数据：

```bash
# 真实餐卡（巨无霸三件套）
python3 scripts/mealcard.py --input tests/fixtures/real-bigmac.json --format md

# 有条件的配平（600 卡 / 22g 蛋白 / 40 元内）
python3 scripts/mealcard.py --input tests/fixtures/card-solve.json --solve --format md

# 名称对齐覆盖率（复现 48.8% 这个数字）
python3 scripts/normalize.py --nutrition data/nutrition-snapshot.json \
  --menu data/menu-snapshot.json --aliases data/aliases.json --out /tmp/report.json
```

## 使用示例

> 用户：巨无霸多少热量？
> → `list-nutrition-foods` 对齐 → **513 千卡 · 约 1.5 碗米饭**（按本项目参照换算）

> 用户：我点了巨无霸、中薯、中可乐，这套怎么样？
> → 出餐卡，标签 `碳水主力` `顶饱型`，一句提醒指向晚上怎么配

> 用户：中午想吃 400 卡以内，蛋白多点
> → L1：取菜单 → 对齐营养 → 穷举组合 → 返回符合条件组合表

> 用户：麦辣鸡腿汉堡三件套多少卡？
> → 套餐无聚合值，`query-meal-detail` 拆默认组成 → 麦辣鸡腿汉堡 + 中薯条 + 可乐中杯求和

> 用户：这个含花生吗？
> → **不调用任何工具**，说明官方接口没有配料与过敏原数据，引导看包装 / 问门店 / 400-920-0205。见 [references/dietary-boundaries.md](references/dietary-boundaries.md)

## 数据对齐：这个项目真正的难点

官方的营养表和门店菜单**没有共同的键，且套餐没有聚合值**：

- `list-nutrition-foods` 按**餐品名称**给数据，没有餐品编码，`nutritionDescription` 全 null
- `query-meals` 按**餐品编码**组织菜单（名称在 `data.meals` 字典里）
- 套餐（三件套/双人餐/随心选）在营养表里**只有单品、没有合计**

所以要算一单的合计，必须分两类处理：

1. **单品** → 名称对齐（精确 / 去规格 / 别名）
2. **套餐** → `query-meal-detail` 拆出 `isDefault=1` 的默认组成，逐项求和

**实测数字**（2026-10-24，上海人民广场某门店）：营养表 160 条 vs 菜单 129 条。单品直接命中 31 条（24.0%），套餐拆解再补 32 个 → **综合覆盖率 48.8%**，全程零猜值。

**一个反直觉的取舍**：字符相似匹配（Dice bigram）能把命中率"做高"，但实测它 100% 把套餐错配成单品——「培根蔬萃双层牛堡三件套」→「培根蔬萃双层牛堡」，系统性低估热量。所以相似匹配、包含匹配**默认关闭**，「套餐」也从可剥离后缀里移除。宁可命中率低，不误配。

匹配器输出 `matched` / `ambiguous` / `unmatched` 三态，每个匹配带命中层级和分数，`ambiguous` 不自动取值。完整报告见 [data/alignment-coverage.md](data/alignment-coverage.md)。

## 目标用户

**大学生和刚工作的年轻人**，尤其是：

- 想吃麦当劳但看不懂营养表的人 ——「1000 毫克钠到底算多吗」
- 想控制一下但不想记流水账的人
- 只想快速知道「我这一单大概是什么构成」的人

## 隐私与安全

- Token 只走环境变量 `MCD_MCP_TOKEN`，仓库内不含任何真实 Token（`mcp-config.example.json` 只保留占位符）
- `.gitignore` 排除 `.env`；`data/` 里的快照均为脱敏的公开营养/菜单数据，不含个人信息
- 本项目不代付：`create-order` 只返回支付链接，是否支付由用户自己在官方渠道完成

## 目录结构

```
mcd-nutrition-translator/
├─ SKILL.md                     # 技能入口：路由 + 三条铁律 + 文案红线
├─ references/
│  ├─ tools-catalog.md          # 35 个 Tool 分组与验证状态
│  ├─ tool-contracts.md         # 实测入参、返回字段、单位、错误码
│  ├─ analogy-basis.md          # 类比基准 + 来源等级 + 可能错在哪
│  └─ dietary-boundaries.md     # 拒答话术 + 禁止词表
├─ scripts/
│  ├─ mcp_client.py             # 纯标准库 Streamable-HTTP 客户端
│  ├─ fetch_snapshot.py         # 抓营养表 + 菜单 + 门店快照
│  ├─ normalize.py              # 名称归一化 + 对齐匹配器（三态）
│  ├─ decompose.py              # 套餐拆默认组成求和
│  └─ mealcard.py                # 合计 / 类比 / 外号 / 一句提醒 / 穷举求解
├─ tests/                       # 42 个 unittest，含"故意错配"反例
├─ data/                        # 脱敏快照 + 对齐覆盖率报告 + 套餐拆解结果
└─ examples/                    # 真实数据的餐卡示例
```

四条设计约束：真实字段名只出现在适配器一处；`null` 不参与求和但一定进缺失清单；份量基准不明就拒绝给合计；求解用穷举不用启发式（可复现比优雅重要）。

## 参赛合规自查

- ✅ 五件套齐全：`README.md` / `CONTEST_DECLARATION.md`（官方原文）/ `MCP_INTEGRATION.md` / `mcp-config.example.json` / 源码
- ✅ 真实调用过 MCP（`tool-contracts.md` 有 2026-10-24 实测记录）
- ✅ 无 token、无密钥、无个人隐私数据入库
- ✅ 不贬低品牌、不做跨品牌比较、不夸大功能（过敏原/配料/疾病建议一律明示"不提供"）
- ✅ 不刷 Star、不多账号

## 搜索关键词

**中文**：麦当劳 · 麦门 · 麦当劳营养 · 麦当劳热量 · 麦当劳营养成分 · 套餐热量 · 卡路里 · 蛋白质 · 钠 · 说人话 · 营养翻译 · 麦当劳程序员创意开发大赛 · WorkBuddy 技能 · AI 智能体 · Agent Skill · MCP

**English**: McDonald's / McDonalds China / MCD · MCP (Model Context Protocol) · mcd-mcp · nutrition · calories · protein · sodium · meal card · combo decomposition · nutrition translation · WorkBuddy skill · AI agent

## 参赛声明

本项目为「麦当劳程序员创意开发大赛」参赛作品，非麦当劳官方产品。使用的 MCP 能力与调用记录见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。参赛声明见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)。

## License

MIT
