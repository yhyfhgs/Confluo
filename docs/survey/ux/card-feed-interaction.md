---
title: UX 调研：卡片流与滑动交互（抖音/小红书/Tinder 式）及实现技术
status: draft
owner: opus5.5-survey
updated: 2026-09-26
---

# UX 调研：卡片流与滑动交互（抖音/小红书/Tinder 式）及实现技术

> 定位：v2 重设计「④ 前端：类小红书/抖音的论文卡片流」的调研底稿。本文只做调研与规范建议，不含实现代码；文中代码块均为**设计伪代码**。
> 引用约定：正文 `[Rxx]` 对应 §5 参考来源（URL + 核验日期，除另注外均为 2026-09-26 访问核验）。"⚠ 未核验"= 本轮无法用一手来源证实；"⚠ 推断"= 由已核验事实推理得到、未经实测。
> 证据分级：**A** 官方文档/源码/论文/法规原文；**B** 本轮一手实测观察（浏览器渲染、API 返回）；**C** 二手媒体/社区讨论/检索摘要。

## 0. 一页结论

1. **形态**：论文"分拣"最适合**单卡聚焦 + 显式横向决策**（Tinder 横轴：→ 喜欢 / ← 不感兴趣），叠加**抖音纵轴心智**（↑ 下一篇＝中性跳过、↓ 上一篇＝撤销）；"探索/收藏库"用**小红书式双列瀑布流**；"深读"用可下拉关闭的**详情 Sheet**。不做无尽视频式流：**每日有限批次 + 明确结束态**。
2. **卡片 P0 字段**：标题、AI TL;DR（显式标注、可关闭、**绝不替代作者摘要**）、venue·年份、评审状态（预印本/已发表）、开放获取状态、一行"为什么推荐（why-this）"。**关键图必须许可门控**：arXiv 多数论文采用非独占分发许可，其 API 条款禁止第三方存储/再分发 e-print 内容 [R92][R93]。
3. **动效**：跟手 1:1；投影判定 `proj = d + v·0.1s`，横向 `abs(proj) ≥ 0.35W` 提交；回弹 ζ≈0.8、T0≈280ms；飞出保留释放速度 120–280ms；次卡升位 ζ=1.0；详情展开 ζ≈0.9、T0≈390ms；Reduce Motion 退化为 150ms 交叉淡化。
4. **可访问性**：每个手势都有按钮与键盘等价（WCAG 2.2 SC 2.5.1/2.5.7/2.1.1 [R80]）；撤销优先于确认弹窗 [R83]；撤销免费且不限次（对比 Tinder 把 Rewind 放进付费档 [R16]）。
5. **技术栈**：v2.0 **Web-first**（React 19.3 `<ViewTransition>` 已稳定 [R78] + Motion 13 + Base UI Drawer + CSS scroll-snap，PWA 安装）；注意 iOS WebKit 默认把页面渲染节拍压在 ~60fps [R68]、Safari 不支持 Vibration API [R71]。移动留存得到验证后，v2.x 上 **Expo SDK 57 + Reanimated 4 + Gesture Handler 3** 原生客户端。
6. **合规/透明**：卡片 why-this + 设置页"兴趣标签可删 + 可关闭个性化"对应 CAC《互联网信息服务算法推荐管理规定》第16、17条 [R88]（亦与 EU DSA 第27/38条同向 [R87]）；auth-gated 全文及其派生物（抽取图、缓存 PDF）**不得跨用户展示或共享**。

---

## 1. 调研范围与方法

### 1.1 范围与子题映射

| 子题（任务书编号） | 本文章节 | 输出物 |
|---|---|---|
| ① 范式对比：抖音/小红书/Tinder/Reels/X | §2.1 | 形态事实表 + 论文任务适配矩阵 |
| ② 已有"论文版抖音/小红书"产品与开源实现 | §2.2 | 产品表、开源表、PaperTok 深挖、社区反馈归纳 |
| ③ 手势与动效参数 | §2.3 | 平台常数表、开源阈值表、弹簧参数归一化表、判定伪代码、编排、共享元素、触感 |
| ④ 性能 | §2.4 | 性能原则与预算、120Hz 现实、预加载/图片/降级 |
| ⑤ 可访问性与撤销 | §2.5 | WCAG/HIG 映射表、非手势替代、撤销设计 |
| ⑥ 论文卡片信息架构 | §2.6 | 字段优先级表、详情层级、评分极简化、why-this、版权约束 |
| ⑦ 技术栈选型 | §2.7、§2.10 | 对比表 + 推荐 |
| ⑧ 开源 UI 组件 | §2.8 | 组件表（star/许可/活跃度/周下载） |
| 输出：交互规范建议 | §2.9 | 手势映射表、键盘映射、动效参数表、卡片线框、埋点契约 |

不在本文范围：推荐/匹配算法本身（另有调研主题负责；本文只写 UI 需要向算法提供/索取的数据契约）、来源接入与多用户数据库设计。

### 1.2 方法

- **一手优先**：产品行为以官方文档/源码/官方博客为准；开源库参数直接读源码常量（而非二手博客），例如 Motion 的 `springDefaults`、Reanimated 的 `springConfigs.ts`、androidx 的 Material 3 motion tokens。
- **参数归一化**：不同框架弹簧参数口径不同（tension/friction、stiffness/damping/mass、duration/bounce、dampingRatio/stiffness），本文统一换算为**阻尼比 ζ、无阻尼周期 T0、阶跃超调、2% 稳定时间**，换算与数值仿真由本调研完成（初速 0 的阶跃响应，步长 0.2ms），属派生数据。
- **实测观察**：对 JS 渲染站点（抖音安全与信任中心、抖音网页版、小红书网页版、Gist Discover、WikiTok 复盘博客）使用浏览器面板渲染后读取文本/截图；遇登录弹窗仅关闭、不登录；遇 Cloudflare 人机校验（ACM DL）即停止、不绕过（合规红线）。

### 1.3 过程记录（可复现）

日期：全部于 **2026-09-26** 执行。

**WebSearch 检索式**（本会话 WebSearch 配额在第 14 次时耗尽，其后全部改用一手 URL、`gh`、`curl` 与公开 API）：
1. `Scholar Inbox personalized paper recommendations arXiv 2025 Geiger rating interface`
2. `R Discovery app research feed swipe personalized papers CACTUS features 2025`
3. `alphaXiv feed trending papers likes bookmarks comments 2025 funding`
4. `alphaXiv iPhone app launch 2026 papers feed`
5. `Hugging Face Daily Papers upvote trending papers Papers with Code sunset July 2025`
6. `Researcher app researcher-app.com personalized feed journals acquired`
7. `Semantic Scholar Research Feeds rate papers thumbs up relevant not relevant train feed`
8. `单列 双列 信息流 对比 抖音 快手 小红书 沉浸式 选择成本 分发效率 产品分析`
9. `快手 8.0 双列 单列 精选 改版 2020 用户时长`
10. `woshipm 单列 双列 瀑布流 沉浸式 产品设计 选择 用户 主动 被动 小红书 封面 点击率`
11. `Pronk Denissen 2020 "rejection mind-set" choice overload online dating swiping`
12. `Nielsen Norman Group infinite scrolling not for every website pagination findability`
13. `Nielsen Norman Group swipe gestures discoverability contextual swipe mobile`
14. `"project(initialVelocity" "decelerationRate" ... WWDC 2018`（配额耗尽未执行 → 改 `gh search code`）

**GitHub（`gh`）**：
- `gh search repos`：`wikitok`、`arxiv tiktok`、`tiktok for papers`、`paper tiktok`、`arxiv swipe`、`tinder papers`、`papertok`、`arxivtok`、`xivtok`、`scitok`、`tiktok-style`、`arxiv reels`、`react-native-deck-swiper` 等。
- `gh search code`：`springDefaults`/`underDampedSpring`/`defaultElastic`（motiondivision/motion）、`molasses`（pmndrs/react-spring）、`energyThreshold`（software-mansion/react-native-reanimated）、`activeOffsetX`（software-mansion/react-native-gesture-handler）、`SpringDefaultSpatialDamping`（androidx/androidx）、`PreferPageRenderingUpdatesNear60FPSEnabled`（WebKit/WebKit）、`decelerationRate / (1.0 - decelerationRate)`（全站）。
- `gh api repos/{owner}/{repo}`：star、license、`pushed_at`、`archived` 与 README/源码文件（结果见 §2.2、§2.8）。

**公开 API / 直连**：npm registry 与 `api.npmjs.org/downloads`（版本与周下载）；pub.dev API；Flutter releases JSON；Fyrd/caniuse `features-json`；Apple 文档 JSON（`developer.apple.com/tutorials/data/documentation/...` 与 HIG 的 `.../design/human-interface-guidelines/*.json`）；arXiv API（`export.arxiv.org/api/query`）；OpenAlex（`api.openalex.org`）；HN Algolia（`hn.algolia.com/api/v1/search` [R102]，检索词：wikitok / arxiv tiktok / tiktok for papers / tiktok for research papers / tinder for papers / swipe papers arxiv / tiktok for arxiv / doomscroll papers / papertok / ACM AI summaries abstracts）；W3C WCAG 2.2；EUR-Lex（DSA）；网信办（算法推荐规定）；web.dev；MDN；motion.dev；reactnative.dev；docs.expo.dev；docs.flutter.dev；lynxjs.org；webkit.org。

**受阻与处理**：ACM DL（Cloudflare 挑战，未绕过，相关断言标 ⚠）；Tinder 帮助中心与 X 帮助中心/工程博客（HTTP 403，改用 Tinder 订阅页与 xai-org/x-algorithm 仓库）；App Store 页面被重定向到区域首页（alphaXiv 细节标 ⚠）；webkit.org 与部分中文站 WebFetch 证书错误（改用 curl/浏览器）；Semantic Scholar API 返回 429（S2 `tldr` 字段标 ⚠）；小红书/抖音网页登录弹窗（仅关闭，不登录）。

### 1.4 与仓库既有文档的关系

- v1 是本地 CLI，无前端；仓库内无既有 UX 文档。`docs/research/github-similar-projects.md` 调研的是获取/爬取类开源项目，与本文不重叠。
- 本文输出的"UI 事件与 why-this 数据契约"（§2.9.6）需与推荐算法调研、多用户数据模型调研对齐；本文不修改这些文档。

---

## 2. 主体内容

### 2.1 范式对比（①）

#### 2.1.1 五种信息流形态事实表

| 形态 | 代表 | 一屏条目 | 主手势 | 已核验的关键事实 | 证据 |
|---|---|---|---|---|---|
| 单列沉浸全屏 | 抖音、快手"精选"、Instagram Reels | 1 | 上/下滑切换 | 全屏只放一条，用户被迫对"这一条"表态，算法能看清对单条的反应；对比无限纵向 feed 算法"看不到"眼睛停在哪条 [R01]；短内容使单位时间训练数据量高 [R02]；快手 8.0（2020-09-03）在双列点选之外新增"精选"单列上下滑 [R05]；抖音以点击/浏览/喜欢/转发/收藏等行为建模，预测"是否看完/点赞/收藏" [R07] | A/C |
| 双列瀑布流 | 小红书、快手"发现"、抖音网页"精选" | 4–6 | 点选卡片→详情 | 双列给用户选择权、容错高、探索性强；单列减少思考与选择成本、强制曝光但容错低、对算法要求高、易茧房；电商实践：具象搜索词用单列、模糊意图用双列 [R03]；双列封面承担点击转化 [R04] | C |
| Tinder 决策卡 | Tinder、papr（论文） | 1 | 左/右（上）滑 | 连续二元决策出现"拒绝心态"：三项研究中从第一个到最后一个选项接受概率平均下降 27% [R15]；Tinder 把撤销（Rewind）作为 Plus 付费权益 [R16] | A |
| 沉浸 + 网格双入口 | Instagram（Reels + Explore） | 1 / 多 | 两种并存 | Reels（2020-08-05）以竖向 feed 形式放在 Explore 中，可点赞/评论/分享 [R10] | A |
| 列表时间线 | X、arXiv listing | 3–6 | 纵向滚动 + 行内操作 | X 开源排序模型预测的动作族：互动（favorite/reply/repost/quote/share…）、点击（post/profile/link/photo expand…）、注意力（dwell/dwell time/click dwell time/active seconds）、负向（not interested/mute/block/report/**not dwelled**）；最终分 = Σ 权重 × 预测概率 [R08] | A |

**实测观察（B，2026-09-26）**：
- 抖音网页"推荐"页首次进入出现引导浮层：提示可滚动鼠标或按键盘上下键切换，并可点屏幕上的上下按钮；右侧为竖排动作列（头像、喜欢、评论、收藏、分享）。抖音网页"精选"页则是**多列网格**而非单列。
- 小红书网页 explore 为多列瀑布流，卡片 = 封面（视频有播放角标）+ 1–2 行标题 + 作者头像/昵称 + 点赞数；首屏即可见到不少封面本身是**文字排版图**（纯文字/手写截图）。移动端为双列（⚠ 本轮未在 App 内实测，依据 [R03][R04] 描述）。

#### 2.1.2 三维取舍（决策成本 / 信息密度 / 沉浸感）

| 形态 | 决策成本 | 信息密度 | 沉浸感 | 反馈信号洁净度 | 主要风险 |
|---|---|---|---|---|---|
| 单列沉浸 | 低（不选择，滑走即可） | 低（每屏 1 条） | 高 | 高（单条独占屏幕 [R01]） | 茧房、容错低 [R03]；无限流懊悔循环 [R13] |
| 双列瀑布流 | 中（需挑选） | 中高 | 低 | 中（点击是强意图 [R03]，未点击的曝光含义弱） | 依赖封面质量 [R04] |
| Tinder 决策卡 | 中（每张必须二选一） | 低-中 | 中 | **最高**（显式二元标签） | 拒绝心态 [R15]、手势可发现性差 [R12] |
| 列表时间线 | 最低（浏览） | 最高 | 中 | 需靠 dwell 近似 [R08] | 无限滚动的键盘可达性、返回丢位置 [R11] |

（表中高/中/低为本调研的定性分析，依据见"证据"列。）

#### 2.1.3 哪种最适合论文？——按研究者任务拆分

研究者在卡片上要做的判断是"值不值得读"，信息主要是**文字**（标题、摘要）而非视觉；社区反馈也指出手机上读 arXiv 基本只看摘要 [R28]。据此按任务评估：

| 研究者任务 | 频率 | 最适合形态 | 理由 |
|---|---|---|---|
| T1 每日新论文分拣（20–50 篇） | 每日 | **单卡聚焦 + 显式横向决策** | 需要为推荐器产出干净的显式标签（Scholar Inbox 👍/👎 [R17]、S2 Research Feeds relevant/not relevant [R27]、ASReview relevant/irrelevant [R39] 均为同构"一次一条 + 二元标注"）；单卡独占屏幕保证信号只归属这一篇 [R01] |
| T2 主题探索 / 看看最近热门 | 每周数次 | **双列瀑布流** | 用户需要比较与挑选；双列容错高、探索性强 [R03]；Instagram/快手均采用"网格 + 沉浸"双入口 [R05][R10] |
| T3 深读前的细看 | 每篇 | **详情 Sheet**（卡片原位放大） | 保持分拣位置，避免返回后丢失位置（pogo-sticking）[R11] |
| T4 回顾收藏库 | 每周 | 双列瀑布流 / 桌面紧凑列表 | 回找与管理任务不宜无限流 [R11] |

**结论**：不照搬抖音"纯视频式无限流"，也不照搬纯 Tinder。推荐"**分拣 Deck（主）+ 双列瀑布流（探索/库）+ 详情 Sheet**"三件套；纵向沉浸流仅作为实验模式（见 §2.9.2 映射 C）。每日分拣是**有限批次**并有结束态：Instagram 2018 年起在看完近两天内容后提示"已全部看完" [R09]；无限滚动被报告会让用户陷入"循环"、懊悔地延长会话，Rixen 等以一周田野研究（N=46）刻画了该循环与退出原因 [R13]，干预效果受情境影响（N=72，7 天）[R14]。

### 2.2 既有"论文版抖音/小红书"产品与开源实现（②）

#### 2.2.1 商业/学术产品

| 产品 | 形态 | 反馈与交互 | 卡片内容 | 关键事实（日期） | 证据 |
|---|---|---|---|---|---|
| Scholar Inbox（图宾根 Geiger 组，ACL 2025 Demo） | 移动友好卡片列表 + 每日/每周 digest（可指定工作日邮件） | 👍/👎 二元评分；显式负样本与随机负样本分别加权；主动学习：分层采样，优先请用户评"决策边界附近及以上"的论文 | 标题、摘要、作者、venue、**PDF 前五张图表（papermage 抽取）**；相关度分数缩放到 [-100,100] 并用表头颜色编码；评分/书签/收藏夹/bibtex 快捷按钮 | 冷启动三路：作者检索（自己的论文）、Scholar Maps（300 万论文 t-SNE 地图）、主动学习；80 万评分、1.43 万评分用户、2.3 万注册、30 日活跃 8 千（35%）；GTE-Large F1 84.51% | A [R17] |
| Semantic Scholar Research Feeds | 基于 Library 文件夹的推荐 feed | Library 收藏＝正信号，feed 内标 "not relevant"＝负信号；官方建议起步评 5 篇相关 + 3 篇不相关 | — | FAQ 现行说明 | A [R27] |
| alphaXiv | Trending feed + 论文页讨论 | 点赞、书签、评论（含行内评论） | — | 2025-11-19 宣布 700 万美元种子轮（Menlo Ventures、Haystack 共同领投）；iOS 版 App Store 首发 **2026-07-08**（iTunes Lookup `releaseDate`；官方 X 帖 2026-07-13 宣布），现版本 1.4.0（2026-09-01）、需 iOS 17+；商店描述：Trending Feed 以"quick informative blurbs"帮助决定细读哪篇、Library、AI Assistant、Paper Reader（高亮/笔记）、AI Visual Blogs（核验修正：原文把 X 帖日期当作发布日，且商店细节已可经 Lookup API 直读） | A [R18][R19] |
| Hugging Face Papers | Daily/Weekly/Monthly/Trending 列表 | upvote、讨论（自动翻译）、librarian-bot 推荐相关论文、工作日邮件订阅、作者认领 | 缩略图、标题、提交者、upvote 数、评论数、机构徽标、作者 | Trending Papers 于 2025-07-28 上线（changelog，按近期 GitHub star 活跃度排序）；Papers with Code 于 2025-07-24 下线（HF 员工 AK 2025-07-25 X 帖称"昨日"下线），paperswithcode.com 现 302 重定向至 `huggingface.co/papers/trending`（2026-09-26 实测） | A/B/C [R20][R21][R22][R23] |
| R Discovery（CACTUS） | 个性化阅读 feed | 收藏/书单协作；音频论文；30+ 语言翻译；Prime 定价以 Editage 页为准：$5/月、$12/季、$39/年（核验修正：原文"每月 12 美元起"系误读季付价；价格随促销/地区变动 ⚠） | "Research in Shorts"：以类 Instagram Story 的格式呈现论文要点（核验补充） | Google Play 描述原文：用大学凭证登录、经 **GetFTR & LibKey 集成**访问付费墙论文（核验确认）——与本项目"用户自有凭证"模式同构 | A [R24][R25] |
| Researcher | 社媒风格个性化 feed（关注期刊 + 关键词过滤） | — | — | 2019-10-10 T&F 新闻稿：15,000+ 期刊、100 万+ 学者；更新的宣传口径 18,000+ 期刊/200 万（⚠ 未核验） | A/C [R26] |
| Papel（Show HN 2026-05-11，200 分；iOS，着陆页仍为候补名单） | 全屏沉浸论文卡 | 按兴趣/热度/新鲜度/社区互动排序，可切 "Latest" 时间序；端侧 AI 问答（Apple Intelligence/MLX）；每篇 3 题测验 + XP/连胜；点赞/评论/私信 | — | 着陆页自述 | A/B [R28] |
| Gist Discover（Show HN 2026-07-02） | 一次一篇 | ♥ + Next；**横向分层**：Gist → Logic → Counter-argument → Steelman；朗读/倍速 | 一句结论式 gist | 2026-09-26 实测 | B [R29] |
| ArTok（Show HN 2025-04-21） | AI/ML 会议论文发现 | 保存；免注册 | — | 着陆页自述 | C [R30] |
| Open Paper Digest（Show HN 2025-12-02） | 摘要流 | 点击展开摘要 | — | 自称 "Doomscrolling for Smart People" | C [R31] |
| papr（JHU Data Science Lab，2016） | bioRxiv 摘要 "Tinder" | **四向滑动编码 2×2**：有趣/无聊 × 可信/存疑；界面左侧常驻方向图例 | 摘要 | 仓库 2019 年后停更 | A [R34] |
| ASReview LAB（系统综述筛选） | 一次一条题录 | Relevant/Irrelevant 按钮；快捷键 `r`/`i`/`n`（笔记）；每次标注触发异步重训并重排剩余题录 | 标题 + 摘要（+DOI 链接） | 专业"分拣"工具的成熟先例 | A [R39] |
| Covidence（系统综述筛选，核验补充） | 题录/摘要逐条筛选 | **Yes / Maybe / No 三态投票**；默认双人盲审（两名不同审稿人各投一票才推进） | 标题 + 摘要 | 专业筛选工具把"不确定"做成一等选项 | A [R104] |
| Rayyan（系统综述筛选，核验补充） | 列表 + 详情窗格 | **Include / Maybe / Exclude**；Maybe 进入独立列表（与未决、已决分开，可随时筛出）；决策栏 + 键盘快捷键（按 `V` 打开快捷键面板；默认快捷键各方案可用，自定义仅限 Essential 及以上方案） | 标题 + 摘要 | 支持本文"↑ 中性跳过/稍后再看"不计负反馈的设计 | A [R105] |

#### 2.2.2 开源实现（数据 2026-09-26，`gh api`）

| 仓库 | ★ | License | 最近推送 | 技术栈 | 交互 | 可借鉴点 |
|---|---|---|---|---|---|---|
| IsaacGemal/wikitok | 1,324 | MIT | 2025-03-18 | React 18 + TS + Tailwind + Vite（bun） | 纵向无限流、图片与内容预加载、14 语言、PWA | HN 2025-02-04 首发 1,459 分；作者复盘：约 2 小时用 Claude+Cursor 搭出、IntersectionObserver 哨兵触发每次拉 5 条、后期**直接丢弃无缩略图条目**、拒绝加入"算法"与用户数据 [R35] |
| terrakok/WikWok | 163 | Apache-2.0 | 2026-06-18 | Kotlin 2.4 + Compose Multiplatform 1.12.0-alpha02 | TikTok 式文章流；Android/桌面/Web，iOS 以 PWA 安装 | KMP 单代码多端先例 [R36] |
| Miguel07Alm/arxivtok | 91 | MIT | 2025-02-07 | SolidJS/SolidStart + Tailwind + KaTeX | 上下滑切换、双击赞、多源（arXiv/medRxiv/bioRxiv/PubMed/HN）、搜索 | WikiTok 后第二天即出现的论文版衍生 [R37] |
| mugar123/papertok | 27 | MIT | 2026-09-26 | React + Vite + Firebase + Framer Motion + KaTeX + Base UI | CSS scroll-snap 纵向流；底部抽屉放评论/相关/作者；"Research" 报纸式版面；PWA | 见 §2.2.3，**与本项目最接近的开源参照** [R38] |
| ViffyGwaanl/papertok | 17 | — | 2026-02-18 | Python | 未深入 | — |
| jtleek/papr | 19 | — | 2019-05-15 | R Shiny + shinysense | 四向滑动 | 反例：四向×二维编码需常驻图例 [R34] |
| asreview/asreview | 1,019 | Apache-2.0 | 2026-09-21 | Python + Web | 一次一条 + 快捷键 | 分拣键盘操作先例 [R39] |
| karpathy/arxiv-sanity-lite（核验补充） | 1,696 | MIT | 2023-06-19 | Python（Flask + scikit-learn + sqlitedict/SQLite） | 用户给论文打标签；按每个标签在摘要 tf-idf 特征上训练 SVM 推荐新论文；每日推荐邮件 | "显式标签 → 个人模型 → 每日批次"最小闭环的经典开源先例（非卡片 UI）[R106] |

另有大量 0–1 star 的"刷论文"原型（多数创建于 2025–2026 年；`TsaiLintung/paper-scroll` 创建于 2024-10，核验：所列 6 个仓库均存在、均为 0★）（`chiaralisotti/arxiv-swiper`、`spacekorean/arxiv-swipe`、`TsaiLintung/paper-scroll`、`nonidino/paperspark`、`chu0802/arxiv_reels`、`cookiegg/paper-tiktok` 等），以及 HN 上的 PapersTok（2025-02，站点现已不可达）[R32]、pokepaper（2026-02）[R33] 等 Show HN 原型，说明这是高频的快速原型题材，但普遍缺乏持续维护与推荐闭环。

#### 2.2.3 PaperTok（mugar123）深挖——可直接借鉴的实现细节

读取仓库 `design.md`、`src/components/Feed/FeedContainer.css`、`PaperCard.css`、`src/components/ui/drawer.jsx` 与 README [R38]：

- **纵向流**：`scroll-snap-type: y mandatory` + `scroll-snap-stop: always`（一次甩动只过一篇），每项高 `calc(100dvh - 导航高)`，`overscroll-behavior-y: contain`；关闭 scroll anchoring，避免追加分页时"一帧跳变"。——用原生滚动吸附而非 JS 拖拽实现抖音式流，是 Web 端最省性能的做法。
- **动效**：卡片 `transform 320ms` + ease-out-expo；入场 `cubic-bezier(0.16, 1, 0.3, 1)` 0.32–0.36s，子元素错峰 45ms；有 `prefers-reduced-motion` 分支；用独立的 `translate`/`rotate` 属性与 `transform` 组合，避免多个动画争抢同一属性。
- **视觉系统**：颜色来自数据（12 个领域色，卡片以领域色条为唯一强调）；三种字体角色（UI 用 Inter、正文/标题用衬线 Newsreader、元数据用等宽 IBM Plex Mono）；动作键静止态中性、按下才上色，`aria-pressed` 承载状态。
- **诚实标签**：每张卡回答两个问题——是否经过同行评审（Preprint / Verified）、能否读到（Open access / Open version / Subscription）；**数据缺失就不显示，不猜**。
- **抽屉**：基于 Base UI Drawer（swipe-to-dismiss、snap points），用于评论、关注、相关论文、作者；无手势面板用 Sheet。
- **设计变更记录（2026-08-25）**：主题标签原在动作行，概念多时把动作行挤成多行、窄屏裁掉按钮；改为标题上方**单行横向滚动**（右侧 mask 渐隐）。——卡片内"数量由数据决定的列表"必须定高。

#### 2.2.4 社区反馈归纳（HN：Papel 发布帖，2026-05-11，42 条顶层评论）[R28]

以下为 C 级证据（个人意见，非统计），但对设计有直接启发：
1. 手机上读 arXiv 基本只看摘要，建议把摘要要点化。
2. TikTok 式体验的本质是"无摩擦"：打开即见内容，登录/说明应后置。
3. 多人要求 **AI 可关闭**；有评论提到 ACM DL 曾以 AI 摘要替代作者摘要、需切换才能看到原摘要并引发反弹。核验：ACM 官方在 CACM（2026-03-03，Davidson & Graves）确认 DL Premium 推出过 AI 生成的长/短摘要，社区对准确性、与作者摘要重复及学术场景中 AI 内容的角色提出质疑，ACM 随即加了免责声明与用户反馈机制并调整生成流程 [R114]；但"替代作者摘要、需切换才能看到原摘要"这一细节仍 ⚠ 未核验（dl.acm.org 受 Cloudflare 挑战未访问；检索摘要显示其现行说明为作者摘要默认加载、AI 摘要在独立标签页）。另见 HN 2025-12-17 帖 [R103]。
4. 担心流行度指标与 AI 造成偏置，让有用但冷门的论文更难被发现。
5. 有评论以 alphaXiv 为例质疑研究者的社交互动意愿（评论稀少）——单人观点，但提示"评论区"冷启动风险。
6. 性能被点名（CPU 占满、滚动卡顿）。
7. "TikTok" 品牌在学术用户中有负面联想，建议去掉该标签。

### 2.3 手势与动效参数（③）

#### 2.3.1 平台与框架的手势常数

| 常数 | 取值 | 出处 |
|---|---|---|
| iOS 滑动判定滞后（hysteresis） | 约 10 pt | WWDC18 Designing Fluid Interfaces [R40] |
| Android `TOUCH_SLOP` / `PAGING_TOUCH_SLOP` | 8 dp / 16 dp | AOSP `ViewConfiguration` [R59] |
| Android 最小/最大 fling 速度 | 50 / 8000 dp/s | 同上 |
| Android 长按 / 双击 / tap 超时 | 400 / 300 / 100 ms | 同上 |
| Android `ItemTouchHelper` 滑删阈值 | 0.5（视图宽度比例）；逃逸速度 120 dp/s（上限 800 dp/s）；动画 250 ms | androidx `ItemTouchHelper` + dimens [R58] |
| Compose M3 `SwipeToDismissBox` | 位置阈值 56 dp；速度阈值 125 dp/s | androidx 源码 [R57] |
| Android 手势导航排除区 | `setSystemGestureExclusionRects()`（API 29+）；系统只采纳纵向合计 **200 dp** 以内的排除区，且不建议为整块滚动区注册 | [R60][R61] |
| iOS/HIG | 不要与访问系统 UI 的手势冲突；自定义手势只作标准手势的补充，且不能是完成重要操作的唯一方式 | HIG Gestures [R62] |
| RNGH Pan（v3） | `activeOffsetX/Y`（点内移动不激活）、`failOffsetX/Y`（越界即失败）、`minVelocity*` 单位 pt/s | [R55] |
| Motion drag | `dragElastic` 默认 0.35；惯性 `timeConstant` 750ms、`bounceStiffness` 200/`bounceDamping` 40（有 elastic 时）；`dragDirectionLock` 首轴锁定；`onDragEnd` 提供 offset/velocity | 源码 [R46]、文档 [R47] |

#### 2.3.2 开源卡片组件的阈值与形变（源码/README 默认值）

| 组件 | 判定方式 | 位置阈值 | 速度阈值 | 旋转 | 叠层 | 动画时长/弹簧 | 证据 |
|---|---|---|---|---|---|---|---|
| react-spring `cards-stack` 官方示例 | 仅速度 | — | `velocity > 0.2`（use-gesture 速度单位） | `rot = mx/100`，飞出再加 `dir·10·v` | 初始随机 ±10° | 按下 tension 800 / 回弹 500 / 飞出 200，friction 均 50 | [R48] |
| react-tinder-card 1.6.4 | 速度（默认）或位置 | 位置模式 README 建议按屏宽设置 | `swipeThreshold` 0.5 | `maxTilt` 25° | — | 跟手 2000/50；回弹 200/10；飞出时长 = 对角线/速度 | [R49] |
| react-native-deck-swiper 2.0.19 | 位置 | 横 W/4、纵 H/5 | — | ±10° @ ±W/2 | 下层偏移 10、缩放 −3%/层 | 飞出 350ms；叠层弹簧 friction 7 / tension 40 | [R50] |
| rn-swiper-list | 位置（速度可选，px/s） | 映射区间 ±W/3、±H/3 | 默认关闭 | ±π/20（≈±9°）@ ±W/3 | 预渲染 N−1 | 弹簧 stiffness 50 / damping 20 / mass 1，禁超调；翻面 500ms；`swipeBack`、`restoredSwipes` | [R51] |
| flutter_card_swiper 7.2.0 | 位置 | `threshold` 50 | — | `maxAngle` 30 | 显示 2 张，后卡 `scale` 0.9 | 200ms；支持 undo | [R52] |

观察：旋转斜率 ≈ 20–27°/W（deck-swiper 20°/W、rn-swiper-list 27°/W），上限 10–30°；位置阈值 0.25–0.5W；飞出 200–350ms。Tinder 自身参数未公开（⚠ 未核验）。

#### 2.3.3 弹簧参数归一化对照（派生计算）

| 来源 | 原始参数 | ζ | T0 | 阶跃超调 | 2% 稳定 | 证据 |
|---|---|---|---|---|---|---|
| Motion 默认 spring | stiffness 100 / damping 10 / mass 1（bounce 0.3、visualDuration 0.3s） | 0.50 | 628ms | 16.3% | 807ms | [R46] |
| Motion 变换属性默认（x/y/rotate） | 500 / 25 | 0.56 | 281ms | 12.0% | 261ms | [R46] |
| Motion 缩放到 0 | 550 / 2√550 | 1.00 | 268ms | 0 | — | [R46] |
| react-spring `default` | tension 170 / friction 26 | 1.00 | 482ms | 0 | 445ms | [R48] |
| react-spring `gentle` / `wobbly` / `stiff` / `slow` | 120/14、180/12、210/20、280/60 | 0.64 / 0.45 / 0.69 / 1.79 | 574 / 468 / 434 / 375ms | 7.3 / 20.8 / 5.0 / 0% | 547 / 622 / 413 / 786ms | [R48] |
| cards-stack 示例（按下 / 回弹 / 飞出） | 800/50、500/50、200/50 | 0.88 / 1.12 / 1.77 | 222 / 281 / 444ms | 0.2 / 0 / 0% | 160 / 318 / 915ms | [R48] |
| react-tinder-card（跟手 / 飞出 / 回弹） | 2000/50、400/30、200/10 | 0.56 / 0.75 / 0.35 | 140 / 314 / 444ms | 11.9 / 2.8 / 30.5% | 130 / 286 / 774ms | [R49] |
| rn-swiper-list | 50 / 20 | 1.41 | 889ms | 0 | 1400ms | [R51] |
| Reanimated 4 默认（=Gentle） | mass 4 / stiffness 900 / damping 120（或 duration 550 / dampingRatio 1） | 1.00 | 419ms | 0 | 389ms | [R53][R54] |
| Reanimated 4 Snappy / Wiggly | 900/110/4（禁超调）、900/90/4 | 0.92 / 0.75 | 419ms | 0.1（理论值；Snappy 设 `overshootClamping: true`，实际为 0）/ 2.8% | 326 / 382ms | [R53] |
| Reanimated 3 旧默认 | 100 / 10 / 1 | 0.50 | 628ms | 16.3% | 807ms | [R53]（v4 迁移文档称旧默认"在实际应用中用处不大"） |
| SwiftUI `.spring` / `.smooth` 默认 | duration 0.5 / bounce 0 | 1.00 | 500ms | 0 | 465ms | [R45] |
| SwiftUI `interactiveSpring` 默认 | response 0.15 / dampingFraction 0.86 | 0.86 | 150ms | 0.5% | 102ms | [R45] |
| SwiftUI 旧 `spring(response:dampingFraction:)` 默认 | 0.5 / 0.825 | 0.83 | 500ms | 1.0% | 315ms | [R45] |
| WWDC23 bounce 指南 | 0（通用）/ 0.15（尾段更利落）/ 0.3（明显弹性）/ >0.4 对 UI 过度 | ≈1.0 / 0.85 / 0.70 | — | 0 / 0.6 / 4.6%（T0=0.5s 时） | — | [R44]（ζ≈1−bounce 为本调研按其换算关系推导） |
| WWDC18 指南 | 默认 100% 阻尼；手势带动量时用约 80% 阻尼奖励动量 | 1.0 / 0.8 | — | 0 / 1.5% | — | [R40] |
| Material 3 Standard 空间（快/默认/慢） | dampingRatio 0.9；stiffness 1400 / 700 / 300 | 0.9 | 168 / 237 / 363ms | ≈0.1% | 126 / 178 / 272ms | [R56] |
| Material 3 Expressive 空间（快/默认/慢） | 0.6/800、0.8/380、0.8/200 | 0.6 / 0.8 / 0.8 | 222 / 322 / 444ms | 9.4 / 1.5 / 1.5% | 210 / 193 / 266ms | [R56] |
| Material 3 效果类（颜色/透明度） | dampingRatio 1.0；stiffness 3800 / 1600 / 800 | 1.0 | 102 / 157 / 222ms | 0 | — | [R56] |
| Material 3 缓动 | Emphasized / Standard `(0.2,0,0,1)`；Emphasized Decelerate `(0.05,0.7,0.1,1)`；Emphasized Accelerate `(0.3,0,0.8,0.15)`；时长 token Short1–4 = 50–200ms，Medium1–4 = 250–400ms，Long1–4 = 450–600ms | — | — | — | — | [R56] |

要点：Reanimated 4、SwiftUI iOS 17+、M3 的"现代默认值"已收敛到 **ζ≈0.8–1.0、T0≈0.25–0.5s**；而 Reanimated 3 旧默认与 **Motion 现行** `type: "spring"` 物理默认（均为 100/10/1）ζ=0.5、超调 16%，Motion 对 x/y/rotate 的现行默认 500/25 也只有 ζ≈0.56（核验修正：Motion 并未随之收敛，其 100/10/1 不是"早期"默认），对学术工具显得"弹"——用 Motion 时须显式传入 §2.9.4 的参数。

#### 2.3.4 判定算法：位移 + 速度 + 投影

WWDC18 建议不要只看松手位置，而要用触摸历史速度做**动量投影**决定去向；投影函数被社区按其幻灯片（FloatingPanel 注释引 slide p176）复刻为 `(v/1000)·r/(1−r)`，`r` 取 `UIScrollView.DecelerationRate`（normal 常用 0.998）[R40][R41][R43]。换算：`r=0.998` 时投影 ≈ `v × 0.499s`，`r=0.99` 时 ≈ `v × 0.099s`（本调研计算）。卡片判定需要比滚动更"保守"，故取 τ≈0.1s。

```text
// 设计伪代码（非实现）：Deck 顶卡拖拽判定
TAU = 0.10 s            // 投影时间常数（≈ r=0.99 的投影系数）
X_COMMIT = 0.35 · W     // W = 卡片宽；参考 deck-swiper W/4、ItemTouchHelper 0.5W 的中间值
Y_COMMIT = 0.20 · H     // H = 卡片高；参考 deck-swiper H/5
V_ESCAPE = 800 pt/s     // 参考 ItemTouchHelper 逃逸速度上限 800dp/s
AXIS_SLOP = 10 pt       // iOS hysteresis；Android 8dp
EDGE_DEADZONE = 24 pt   // 屏幕左右边缘不接管，留给系统返回手势

on down(p):  if p.x < EDGE_DEADZONE or p.x > screenW - EDGE_DEADZONE: pass to system
on move(d):  if axis unset and hypot(d) >= AXIS_SLOP: axis = abs(d.x) >= abs(d.y) ? X : Y
             if axis == X:
               card.x = d.x                                   // 1:1 跟手
               card.rotate = clamp(d.x / W * 16deg, -12deg, 12deg)
               p = clamp(abs(d.x) / X_COMMIT, 0, 1)
               label(dir(d.x)).opacity = smoothstep(0.3, 1.0, p)
               back.scale = lerp(0.95, 1.0, p); back.y = lerp(10, 0, p)
               if p crosses 1.0 upward: haptic(selection)      // 仅首次越过
on up(d, v): proj = d + v * TAU
             if axis == X and (abs(proj.x) >= X_COMMIT or (abs(v.x) >= V_ESCAPE and sign(v.x) == sign(d.x))):
                  commit(d.x > 0 ? LIKE : NOT_INTERESTED, releaseVelocity = v)
             elif axis == Y and (abs(proj.y) >= Y_COMMIT or (abs(v.y) >= V_ESCAPE and sign(v.y) == sign(d.y))):
                  commit(d.y < 0 ? NEXT_NEUTRAL : PREVIOUS_UNDO, releaseVelocity = v)
             else: springBack(stiffness 500, damping 36)       // ζ≈0.80
```

实现要点：
- **轴锁**：Web 端对 Deck 容器设 `touch-action: none`（完全接管），对可纵向滚动的详情区设 `touch-action: pan-y`（浏览器处理纵滚、JS 只拿横向）[R72]；RN 端用 `activeOffsetX: [-10, 10]` + `failOffsetY: [-10, 10]` 让横滑与纵滚互斥 [R55]；Motion 可用 `dragDirectionLock` [R47]。
- **边缘冲突**：iOS/Android 都把屏幕边缘留给系统返回手势 [R60][R62]；Android 的排除区纵向合计只有 200dp 且不应覆盖大块区域 [R61]，因此**不要试图排除整张卡**，而是让卡片起手区离开边缘。
- **下拉刷新/回弹**：Deck 页面设 `overscroll-behavior: none`（Safari 16+ 支持）[R71]，避免 ↓ 手势触发浏览器下拉刷新。
- **禁止双击**：Deck 上不绑定双击（Android 双击判定窗口 300ms [R59]，会拖慢单击响应）；点赞走右滑/按钮。

#### 2.3.5 飞出与下一张入场的衔接（编排）

| 阶段 | 顶卡 | 次卡（第 2 张） | 第 3 张 | 依据 |
|---|---|---|---|---|
| 拖拽中 | 1:1 跟手 + 线性旋转 | `scale 0.95→1`、`y 10→0` 随进度插值 | 静止（`scale 0.90`，不透明度 0.6） | 叠层参数参考 deck-swiper（10、3%）[R50]、flutter_card_swiper（0.9）[R52] |
| 提交 | 保留释放速度继续运动：时长 = 剩余距离 / max(abs(v), 1000pt/s)，夹在 120–280ms；旋转继续到 ±12° | 与顶卡**并行**升位：spring 600/49（ζ=1.0，~240ms） | 淡入到第 3 位（150ms） | 保速飞出参考 react-tinder-card（时长=距离/速度）[R49]；WWDC18"动量传递"[R40] |
| 未过阈值 | 回弹 spring 500/36（ζ≈0.80，T0≈281ms，超调≈1.4%） | 反向插值回 0.95 | — | WWDC18：有动量时 80% 阻尼 [R40] |
| 撤销 | 上一张从其离开方向飞回：spring 400/32（ζ≈0.80，T0≈314ms） | 退回第 2 位 | 退回第 3 位 | rn-swiper-list `swipeBack` [R51]、flutter_card_swiper undo [R52] |
| Reduce Motion | 不位移不旋转：顶卡 150ms 淡出、次卡 150ms 淡入 | 同左 | — | HIG Motion 与 Reduce Motion [R64][R65]；Motion `reducedMotion="user"` 会关闭变换/布局动画、保留透明度 [R47] |

另：下一张卡必须**预先挂载且图片已解码**（§2.4.3），否则飞出期间会出现空白帧；HIG 也提醒频繁发生的交互不宜加入过多动效 [R64]，分拣是高频操作，编排总时长控制在 ~300ms 内。

#### 2.3.6 卡片 → 详情：共享元素转场

| 技术 | 能力 | 状态（2026-09-26） | 证据 |
|---|---|---|---|
| View Transitions API（同文档） | 浏览器级共享元素/容器变形 | Chrome 111+、Safari 18.0+、Firefox 144+；全球可用约 91.8% | [R71] |
| View Transitions（跨文档） | MPA 页间转场 | Chrome 126+、Safari 18.2+；Firefox 144/145 仅部分 | [R71] |
| React `<ViewTransition>` | 声明式包裹，进入/退出/移动/尺寸变化动画 | **React 19.3（2026-09-09）转为稳定** | [R78] |
| Motion `layoutId` / `layout` | 共享元素与布局动画，全部用 transform 实现 | 稳定 | [R47] |
| SwiftUI | `matchedGeometryEffect`（iOS 14+）；`.navigationTransition(.zoom(sourceID:in:))`（iOS 18+） | 稳定 | [R67] |
| Flutter | `Hero` 组件 | 稳定 | [R97] |
| Reanimated | `sharedTransitionTag` | **实验特性，需 feature flag，不建议生产** | [R79] |

规格建议：展开用 spring 260/29（ζ≈0.90，T0≈390ms，稳定≈291ms）或 M3 Emphasized Decelerate + 400ms（Medium4）[R56]；关闭跟随下拉手势，松手按投影判定（`r=0.998`）是否关闭，未关闭则 spring 700/53（ζ=1.0）回位；背景加 40% 墨色遮罩 + 模糊（PaperTok 同类做法 `rgba(17,19,24,0.4)` + blur [R38]）。**返回后必须停在原卡**，避免 NN/g 所述"返回丢位置" [R11]。

#### 2.3.7 触觉反馈

| 平台 | API | 事实 | 证据 |
|---|---|---|---|
| iOS 原生 | `UIImpactFeedbackGenerator`（iOS 10+）；SwiftUI `.sensoryFeedback(_:trigger:)`（iOS 17+） | HIG：触感应补充其他反馈而非替代，应可关闭，并与系统标准触感保持一致 | [R63][R67] |
| React Native/Expo | `expo-haptics`：`impactAsync`（Light/Medium/Heavy/Rigid/Soft）、`selectionAsync`、`notificationAsync`；Android 推荐 `performAndroidHapticsAsync` | iOS 在低电量模式、用户关闭 Taptic、相机或听写进行中时**不会触发** | [R82] |
| Web（PWA） | `navigator.vibrate()` | Safari/iOS Safari **不支持**；需要粘性用户激活 | [R71][R74] |
| Capacitor 壳 | `@capacitor/haptics` 8.0.2 | 可为 Web 代码提供原生触感 | [R95] |

映射建议：越过判定阈值 → selection（仅一次）；提交"喜欢"→ light impact；"收藏"→ success notification；"不感兴趣"→ 无触感（避免负向强化）；撤销 → soft impact。全部可在设置中关闭。

### 2.4 性能（④）

#### 2.4.1 渲染原则

| 原则 | 依据 | 本项目规则 |
|---|---|---|
| 只动 `transform`/`opacity`，用 `will-change` 或 `translateZ` 提升移动元素，但不要滥用（图层占内存） | web.dev [R75][R76] | Deck 仅 3 张卡设 `will-change: transform`；阴影用静态伪元素而非动画 `box-shadow` |
| Motion 布局动画全部基于 transform；JS 驱动的动画跑在主线程，WAAPI/CSS 可硬件加速 | [R47] | 拖拽跟手必须是 JS（需读指针）；非跟手的入场/淡入可交给 CSS/WAAPI |
| INP：p75 ≤ 200ms 为良好，> 500ms 为差 | web.dev INP（2025-09-02 更新）[R77] | 按钮/键盘提交到下一张可交互 ≤ 100ms（设计目标） |
| 无限流对键盘用户与"返回位置"不友好 | NN/g [R11] | Deck 为有限批次；探索网格虚拟化 + 恢复滚动位置 |

#### 2.4.2 120Hz 的现实

| 平台 | 事实 | 证据 |
|---|---|---|
| iOS 原生 | ProMotion 设备需在 Info.plist 设 `CADisableMinimumFrameDurationOnPhone = YES` 才能请求高于系统默认的帧率（iOS 15+） | [R66] |
| iOS WebKit（Safari/WKWebView/PWA） | WebKit 偏好 `PreferPageRenderingUpdatesNear60FPSEnabled` 默认 **true**（visionOS 除外）：页面渲染更新优先贴近 60fps 而非屏幕刷新率 | 源码 [R68] |
| 推论 | PWA 在 iPhone 上用 JS 驱动的跟手拖拽动画上限约 60Hz；原生滚动（含 CSS scroll-snap）由系统滚动视图处理，可能不受此限 | ⚠ 推断（未在真机测帧） |
| React Native | Reanimated 4 在 UI 线程运行 worklets，仅支持新架构 [R99]；Expo 模板默认已开启 `CADisableMinimumFrameDurationOnPhone`（`expo-template-bare-minimum` 的 Info.plist 与 `@expo/config-plugins` 默认 Info.plist 均为 `true`，核验确认） | [R99][R107] |
| Flutter | Impeller 自 3.27 起为 iOS 与 Android API 29+ 默认渲染器，iOS 上是唯一渲染器 | [R97] |
| Android Chrome | rAF 是否随高刷屏提升 | ⚠ 未核验 |

#### 2.4.3 预加载、虚拟化与图片

- **窗口**：DOM/视图中只保留 3 张卡（当前 + 2 张叠层），另预取 5 条数据、预解码 2 张图（设计值）。先例：WikiTok 以 IntersectionObserver 哨兵提前拉取，每批 5 条 [R35]；rn-swiper-list `prerenderItems`、flutter_card_swiper `numberOfCardsDisplayed`、deck-swiper `stackSize` 都把"预渲染几张"做成显式参数 [R50][R51][R52]。
- **瀑布流**：Web 用 TanStack Virtual 或 masonic 虚拟化；RN 用 FlashList/LegendList（§2.8）。长卡内容可用 `content-visibility`（Safari 18+、Firefox 125+）[R71]。
- **图片格式**：AVIF（iOS Safari 16+，全球约 95.3%）、WebP（约 96.7%）；原生 `loading="lazy"`（iOS Safari 16.4+）；`<link rel=preload>`；IntersectionObserver（iOS 12.2+）[R71]。服务端生成两档缩略图（卡片 1x/2x 与网格小图）；`decoding="async"` 避免主线程解码（⚠ 支持度本轮未查）。
- **图片可用性本身是个合规问题**：见 §2.6.6——很多论文不能展示抽取图，卡片必须在"无图"时依然好看（排版封面）。
- **scroll-snap 流的"当前卡"检测（核验补充）**：`scrollsnapchange`/`scrollsnapchanging` 事件仅 Chrome 129+ 支持，Safari 与 Firefox 均未实现；`scrollend` 为 Chrome 114+、Firefox 109+、Safari 26.2+；CSS 滚动驱动动画 `animation-timeline` 为 Chrome 115+、Safari 26+，Firefox 仅预览版 [R108]。因此映射 C（纵向 scroll-snap 流）的曝光/停留埋点应以 IntersectionObserver 为主、`scrollend` 为辅，不能依赖 snap 事件；与滚动进度联动的视觉效果可用滚动驱动动画并为 Firefox 保留静态降级。

#### 2.4.4 低端机与降级阶梯

- 探测：`navigator.deviceMemory`（仅 Chromium、HTTPS、为防指纹而取近似 2 的幂）[R73]；更可靠的是运行时采样前 N 次拖拽的帧间隔（设计建议）。
- 降级阶梯（设计建议）：①叠层 3→2 张 → ②关闭卡片阴影与背景模糊 → ③关闭旋转、只平移 → ④图片降一档 → ⑤全部改为淡入淡出（等同 Reduce Motion）。
- `prefers-reduced-motion` 全平台可用（约 96.5%）[R71]；RN `AccessibilityInfo.isReduceMotionEnabled()` 与 `reduceMotionChanged` 事件 [R81]；SwiftUI `accessibilityReduceMotion` [R67]；Reanimated `ReduceMotion.System` 为 `withSpring` 默认 [R54]；Flutter `MediaQuery.disableAnimationsOf`。

### 2.5 可访问性与容错（⑤）

#### 2.5.1 规范映射

| 规范 | 要求（原文意译） | 本设计落点 | 证据 |
|---|---|---|---|
| WCAG 2.2 SC 2.5.1 Pointer Gestures（A） | 路径型手势（滑动）的功能必须能用单指针、非路径方式完成 | 每个滑动都有按钮：↺ ✕ ☆ ♥ + "详情"；长按菜单同样有 ⋯ 按钮 | [R80] |
| SC 2.5.7 Dragging Movements（AA，2.2 新增） | 拖拽功能必须能用单指针不拖拽完成 | 同上；详情 Sheet 除下拉外有关闭按钮 | [R80] |
| SC 2.1.1 Keyboard（A） | 全部功能可键盘操作 | §2.9.3 键盘映射 | [R80] |
| SC 2.5.8 Target Size（AA） | 目标至少 24×24 CSS px（或满足间距例外） | 主按钮 56pt、次按钮 44pt；HIG iOS 默认 44×44pt、最小 28×28pt | [R80][R65] |
| SC 2.3.3 Animation from Interactions（AAA） | 交互触发的运动动画可被关闭 | Reduce Motion 全链路退化（§2.3.5） | [R80] |
| SC 4.1.3 Status Messages（AA） | 状态消息无需获得焦点即可被读屏获知 | "已标记不感兴趣·撤销"用 `aria-live="polite"` | [R80] |
| SC 2.2.2 Pause, Stop, Hide（A） | 自动开始且 >5s 的移动内容须可暂停 | 不做自动轮播；朗读（若有）可暂停 | [R80] |
| HIG | 提供手势替代；支持 Reduce Motion；为 VoiceOver 描述界面 | 读屏自定义动作："喜欢/不感兴趣/收藏/详情/撤销" | [R65] |
| React Native | `accessibilityActions` + `onAccessibilityAction` 支持标准与自定义动作 | 卡片注册 5 个自定义动作 | [R81] |

#### 2.5.2 非手势替代与可发现性

- **可见按钮是主通道，手势是快捷方式**：NN/g 指出滑动的可发现性低于其他操作方式、同一手势多义会增加学习与记忆负担，应提供可见线索与非手势替代 [R12]；HIG 同样要求自定义手势可发现、易执行、与其他手势区分，且不能是完成重要操作的唯一途径 [R62]。
- **首次引导**：抖音网页首次进入即用引导浮层说明"滚轮/↑↓键/屏幕按钮"三种等价操作（实测 B）；papr 用常驻图例说明四个方向（[R34]，但四向二维编码过于复杂，属反例）。建议：首次 3 张卡在拖拽时显示方向标签与半透明箭头提示，之后仅在拖拽时显示标签。
- **键盘分拣**：ASReview 用单键 `r`/`i`/`n` 完成相关/不相关/笔记 [R39]；抖音网页用 ↑↓ 切换（实测 B）。桌面研究者是重度用户，键盘分拣应是一等公民（§2.9.3）。

#### 2.5.3 误触撤销

- **撤销优于确认**：确认弹窗会被习惯化地忽略，稳健的撤销才是解法（Raskin，A List Apart，2007-07-21）[R83]；NN/g 对滑动操作同样建议"确认或提供便捷撤销" [R12]。
- **Tinder 反例**：Tinder 将 "Unlimited Rewinds" 作为 Plus 订阅权益（Gold/Platinum 包含之；页脚注称 Rewinds 可能在部分市场以测试形式提供）[R16]——对论文分拣而言撤销是纠错刚需，应免费且不限次。
- **实现语义**：撤销 = 追加一条"撤回"事件（引用被撤回事件 id），而非删除历史；推荐侧据此回滚该信号（设计建议，见 §2.9.6）。
- **撤销入口**：↓ 下滑（与抖音"下滑回上一条"的心智一致）、↺ 按钮、`Z`/`↑` 键、提交后 4–5 秒的 toast 按钮（toast 时长为设计值）。

### 2.6 论文卡片信息架构（⑥）

#### 2.6.1 证据：研究者用什么做判断

- Scholar Inbox 卡片放**标题、摘要、作者、venue + 前五张图表**，并以色彩编码相关度 [R17]；
- TLDR 生成（Cachola 等，Findings of EMNLP 2020）把"极端压缩的一句话摘要"作为科研文献的新摘要形式，SciTLDR 含 3.2K 论文的 5.4K 条 TLDR（作者写与专家写两类）[R91]；
- PaperTok 每张卡回答"是否经评审""能否读到"，缺数据就不显示 [R38]；
- 社区反馈：手机上只看摘要、要求 AI 可关闭、担心 AI 取代作者摘要 [R28]。

#### 2.6.2 卡片字段优先级（分拣卡正面）

| 优先级 | 字段 | 形态 | 数据来源（v1 已有/需新增） | 合规/可信注意 |
|---|---|---|---|---|
| P0 | 标题 | 衬线，≤3 行，超出省略 | arXiv/OpenAlex/Crossref 元数据 | arXiv 描述性元数据（标题/摘要/作者/标识/分类）为 CC0 [R93] |
| P0 | AI TL;DR | ≤2 行，带 "AI" 角标，可全局关闭 | 由摘要生成（自有模型）；S2 Graph API 的 `tldr` 字段（`{model, text}`，模型版本如 `tldr@v2.0.0`，源自 SciTLDR）可作参考——字段存在性经 swagger 核验，实际取值因 API 429 限流未取回，展示许可需按 S2 API 许可另核（⚠）[R113] | 永不替代作者摘要；出版社摘要的版权状态因源而异（⚠ 需法务/来源调研确认） |
| P0 | venue · 年份 · 新鲜度 | 等宽小字元数据行（如 `cs.CL · 2d · arXiv`） | VenueSpec/OpenAlex `primary_location` | — |
| P0 | 评审状态 | 徽标：预印本 / 已发表（venue） | 来源类型 + 版本（OpenAlex `version`） | 缺失则不显示 |
| P0 | 开放获取状态 | 四态徽标：可读（OA）/ OA 版本（仓储）/ 需订阅（用你的凭证）/ 不显示（未知） | OpenAlex `open_access.oa_status`（取值 diamond/gold/green/hybrid/bronze/closed）+ `best_oa_location.license` [R94]；"用你的凭证"由用户私有凭证可达性计算 | 可达性判断**按用户私有计算，不共享** |
| P0 | why-this | 1 行 + ⓘ，如"因为你收藏了《…》""你关注的主题 · RAG""探索推荐" | 推荐服务返回的 reason code（§2.9.6） | 探索性推荐须如实标注 |
| P1 | 关键图 | 16:9 区域，≤卡高 38%；无许可则**排版封面** | CC 许可论文的抽取图（Scholar Inbox 用 papermage [R17]） | 见 §2.6.6 |
| P1 | 作者 · 机构 | "第一作者 等 · 机构"，1 行 | OpenAlex `authorships` | — |
| P1 | 主题标签 | ≤3 个，单行横滑 | OpenAlex topics / arXiv 分类 / 用户订阅 DSL 命中项 | PaperTok 教训：标签定高单行 [R38] |
| P2 | 引用数、代码/数据链接 | 仅详情页 | OpenAlex `cited_by_count`；HF 论文-模型关联 [R20] | 分拣卡不放社交计数（§3 启示 22） |

"排版封面"：用领域色（数据驱动配色，同 PaperTok [R38]）+ 标题大字 + venue 生成封面图——小红书网页上大量文字排版封面同样能承担封面职能（实测 B）。WikiTok 作者后来直接丢弃无缩略图条目 [R35]，论文场景不能这样做，所以排版封面是必需品。

#### 2.6.3 详情页层级

| 层级 | 载体 | 内容顺序 | 交互 |
|---|---|---|---|
| L0 卡片 | Deck/网格 | §2.6.2 | 滑动决策；单击进入 L1 |
| L1 详情 Sheet | 底部抽屉（可下拉关闭，snap 到 60%/95%） | 标题 → 作者（可展开）/venue/年份/徽标 → **作者摘要（全文）** → AI TL;DR（折叠、带标识）→ 图集（仅许可允许时，横滑）→ why-this 详解（2–3 条）→ 相关论文 3 张小卡 → 私人笔记/评分（可选）→ 操作 | 下拉关闭回到原卡；图集横滑与 Sheet 纵滑轴锁 |
| L2 阅读器 | 全屏 | OA 源直链或经**用户自有凭证**取回的全文 | auth-gated 内容只存该用户私有空间，不进入共享缓存（合规红线） |

#### 2.6.4 评分/点赞/收藏/评论的极简化

| 证据 | 结论 | 证据 |
|---|---|---|
| YouTube 2009-09-22：星级评分几乎"全有或全无"，绝大多数视频是五星，官方自问 thumbs up/down 是否更有效 | 5 星粒度在低成本浏览场景信息量低 | [R84] |
| Netflix 2017-04-05：测试中以 thumbs 替代星级，评分活动增加 200% | 二元评分显著提高反馈量 | [R85] |
| S2 Research Feeds：Library 收藏 = 正、"not relevant" = 负；5 正 + 3 负起步 | 收藏本身就是最强正信号 | [R27] |
| Scholar Inbox：👍/👎 + 主动学习挑选待评论文 | 二元 + 主动挑样本足以训练个人模型 | [R17] |
| 抖音："不感兴趣"是强负反馈，有独立打分模型；另有屏蔽词 | 负反馈要有独立入口与"原因/屏蔽"扩展 | [R06] |
| papr 四向 2×2 | 多维度编码到方向 → 需常驻图例，学习成本高 | [R34] |

**方案（信号阶梯，从轻到重）**：隐式（停留、展开、打开详情）→ ↑ 中性跳过 → ←/→ 二元决策 → ☆ 收藏（最强正）→ 长按/详情内：不感兴趣原因（主题/作者/来源/已读过）、屏蔽词、1–5 星精评（可选）、私人笔记 → 公开评论（二期，详情页内）。默认界面只露出 4 个按钮（↺ ✕ ☆ ♥）。

#### 2.6.5 why-this 与用户控制

- TikTok 2022-12-20 在分享面板加入 "Why this video"，把推荐原因翻译成易懂条目 [R86]。
- CAC《互联网信息服务算法推荐管理规定》（2022-03-01 施行）：第十六条要求以显著方式告知并公示基本原理；第十七条要求提供不针对个人特征的选项或便捷关闭算法推荐，并提供选择或删除用户标签的功能；第十二条鼓励去重、打散与提升可解释性 [R88]。
- EU DSA：第 27 条第 1、2 款要求在条款中以易懂语言说明推荐系统主要参数（含"为何向你推荐"的最重要标准及其权重理由）及修改选项；**第 27 条第 3 款**（正文而非序言）要求在有多个选项时提供可随时切换偏好选项的功能，且该功能须能在信息被排序呈现的界面区域**直接、便捷访问**；第 38 条要求超大平台/搜索引擎为每个推荐系统至少提供一个不基于画像的选项 [R87]（核验修正：原文把"界面直接访问"归于序言）。
- **平台先例（核验补充）**：TikTok（新闻稿 2025-06-03）提供 "Manage Topics" 主题滑杆（调高/调低而非彻底屏蔽）、Smart Keyword Filters（最多 200 个关键词，AI 扩展同义/俚语）、**长按 → "Not interested"**、以及一键重置 For You 推荐 [R109]；Instagram "Your Algorithm"（2025-12-10 于 Reels 推出，2026-04-15 扩展至 Explore，2026-06-10 覆盖 Feed/Reels/Explore 统一生效）让用户查看系统推断的兴趣主题、增加新主题并调多/调少 [R110]。二者可直接作为"兴趣标签可删/可调 + 重置"设置页的交互参照。
- 解释的目标可参考 Tintarev & Masthoff 的综述（透明、可审查、可信、有效、说服、效率、满意七项）[R90]——七项名称经 Tintarev 同年 RecSys'07 博士论坛论文 Table 1（Transparency / Scrutability / Trustworthiness / Effectiveness / Persuasiveness / Efficiency / Satisfaction，并注明详见该综述）核验 [R115]；协同过滤解释的经典研究见 Herlocker 等 [R89]。
- 先例：Papel 提供 "Latest" 时间序切换 [R28]。

落点：卡片 1 行 why-this（点开看 2–3 条原因）；设置页"我的兴趣标签（可删）""屏蔽词""个性化推荐开关（关闭后按时间/来源排序）"；探索性推荐在卡片上标"探索"。

#### 2.6.6 版权与多用户合规约束（对卡片内容的硬约束）

| 约束 | 事实 | 对 UI 的要求 | 证据 |
|---|---|---|---|
| arXiv 许可 | 可选 CC BY 4.0、CC BY-SA 4.0、CC BY-NC-SA 4.0、CC BY-NC-ND 4.0、CC0、arXiv.org perpetual non-exclusive license 1.0；后者只授予 arXiv 分发权并限制他人任何形式的再利用 | 仅对 CC 许可（且满足署名/非商用/禁演绎条件）的论文展示抽取图；BY-NC-ND 的"裁图"是否构成演绎 ⚠ 需法务 | [R92] |
| arXiv API 条款 | 描述性元数据 CC0 可自由存储/共享；**不得从自有服务器存储并提供 e-print 内容（PDF、源文件等）**，除非获版权人许可或许可证允许；鼓励链接到摘要页；legacy APIs（含 OAI-PMH、RSS 与 arXiv API）每 3 秒不超过 1 次请求、同一时间单连接 | 默认链接到 arXiv 摘要/全文页；不在平台缓存并分发 PDF/图 | [R93] |
| OpenAlex 许可字段常缺 | 示例：arXiv:2504.08385 的 `best_oa_location.license` 为 null、`oa_status` 为 green | 许可未知 ⇒ 视为不可展示图（保守默认） | [R94] |
| auth-gated 全文 | 项目红线：只能用各用户自有凭证取回并私有存放 | L2 阅读器与任何派生物（缩略图、抽取图、全文索引片段）不跨用户 | 任务书合规红线 |

### 2.7 技术栈选型（⑦）

#### 2.7.1 版本与关键事实（2026-09-26）

| 生态 | 当前版本（发布日） | 关键事实 | 证据 |
|---|---|---|---|
| React / Next.js | react 19.3.0（2026-09-09）；next 16.3.6（2026-09-22） | `<ViewTransition>` 在 19.3 稳定 | [R78][R95] |
| Motion（原 Framer Motion） | motion 13.4.4（2026-09-25）；npm `motion` 约 2,407 万/周、`framer-motion` 约 5,198 万/周（2026-09-18～24 窗口复查值，核验修正） | drag/spring/`layoutId`/`AnimatePresence`/`reducedMotion` | [R46][R47][R95] |
| Base UI | @base-ui/react 1.8.0（2026-09-04），约 1,570 万/周（核验修正） | 含 Drawer（swipe-to-dismiss、snap points），PaperTok 在用 | [R38][R95][R100] |
| Expo / React Native | expo 57.0.25（2026-09-24）；react-native 0.87.1（2026-08-26） | — | [R95] |
| Reanimated / Worklets / RNGH | 4.7.0（2026-09-18）/ 0.13.0 / 3.3.0（2026-09-11） | Reanimated 4 仅支持新架构及最近三个 RN 版本；共享元素转场仍为实验特性 | [R53][R79][R95][R99] |
| Flutter | 3.47.5（2026-09-18，Dart 3.13.4） | Impeller 默认（iOS 唯一渲染器；Android API 29+ 默认）；`Hero` 共享元素 | [R96][R97] |
| SwiftUI | iOS 17：`scrollTargetBehavior(.paging)`、`sensoryFeedback`；iOS 18：`.navigationTransition(.zoom)` | — | [R67] |
| Lynx（字节跳动） | lynx **4.1.0**（2026-09-07，GitHub 标记 latest；4.0.0 于 2026-07-20 发布，4.0.x 分支最新补丁 4.0.3 为 2026-09-11——核验修正：原文把 4.0.3 当作最新版）；@lynx-js/react 0.126.2（2026-09-24） | 2025-03-05 开源；双线程（主线程 PrimJS + 后台运行时）；TikTok 的 Search 面板、TikTok Studio、Shop、LIVE 等使用（未声明用于主推荐流） | [R98][R95] |
| Capacitor | @capacitor/core 8.5.2；@capacitor/haptics 8.0.2 | 可把 Web 代码包成原生壳并调用触感 | [R95] |
| iOS PWA | iOS/iPadOS 16.4 起（WebKit 于 2023-02-16 随 beta 公布）Home Screen web app 支持 Web Push 与 Badging；iOS 26 起**任何网站加到主屏幕默认以 web app 打开** | 安装门槛下降；但渲染节拍与触感限制仍在（§2.4.2、§2.3.7） | [R69][R70] |

#### 2.7.2 方案对比

| 方案 | 开发成本 | 跟手动画品质上限 | 触感 | 共享元素 | 跨端 | 主要风险 |
|---|---|---|---|---|---|---|
| **PWA**：React 19.3 + Motion 13（或 use-gesture + react-spring）+ Base UI + scroll-snap | 最低：一套代码覆盖桌面与移动；与 Demo 同栈 | Android 视设备而定（高刷下 rAF 节拍 ⚠ 未核验）；iPhone 上 JS 驱动动画约 60Hz（[R68]，⚠ 推断未实测）；需严守 transform/opacity | iOS 无；Android `vibrate` 可用 [R71] | View Transitions + `<ViewTransition>` / `layoutId` [R71][R78] | 最佳（桌面键盘分拣 + 移动） | iOS 帧率与触感；浏览器边缘手势；低端 Android 主线程压力 |
| **Expo/RN**：SDK 57 + Reanimated 4 + RNGH 3 + FlashList | 中：移动双端一套；桌面体验需另做（RN-web 可用但密集阅读体验一般，⚠ 判断） | 高：UI 线程 worklets；120Hz 需 plist 键 [R66]（Expo 模板默认已设 [R107]） | expo-haptics [R82] | Reanimated SET 实验中 [R79]，常用手写容器变形替代 | iOS+Android（+Web 次选） | 新架构/升级节奏；共享元素不成熟 |
| **Flutter 3.47** | 中 | 高且一致（Impeller）[R97] | 有：`HapticFeedback.lightImpact/mediumImpact/heavyImpact/selectionClick/vibrate`（核验）[R112] | `Hero` [R97] | 移动/桌面/Web | Web 端文本密集/可访问性/SEO 偏弱（⚠ 判断）；与 Python + TS 团队技能不匹配 |
| **SwiftUI 原生** | 高（仅 iOS） | 最高 | 原生 | `.zoom`、`matchedGeometryEffect` [R67] | 仅 Apple | Android 需另写 Compose |
| **Compose Multiplatform** | 中 | 高（Android 原生） | 有 | — | Android/桌面/Web/iOS（iOS 自 CMP 1.8.0〔2025-05〕起 Stable，核验）[R111] | 生态较新（WikWok 可参考 [R36]） |
| **Lynx 4.x** | 中高（生态早期） | 高（双线程）[R98] | ⚠ 未核验 | ⚠ 未核验 | iOS/Android/Web | 组件/文档/社区仍在成长 |
| **Capacitor 壳 + PWA** | 低（在 PWA 之上） | 同 PWA（仍为 WKWebView）[R68] | 有 [R95] | 同 PWA | 同 PWA + 应用商店 | 只补触感/分发，不补帧率 |

### 2.8 开源 UI 组件清单（⑧）

数据：`gh api`（star/许可/最近推送）、npm 周下载（2026-09-18 至 09-24）、pub.dev（2026-09-26）[R95][R101]。
（核验修正：2026-09-26 以 `api.npmjs.org/downloads/point/2026-09-18:2026-09-24/<pkg>` 复查同一窗口，调研员原值系统性偏低约 17%（按日数据看，疑为抓取时某日数据尚未入账），下表周下载已全部按复查值更正；star 复查仅有个位数漂移，保留原值。）

**Web**

| 仓库 / 包 | ★ | License | 最近推送 | 周下载 | 能力与状态 | 建议 |
|---|---|---|---|---|---|---|
| motiondivision/motion（`motion`/`framer-motion`） | 33,736 | MIT | 2026-09-25 | 2,407 万 / 5,198 万 | drag、spring、inertia、`layoutId`、`AnimatePresence`、`reducedMotion` | **首选** |
| pmndrs/react-spring（`@react-spring/web`） | 29,161 | MIT | 2026-09-26 | 595 万 | 物理弹簧；官方 cards-stack 示例 | 备选 |
| pmndrs/use-gesture（`@use-gesture/react`） | 9,622 | MIT | **2024-07-15** | 766 万 | 手势状态机（速度、方向、轴） | 可用但维护放缓 |
| 3DJakob/react-tinder-card | 405 | MIT | **2024-06-21** | 0.9 万 | v1.6.4，依赖 react-spring 9；`swipeRequirementType`、`preventSwipe`、`restoreCard` | 不建议（停滞；自研 Deck 约 200 行即可） |
| nolimits4web/swiper | 41,902 | MIT | 2026-09-14 | 473 万 | v14.2.0；`effect-cards`、`effect-creative`、`a11y`、`keyboard`、`virtual`、`zoom` 模块 | 用于详情图集 |
| davidjerleke/embla-carousel（`embla-carousel-react`） | 8,427 | MIT | 2026-09-18 | 4,014 万 | 轻量轮播 | 图集备选 |
| mui/base-ui（`@base-ui/react`） | 11,000 | MIT | 2026-09-25 | 1,570 万 | Drawer（swipe-to-dismiss、snap points）、Dialog 等无样式组件 | **详情 Sheet 首选** |
| emilkowalski/vaul | 8,623 | MIT | 2025-10-03 | 4,399 万 | Drawer；README 声明**不再维护** | 不建议新用 |
| TanStack/virtual（`@tanstack/react-virtual`） | 7,122 | MIT | 2026-09-21 | 2,683 万 | 无头虚拟化（列表/网格） | 瀑布流/列表 |
| jaredLunde/masonic | 1,414 | MIT | 2026-01-31 | 9.2 万 | 虚拟化 masonry | 瀑布流备选 |
| petyosi/react-virtuoso | 6,461 | MIT（npm） | 2026-09-22 | 386 万 | 虚拟列表 | 紧凑列表模式 |
| hammerjs/hammer.js | 24,337 | MIT | 2026-01-04 | — | 老牌多点手势 | 仅参考 |
| gajus/swing | 2,630 | NOASSERTION | 2023-09-22 | — | 早期 Tinder 卡 | 不建议 |

**React Native**

| 仓库 / 包 | ★ | License | 最近推送 | 周下载 | 能力与状态 | 建议 |
|---|---|---|---|---|---|---|
| software-mansion/react-native-reanimated | 11,010 | MIT | 2026-09-25 | 938 万 | 4.7.0；UI 线程动画；默认弹簧 ζ=1 | **首选** |
| software-mansion/react-native-gesture-handler | 6,789 | MIT | 2026-09-25 | 904 万 | 3.3.0；`activeOffsetX`/`failOffsetY` 轴锁 | **首选** |
| Shopify/flash-list | 7,238 | MIT | 2026-09-15 | 271 万 | 高性能列表（masonry 能力 ⚠ 本轮未核） | 网格/列表 |
| LegendApp/legend-list（`@legendapp/list`） | 3,414 | MIT | 2026-09-21 | 67 万 | 高性能列表（RN + React） | 备选 |
| callstack/react-native-pager-view | 3,364 | MIT | 2026-09-25 | 146 万 | 原生分页（纵向沉浸模式） | 映射 C 实验 |
| dohooo/react-native-reanimated-carousel | 3,430 | MIT | 2026-08-08 | 62 万 | 轮播 | 图集 |
| webraptor/react-native-deck-swiper | 178 | ISC | 2025-08-12 | 2.1 万 | v2.0.19；基于 PanResponder + 旧 `Animated` API | 不建议（非 UI 线程） |
| Skipperlla/rn-swiper-list | 311 | MIT | 2026-06-06 | 0.5 万 | 基于 Reanimated 4 + worklets；`swipeBack`、`restoredSwipes`、翻面 | 参考实现 |

**Flutter / 跨平台 / 参考实现**

| 仓库 / 包 | ★ / pub | License | 最近 | 说明 |
|---|---|---|---|---|
| ricardodalarme/flutter_card_swiper | 205★；pub 708 likes、30 日约 6 万下载 | MIT | 7.2.0（2025-11-02）；推送 2026-08-20 | `maxAngle` 30、后卡 `scale` 0.9、200ms、undo [R52] |
| appinio_swiper（appinioGmbH/flutter_packages） | 213★（整仓）；pub 468 likes | — | 2.1.1（2024-04-15） | 停滞 |
| lynx-family/lynx | 15,133 | Apache-2.0 | 2026-09-26 | latest release 4.1.0（2026-09-07）；观望 [R98] |
| nathangitter/fluid-interfaces | 2,593 | Apache-2.0 | 2018-12-16 | WWDC18 手势复刻（投影、弹簧）[R42] |
| scenee/FloatingPanel | 5,818 | MIT | 2026-09-24 | 投影公式注释引 WWDC18 [R41] |
| jtrivedi/Wave | 2,395 | MIT | 2026-03-25 | 弹簧 + 投影工具（默认 0.998）[R43] |

### 2.9 交互规范建议（输出）

#### 2.9.1 信息架构总览

```text
底部导航（3 项，界面极简）:
  [今日]  分拣 Deck（有限批次，默认首页）
  [探索]  双列瀑布流（主题/热门/相似），点卡 → 详情 Sheet
  [我的]  收藏库（双列/紧凑列表切换）· 兴趣标签 · 设置
不设：发布、私信、直播、积分、测验等社交/游戏化入口（"界面简单，不要多余功能"）
```

#### 2.9.2 手势映射

**推荐映射 A：抖音纵轴 × Tinder 横轴（默认）**

| 输入 | 动作 | 语义 / 信号 | 拖拽中视觉 | 等价按钮 | 等价键 |
|---|---|---|---|---|---|
| → 右滑 | 喜欢（想读） | 显式正反馈；进入"喜欢/待读" | 右倾 + 右上角"喜欢"标签淡入 | ♥ | `→` / `L` |
| ← 左滑 | 不感兴趣 | 显式负反馈；toast 内可补原因 | 左倾 + "不感兴趣"标签 | ✕ | `←` / `H` |
| ↑ 上滑 | 下一篇（稍后再看） | **中性跳过**，不计负反馈，可在后续批次回流 | 上移，次卡升位 | —（可选 ⤓ 按钮） | `↓` / `J` / `Space` |
| ↓ 下滑 | 上一篇 = 撤销上一决策 | 追加撤回事件 | 上一张从离开方向落回 | ↺ | `↑` / `K` / `Z` |
| 单击 | 打开详情 Sheet | 隐式强兴趣 | 共享元素放大 | "详情"（整卡可点） | `Enter` / `O` |
| 长按 ≥400ms | 快捷菜单 | 收藏到…/不感兴趣原因/屏蔽词/评分/复制引用/分享 | 轻触感 + 菜单 | ⋯ | `.` |
| ☆ 按钮 | 收藏（默认收藏夹，可改） | 最强正反馈 | 星形填充 | ☆ | `S` |
| 详情内下拉 | 关闭详情 | — | 跟手缩回原卡 | ✕ | `Esc` |

说明：键盘 `↓` 对应"下一篇"与抖音网页一致（按下方向键向下翻），触屏 ↑ 上滑同义；`J/K` 为常见的上下条目快捷键约定（⚠ 未在本轮逐一核验各产品）。长按阈值取 Android 默认 400ms [R59]。

**备选映射 B：纯 Tinder（↑ = 收藏）**——优点：四方向都有语义，收藏一步完成。缺点：国内用户"上滑看下一条"的肌肉记忆会造成大量**误收藏**（⚠ 推断，需 Demo A/B 验证）；没有中性跳过，逼迫二元决策，放大拒绝心态 [R15]。不推荐作为默认。

**实验映射 C：纯抖音纵向流（arxivtok/PaperTok/Papel 同类）**——↑/↓ 切换、侧边动作列（喜欢/收藏/评论/分享）、单击看详情；Web 端可直接用 CSS scroll-snap 实现（PaperTok 做法 [R38]）。缺点：滑走≠不感兴趣，信号含义模糊；侧边动作列占据阅读宽度。作为"沉浸浏览"实验入口保留。

#### 2.9.3 桌面键盘映射（分拣是一等公民）

| 键 | 动作 | 键 | 动作 |
|---|---|---|---|
| `→` / `L` | 喜欢 | `Enter` / `O` | 打开详情 |
| `←` / `H` | 不感兴趣 | `Esc` | 关闭详情/菜单 |
| `↓` / `J` / `Space` | 下一篇（中性） | `Z` | 撤销 |
| `↑` / `K` | 上一篇（撤销） | `N` | 私人笔记（同 ASReview `n` [R39]） |
| `S` | 收藏 | `?` | 快捷键面板 |

桌面布局建议：中间 Deck + 右侧详情常驻窗格（宽屏不弹 Sheet），键盘提示条常驻底部。

#### 2.9.4 动效参数表（设计规格，Demo 中可调）

| 场景 | 类型 | 参数（Motion 写法） | 等效 ζ / T0 / 稳定 | 依据 |
|---|---|---|---|---|
| 跟手拖拽 | 直接映射 | `x = dx`；`rotate = clamp(dx/W·16°, ±12°)`；旋转原点底部中心 | — | 1:1 跟手 [R40]；比约会类（20–27°/W、上限 10–30°）更克制，照顾文字可读性（设计选择） |
| 方向标签 | 插值 | 进度 p = abs(dx)/(0.35W)；`opacity = smoothstep(0.3, 1.0, p)` | — | deck-swiper 标签透明度映射 [R50] |
| 次卡跟随 | 插值 | `scale 0.95→1`、`y 10→0` 随 p | — | [R50][R52] |
| 未过阈值回弹 | spring | stiffness 500 / damping 36 / mass 1 | 0.80 / 281ms / 170ms，超调 1.4% | WWDC18 有动量用 ~80% 阻尼 [R40] |
| 提交飞出 | 保速 | 初速 = 释放速度；时长 = 剩余距离 / max(abs(v), 1000pt/s)，夹 120–280ms；旋转续至 ±12° | — | react-tinder-card 距离/速度 [R49]；ItemTouchHelper 250ms [R58]；flutter_card_swiper 200ms [R52] |
| 次卡升位 | spring | 600 / 49 | 1.00 / 257ms / 239ms | 与飞出并行；Reanimated 4 默认同为 ζ=1 [R53] |
| 撤销回位 | spring | 400 / 32 | 0.80 / 314ms / 188ms | [R40] |
| 详情展开 | spring 或缓动 | 260 / 29；或 `cubic-bezier(0.05,0.7,0.1,1)` 400ms | 0.90 / 390ms / 291ms | M3 Emphasized Decelerate + Medium4 [R56] |
| 详情下拉关闭 | 跟手 + 投影 | 投影 `r=0.998`；投影越过 30% 高或 v ≥ 800pt/s 则关闭，否则 spring 700/53 回位 | 1.00 / 237ms / 222ms | 投影 [R41]；速度阈值同 §2.3.4 |
| 按钮按压 | spring | `scale 0.92`，700 / 40 | 0.76 / 237ms / 214ms | 设计值 |
| 状态提示（toast） | 缓动 | 进 150ms（Emphasized Decelerate）/ 出 100ms（Emphasized Accelerate） | — | M3 Short3/Short2 [R56] |
| Reduce Motion | 替换 | 所有位移/旋转/缩放 → opacity 150ms | — | [R47][R64][R80] |

#### 2.9.5 卡片线框（手机竖屏 390×844pt 示意；框内用英文占位避免等宽错位）

**(a) 分拣卡正面**

```text
+----------------------------------------+
| TODAY 12/30                  [gear]    |   顶栏：批次进度 + 设置
|  +----------------------------------+  |
|  | === cs.CL . 2d . arXiv           |  |   领域色条 + 分类 + 新鲜度 + 来源（等宽）
|  |                                  |  |
|  | [TITLE, serif, max 3 lines]      |  |   P0 标题
|  |                                  |  |
|  | (AI) [TL;DR, max 2 lines]        |  |   P0 AI 摘要（角标、可关闭）
|  | +------------------------------+ |  |
|  | | [KEY FIGURE / TYPO COVER]    | |  |   P1 关键图（许可门控）或排版封面
|  | | 16:9, <= 38% card height     | |  |
|  | +------------------------------+ |  |
|  | First Author et al. . Inst.      |  |   P1 作者·机构（1 行）
|  | [Preprint] [OA] [ACL 2026]       |  |   P0 评审状态 / 开放获取 / venue
|  | #tag1  #tag2  #tag3  ->          |  |   P1 标签（单行横滑）
|  | * Because you saved "..."   (i)  |  |   P0 why-this（1 行）
|  +----------------------------------+  |
|    back cards peek 8-10pt below        |   叠层：次卡 0.95 / 第三张 0.90
|                                        |
|     ( <- )   ( X )   ( * )   ( <3 )    |   ↺ 撤销 / ✕ 不感兴趣 / ☆ 收藏 / ♥ 喜欢
|      44pt     56pt    56pt    56pt     |   主按钮 56pt，次按钮 44pt
|  [Today]      [Explore]      [Me]      |   底部导航 3 项
+----------------------------------------+
```

**(b) 详情 Sheet（L1）**

```text
+----------------------------------------+
|              ------  (grabber)         |   下拉关闭；snap 60% / 95%
| [TITLE]                                |
| Authors (tap to expand) . Venue . Year |
| [Preprint] [OA: green] [CC BY 4.0]     |   许可徽标决定能否显示图
| ABSTRACT (author-written, full text)   |   作者摘要优先
| (AI) TL;DR  [collapsed]                |   AI 内容折叠且标注
| [FIG 1] [FIG 2] [FIG 3]  <- swipe ->   |   仅许可允许时出现
| WHY THIS: 2-3 reasons                  |
| RELATED: [mini] [mini] [mini]          |
| NOTE (private) . RATE 1-5 (optional)   |
| [Read (OA)] [Read via my library]      |   OA 直链 / 用户自有凭证
| [Cite] [Share] [Not interested...]     |
+----------------------------------------+
```

**(c) 探索/收藏库：双列瀑布流小卡**

```text
+---------------+ +---------------+
| [FIG 4:3]     | | [TYPO COVER]  |   有许可图 / 排版封面（领域色+标题）
|               | |  field color  |
+---------------+ +---------------+
| Title 2 lines | | Title 2 lines |
| Venue.Yr   OA | | Venue.Yr   *  |   不放点赞数等社交计数
+---------------+ +---------------+
```

#### 2.9.6 UI 事件与 why-this 数据契约（交给推荐/数据模型设计对齐）

```text
// 设计伪代码（非实现）：前端上报事件（全部带 user_id、paper_id、session_id、surface、position、ts）
impression        { visible_ms }                          // 卡片可见时长（dwell），对应 X 的 dwell/not dwelled [R08]
expand_detail     { via: tap | swipe_up_sheet | key }
figure_view       { index }
swipe_decision    { dir: like | not_interested | next_neutral, dx, vx, decision_latency_ms, input: touch | button | key }
save              { collection_id }
like / unlike
not_interested    { reason?: topic | author | source | already_read, block_term? }
undo              { retracts_event_id }                   // 撤销 = 追加撤回事件
rate              { stars: 1..5 }                         // 可选
note_create       { private: true }
open_fulltext     { source: oa_link | user_credential }   // 用户凭证路径只记来源类型，不记凭证
ai_summary_toggle { enabled }
batch_end         { shown, decided, liked, saved, duration_ms }

// 推荐服务 → 前端：why-this reason code
reason { type: similar_to_saved | followed_topic | followed_author | trending_in_field | exploration | recency,
         ref?: paper_id | topic_id | author_id, text_zh }
```

### 2.10 技术栈推荐（输出）

1. **v2.0：Web-first（PWA）**——React 19.3 + Motion 13（Deck 拖拽/弹簧/`AnimatePresence`）+ React `<ViewTransition>`/View Transitions API（卡片→详情）+ Base UI Drawer（详情 Sheet）+ CSS scroll-snap（映射 C 实验模式）+ TanStack Virtual/masonic（瀑布流）。理由：一套代码同时服务**桌面键盘分拣**（研究者主力场景）与移动端；与设计阶段 Demo 同栈；React 19.3 让共享元素转场进入稳定 API [R78]；iOS 26 起主屏幕安装默认以 web app 打开 [R70]。框架选 Next.js 或 Vite SPA 均可（本文不做路由/SSR 决策）。
2. **v2.x：原生移动客户端（条件触发）**——当移动端留存/分拣占比达到阈值（由度量决定）时，上 Expo SDK 57 + Reanimated 4.7 + RNGH 3.3 + FlashList + expo-haptics：获得 UI 线程动画、120Hz（需 plist 键 [R66]）、原生触感 [R82]。与 Web 共享 TypeScript 领域模型、API client、设计 token 与事件契约；卡片组件**分别实现**，不强求 RN-web 共享 UI。
3. **过渡选项**：若 v2.0 阶段就需要应用商店分发与触感，可用 Capacitor 8 壳 + `@capacitor/haptics` [R95]，但渲染仍受 WKWebView 60fps 偏好约束 [R68]。
4. **不作为主线**：Flutter（团队技能与 Web 文本密集场景不匹配，⚠ 判断）、纯 SwiftUI（单平台）、Lynx（生态早期，TikTok 公开的使用面不含主推荐流 [R98]，列入观望）。
5. **组件取舍**：不用 react-tinder-card（2024-06 后停更）与 vaul（官方声明不再维护）；Deck 基于 Motion drag 自研（判定逻辑见 §2.3.4），便于实现投影、轴锁、边缘死区与撤销语义。

---

## 3. 对 v2 设计的启示

1. **三件套形态**：今日分拣 Deck（默认首页）+ 双列瀑布流（探索、收藏库）+ 详情 Sheet；纵向沉浸流仅作实验入口（§2.1.3、§2.9.2 映射 C）。
2. **默认手势映射 A**：→ 喜欢、← 不感兴趣、↑ 中性下一篇、↓ 上一篇=撤销、单击详情、长按菜单；Deck 上不绑定双击（§2.9.2）。
3. **中性跳过与负反馈分离**：↑ 不计负信号；"不感兴趣"支持原因与屏蔽词（对齐抖音"不感兴趣 + 屏蔽词"的双通道 [R06]）。专业筛选工具 Covidence（Yes/Maybe/No）与 Rayyan（Include/Maybe/Exclude，Maybe 独立成表）都把"不确定"做成一等选项，可作为"稍后再看"队列的先例（核验补充 [R104][R105]）。
4. **判定算法统一为"位移 + 速度 + 投影"**：`proj = d + v·0.1s`，横向 0.35W、纵向 0.2H、逃逸速度 800pt/s；10pt 轴锁；左右 24pt 边缘死区（§2.3.4）。
5. **动效采用 ζ≈0.8–1.0 的"现代默认"**，不用 ζ=0.5 的旧默认；具体见 §2.9.4 参数表；所有参数在 Demo 中做成可调面板。
6. **飞出与升位并行、总时长 ≤300ms**，下一张卡预挂载且图片已解码（§2.3.5、§2.4.3）。
7. **有限批次 + 结束态**：每日批次上限（建议 20–30 篇，⚠ 待 Demo 验证）与"今日已看完"页；会话后段的负反馈在建模时降权以对冲拒绝心态 [R15]（需推荐侧确认）。
8. **撤销免费、不限次、以撤回事件实现**（§2.5.3）。
9. **每个手势都有按钮与键盘等价**，读屏自定义动作齐全，满足 WCAG 2.2 AA（§2.5.1）。
10. **桌面键盘分拣是一等公民**（§2.9.3），宽屏用右侧详情窗格替代 Sheet。
11. **卡片 P0 字段固定为 6 项**（标题、AI TL;DR、venue·年份、评审状态、OA 状态、why-this），P1/P2 按 §2.6.2；分拣卡不放社交计数。
12. **AI 摘要三原则**：显式标注、全局可关、永不替代作者摘要（详情页作者摘要在前）（§2.2.4、§2.6.3）。
13. **关键图许可门控 + 排版封面兜底**：仅 CC 许可论文展示抽取图；许可未知即不展示；不缓存/不再分发 arXiv PDF 与图（§2.6.6）。
14. **OA 四态徽标按用户私有计算**："需订阅（用你的凭证）"只基于该用户自己的凭证可达性，结果不跨用户共享。
15. **why-this + 兴趣标签可删 + 个性化开关**写入产品需求（CAC 第16/17条 [R88]；DSA 第27/38条同向 [R87]）；设置入口应能从推荐流界面直达（DSA 第 27 条第 3 款），交互可参照 TikTok Manage Topics 与 Instagram "Your Algorithm"（核验补充 [R109][R110]）。
16. **首屏零门槛**：未登录可先刷一小批示例（公开 CC0 元数据），登录后置（§2.2.4）；冷启动提供"选 3–5 个主题/种子论文"与"评 5 篇相关 + 3 篇不相关"两条路径（S2 [R27]、Scholar Inbox [R17]）。
17. **性能预算**：DOM 中 3 张卡、只动 transform/opacity、INP p75 ≤ 200ms、提交到下一张可交互 ≤ 100ms（设计目标），并实现 5 级降级阶梯（§2.4）。
18. **Reduce Motion 全链路**：Web `prefers-reduced-motion` + Motion `reducedMotion="user"`；原生读取系统设置（§2.4.4）。
19. **触感只做补充且可关**；iOS PWA 无触感属已知限制（§2.3.7）。
20. **技术栈**：v2.0 Web-first（React 19.3 + Motion 13 + Base UI + View Transitions）；v2.x 条件触发 Expo/RN（§2.10）。
21. **事件契约先行**：§2.9.6 的事件与 reason code 作为前端—推荐服务接口，需在数据模型与推荐设计中落表/落 schema。
22. **弱化流行度**：分拣卡不显示点赞数；探索页可显示热度但须混入"探索"标注条目（HN 反馈 [R28]；抖音多样性实验结论：推送越多元长期活跃越高 [R06]）。
23. **社交功能分期**：v2.0 只做私人笔记与收藏；公开评论/点赞可见性放二期（alphaXiv 评论稀少的反馈为单人观点，⚠ 需市场调研侧数据佐证）。
24. **设计阶段 Demo 范围**：单页 Web Demo（真实 arXiv CC0 元数据 20–30 条 + 排版封面，避免图版权）；实现映射 A/B/C 切换、参数面板（阈值/弹簧）、Reduce Motion 开关、键盘分拣、撤销；用于录制视觉案例与内部 A/B。
25. **度量先定义**：分拣速度（卡/分）、撤销率、方向误判率（提交后 3s 内撤销）、后半段负反馈占比、详情打开率、收藏→阅读转化、会话长度与"今日已看完"到达率。

## 4. 未决问题与风险

1. **单卡决策耗时缺少实证**：未找到"研究者读 TL;DR/摘要做相关性判断需要几秒"的可靠研究（本轮检索未果）；批次大小（20–30）与卡片信息量是假设，需 Demo 实测。
2. **映射 A 的 ↑ 中性跳过是否会被滥用**，使显式标签变少；映射 B 的误收藏风险亦属推断；需 A/B。
3. **iOS PWA 帧率**：WebKit 默认 60fps 偏好 [R68] 对跟手拖拽的实际观感影响、scroll-snap 是否仍可 120Hz，均未真机测量（⚠ 推断）。
4. **触感缺失**：iOS PWA 无 Vibration API [R71]；是否足以驱动 v2.x 原生客户端，取决于度量。
5. **图片许可**：CC BY-NC-ND 下裁剪/缩放图是否构成演绎、平台是否算"商业"用途、出版社摘要能否展示与再生成摘要，需法务与来源调研确认（⚠）。
6. **AI 摘要准确性与作者接受度**：错误摘要会误导分拣；ACM DL 的 AI 摘要确曾因准确性与"与作者摘要重复"遭社区质疑并被迫加免责声明与反馈入口（CACM 2026-03-03 [R114]），细节见 §2.2.4。
7. **拒绝心态与疲劳**：约会场景的 27% 下降 [R15] 能否外推到论文分拣未知；会话位置偏置需在推荐建模中处理。
8. **手势可发现性**：即便有引导，用户仍可能忘记手势 [R12]；按钮必须长期保留。
9. **多用户隐私**：喜欢/收藏/评论的默认可见性、why-this 是否会泄露他人行为（例如"与你相似的研究者喜欢"类理由）需在数据模型与隐私策略中定义。
10. **监管细节**：CAC 规定第二十四条要求"具有舆论属性或者社会动员能力"的算法推荐服务提供者自提供服务之日起十个工作日内履行备案，第二十七条要求其开展安全评估（条款原文已核验 [R88]）；**本平台是否落入该范围属法律判断，仍 ⚠ 需法务确认**；面向欧盟用户时 DSA 义务随平台规模而变（第 38 条仅适用于超大平台/搜索引擎 [R87]）。
11. **组件维护风险**：use-gesture 自 2024-07 无推送；vaul 已声明不再维护；Reanimated 共享元素转场仍是实验特性 [R79]。
12. **跨文档 View Transitions 在 Firefox 仅部分支持** [R71]；若采用 MPA 需要降级方案。
13. **低端 Android 主线程压力**：JS 拖拽 + 大图解码可能掉帧，降级阶梯的触发阈值需实测。
14. **键盘约定**：`J/K`、`H/L` 与现有学术工具/浏览器扩展的冲突未评估（⚠）。
15. **中文排版**：中文标题/TL;DR 的行数与字号（CJK 字宽）会改变卡片高度分配，需在 Demo 中以真实中文翻译标题校准。

## 5. 参考来源

除另注外，访问/核验日期均为 **2026-09-26**。

| ID | 来源 | URL | 支撑的断言 |
|---|---|---|---|
| R01 | Eugene Wei, *Seeing Like an Algorithm*（2020-09） | https://www.eugenewei.com/blog/2020/9/18/seeing-like-an-algorithm | 全屏单条让用户对单条表态；无限 feed 算法看不到视线停留 |
| R02 | Eugene Wei, *TikTok and the Sorting Hat*（2020-08） | https://www.eugenewei.com/blog/2020/8/3/tiktok-and-the-sorting-hat | 短内容带来高单位时间训练数据量 |
| R03 | 流星桑（字节跳动社区 PM），《产品设计：单列还是双列，该如何抉择？》，人人都是产品经理，2022-07-01 | https://www.woshipm.com/pd/5508079.html | 单双列优劣、电商中具象/模糊意图分用单/双列 |
| R04 | 袁Peter，《为什么短视频难逃【单列沉浸式】的真香定律？》，人人都是产品经理，2021-01-11 | https://www.woshipm.com/operate/4332491.html | 单列降低消费成本；双列封面承担转化；双列广告 CTR 为内容的 1/5–1/10（文中引"快手 2019 报告"，⚠ 二手） |
| R05 | 人民网（转环球网），《快手8.0版本上线 品牌与产品全面升级》，2020-09-03 | http://finance.people.com.cn/n1/2020/0903/c1004-31848521.html | 快手 8.0 兼容双列点选与单列上下滑，新增"精选" |
| R06 | 抖音安全与信任中心，《算法和用户都想打破"信息茧房"》，2025-01-20 | https://95152.douyin.com/article/15364 | "不感兴趣"为强负反馈且有独立打分模型；屏蔽词；打散；随机探索；多样性与长期活跃 |
| R07 | 抖音安全与信任中心，《从零开始了解推荐系统》，2025-03-30 | https://95152.douyin.com/article/15358 | 行为类型；预测是否看完/点赞/收藏 |
| R08 | xai-org/x-algorithm README（仓库创建 2026-01-19） | https://github.com/xai-org/x-algorithm | For You 动作族（含 dwell、not dwelled）；得分 = Σ 权重×概率 |
| R09 | Instagram, *Introducing "You're All Caught Up" in Feed*, 2018-07-02 | https://about.instagram.com/blog/announcements/introducing-youre-all-caught-up-in-feed | 看完近两天内容后提示 |
| R10 | Instagram, *Introducing Instagram Reels*, 2020-08-05 | https://about.instagram.com/blog/announcements/introducing-instagram-reels-announcement | Reels 在 Explore 中以竖向 feed 呈现 |
| R11 | NN/g, *Infinite Scrolling: When to Use It, When to Avoid It*, 2022-09-04 | https://www.nngroup.com/articles/infinite-scrolling-tips/ | 无限滚动的适用性、键盘可达性、返回丢位置 |
| R12 | NN/g, *Using Swipe to Trigger Contextual Actions*, 2017-02-12 | https://www.nngroup.com/articles/contextual-swipe/ | 滑动可发现性低、需可见线索、多义问题、需确认或撤销 |
| R13 | Rixen et al., *The Loop and Reasons to Break It*, PACM HCI (MobileHCI) 2023 | https://doi.org/10.1145/3604275 | 无限滚动与懊悔的会话延长（摘要称此前已有报告）；一周田野研究 N=46；内外循环（核验：Crossref 摘要） |
| R14 | Meinhardt et al., *Scrolling in the Deep*, CHI 2025 | https://doi.org/10.1145/3706598.3713187 | 干预效果受情境影响（N=72，7 天） |
| R15 | Pronk & Denissen, *A Rejection Mind-Set: Choice Overload in Online Dating*, SPPS（2019 在线/2020 刊期） | https://doi.org/10.1177/1948550619866189 | 接受概率从首个到末个选项平均下降 27% |
| R16 | Tinder 订阅权益页 | https://tinder.com/feature/subscription-tiers | "Unlimited Rewinds" 属 Tinder Plus（Gold/Platinum 包含）；脚注：Rewinds 可能在部分市场以测试形式提供 |
| R17 | Flicke et al., *Scholar Inbox: Personalized Paper Recommendations for Scientists*, arXiv:2504.08385（ACL 2025 Demo） | https://arxiv.org/abs/2504.08385 ；https://aclanthology.org/2025.acl-demo.30/ | 卡片内容、二元评分、主动学习、冷启动、用户与评分规模 |
| R18 | PR Newswire, alphaXiv $7M 种子轮, 2025-11-19 | https://www.prnewswire.com/news-releases/alphaxiv-raises-7m-seed-round-to-bridge-the-ai-research-to-practice-divide-302619615.html | 融资额、领投方 |
| R19 | alphaXiv 发布 Mobile 的 X 帖（ID 解码时间 2026-07-13）；App Store 页（网页被区域重定向）；iTunes Lookup API（核验改用） | https://x.com/askalphaxiv/status/2076679038408572943 ；https://apps.apple.com/us/app/alphaxiv/id6782411985 ；https://itunes.apple.com/lookup?id=6782411985&country=us | 首发 2026-07-08、现版本 1.4.0（2026-09-01）、iOS 17+；商店描述（Trending Feed blurbs、Library、AI Assistant、Paper Reader、AI Visual Blogs） |
| R20 | Hugging Face 博客，*A Guide to Hugging Face's Papers Page*, 2025-11-25 | https://huggingface.co/blog/AdinaY/a-guide-to-hugging-faces-papers-page | upvote、讨论、librarian-bot、订阅、作者认领、关联模型/数据集 |
| R21 | Hugging Face Daily Papers 页面（实测） | https://huggingface.co/papers | 卡片字段与 Daily/Weekly/Monthly/Trending |
| R22 | Hugging Face Changelog: Trending Papers, 2025-07-28 | https://huggingface.co/changelog/trending-papers | Trending Papers 上线日期 |
| R23 | CodeSOTA, Papers with Code 页面（二手）；AK（HF）X 帖 2025-07-25（ID 解码）；paperswithcode.com 重定向实测 | https://www.codesota.com/papers-with-code ；https://x.com/_akhaliq/status/1948729112626946080 ；https://paperswithcode.com/ | PwC 于 2025-07-24 下线；现 302 → huggingface.co/papers/trending |
| R24 | Editage R Discovery 页；R Discovery 官网 | https://www.editage.com/r-discovery ；https://discovery.researcher.life/ | 个性化 feed、音频、翻译、Prime 定价（$5/月、$12/季、$39/年） |
| R25 | R Discovery Google Play 页（核验：已逐字读取商店描述） | https://play.google.com/store/apps/details?id=com.rdiscovery | GetFTR & LibKey 集成用大学凭证访问付费墙论文；Research in Shorts（类 Instagram Story） |
| R26 | Taylor & Francis Newsroom, 2019-10-10 | https://newsroom.taylorandfrancisgroup.com/access-taylor-francis-research-easily-on-the-move-with-researcher/ | Researcher 社媒式 feed、15,000+ 期刊、100 万+ 学者 |
| R27 | Semantic Scholar FAQ: *How do I create a Research Feed?* | https://www.semanticscholar.org/faq/create-research-feeds | Library 正信号、not relevant 负信号、5+3 起步 |
| R28 | Papel 着陆页；HN Show HN 讨论（2026-05-11） | https://andreaturchet.github.io/website/index.html ；https://news.ycombinator.com/item?id=48096842 | 产品功能；社区反馈归纳 |
| R29 | Gist Discover；HN（2026-07-02） | https://gist.is/discover ；https://news.ycombinator.com/item?id=48768342 | 一次一篇、分层 gist、朗读 |
| R30 | ArTok；HN（2025-04-21） | https://artok.app ；https://news.ycombinator.com/item?id=43755405 | AI/ML 会议论文发现、免注册 |
| R31 | Open Paper Digest；HN（2025-12-02） | https://www.openpaperdigest.com ；https://news.ycombinator.com/item?id=46119932 | 摘要流、点击展开 |
| R32 | PapersTok HN（2025-02-21；站点 2026-09-26 不可达） | https://news.ycombinator.com/item?id=43125566 | 早期论文 TikTok 原型 |
| R33 | pokepaper HN（2026-02-04） | https://news.ycombinator.com/item?id=46890772 | TikTok 式论文阅读器原型 |
| R34 | jtleek/papr（about.md、help.md、ui.R）；HN（2021-04-21） | https://github.com/jtleek/papr ；https://news.ycombinator.com/item?id=26886409 | 四向 2×2 评分与图例 |
| R35 | IsaacGemal/wikitok README；HN（2025-02-04，1,459 分）；作者复盘（2025-02-27） | https://github.com/IsaacGemal/wikitok ；https://news.ycombinator.com/item?id=42936723 ；https://www.aizk.sh/posts/reflecting-on-wikitok | 技术栈、预加载、构建过程、丢弃无图条目 |
| R36 | terrakok/WikWok README 与 `gradle/libs.versions.toml` | https://github.com/terrakok/WikWok | Kotlin 2.4 + Compose Multiplatform |
| R37 | Miguel07Alm/arxivtok README；HN（2025-02-05） | https://github.com/Miguel07Alm/arxivtok ；https://news.ycombinator.com/item?id=42952147 | SolidJS 栈、手势、多源 |
| R38 | mugar123/papertok：README、design.md、FeedContainer.css、PaperCard.css、ui/drawer.jsx、package.json | https://github.com/mugar123/papertok | scroll-snap、动效、诚实标签、Base UI Drawer、设计变更记录 |
| R39 | ASReview LAB 文档（Screening）；asreview/asreview | https://asreview.readthedocs.io/en/stable/lab/screening.html ；https://github.com/asreview/asreview | 一次一条、快捷键、异步重训 |
| R40 | Apple WWDC18 *Designing Fluid Interfaces*（Session 803） | https://developer.apple.com/videos/play/wwdc2018/803/ | 10pt 滞后、1:1 跟手、动量投影、100%/80% 阻尼、橡皮筋 |
| R41 | scenee/FloatingPanel `Sources/Core.swift`（注释引 WWDC18 slide p176） | https://github.com/scenee/FloatingPanel/blob/master/Sources/Core.swift | 投影公式 `(v/1000)·r/(1−r)` |
| R42 | nathangitter/fluid-interfaces `Pip.swift` | https://github.com/nathangitter/fluid-interfaces | 投影公式复刻 |
| R43 | jtrivedi/Wave `UIMathUtilities.swift` | https://github.com/jtrivedi/Wave | 默认减速率 0.998 |
| R44 | Apple WWDC23 *Animate with springs*（Session 10158） | https://developer.apple.com/videos/play/wwdc2023/10158/ | duration/bounce 模型与取值建议、速度保持 |
| R45 | Apple SwiftUI `Animation` 文档（spring/smooth/snappy/bouncy/interactiveSpring） | https://developer.apple.com/documentation/swiftui/animation | 各函数默认参数 |
| R46 | motiondivision/motion 源码：`motion-dom/.../generators/spring.ts`、`default-transitions.ts`、`framer-motion/.../drag/utils/constraints.ts`、`VisualElementDragControls.ts` | https://github.com/motiondivision/motion | spring 默认 100/10/1、变换属性 500/25、dragElastic 0.35、惯性参数 |
| R47 | Motion 文档：react-drag、react-layout-animations、react-accessibility、performance | https://motion.dev/docs/react-drag ；https://motion.dev/docs/react-layout-animations ；https://motion.dev/docs/react-accessibility ；https://motion.dev/docs/performance | dragDirectionLock、layoutId、reducedMotion="user"、主线程/硬件加速 |
| R48 | pmndrs/react-spring：`packages/core/src/constants.ts`、`demo/src/sandboxes/cards-stack/src/App.tsx` | https://github.com/pmndrs/react-spring | config 预设；cards-stack 参数 |
| R49 | 3DJakob/react-tinder-card `index.js`、`readme.md`、`package.json` | https://github.com/3DJakob/react-tinder-card | 阈值、倾角、弹簧、飞出时长 |
| R50 | webraptor/react-native-deck-swiper README、`Swiper.js` | https://github.com/webraptor/react-native-deck-swiper | W/4、H/5、±10°、350ms、叠层、PanResponder |
| R51 | Skipperlla/rn-swiper-list README、`src/Swiper.tsx` | https://github.com/Skipperlla/rn-swiper-list | ±π/20、弹簧 50/20、swipeBack、restoredSwipes |
| R52 | ricardodalarme/flutter_card_swiper README；pub.dev | https://github.com/ricardodalarme/flutter_card_swiper ；https://pub.dev/packages/flutter_card_swiper | maxAngle 30、scale 0.9、200ms、版本与下载 |
| R53 | react-native-reanimated `src/animation/spring/springConfigs.ts`；迁移文档 `migration-from-3.x.md` | https://github.com/software-mansion/react-native-reanimated | Gentle/Snappy/Wiggly、v3 旧默认、energyThreshold |
| R54 | Reanimated 文档 `withSpring` | https://docs.swmansion.com/react-native-reanimated/docs/animations/withSpring/ | 默认值与 ReduceMotion.System |
| R55 | RNGH 文档 `use-pan-gesture.mdx`（v3） | https://github.com/software-mansion/react-native-gesture-handler/blob/main/packages/docs-gesture-handler/docs/gestures/use-pan-gesture.mdx | activeOffset/failOffset/minVelocity 语义与单位 |
| R56 | androidx Material 3 tokens：`MotionTokens.kt`、`StandardMotionTokens.kt`、`ExpressiveMotionTokens.kt` | https://github.com/androidx/androidx/tree/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens | 时长、缓动、弹簧 token |
| R57 | androidx `SwipeToDismissBox.kt` | https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/SwipeToDismissBox.kt | 56dp、125dp/s |
| R58 | androidx `ItemTouchHelper.java` 与 `res/values/dimens.xml` | https://github.com/androidx/androidx/blob/androidx-main/recyclerview/recyclerview/src/main/java/androidx/recyclerview/widget/ItemTouchHelper.java | 0.5、120/800dp/s、250ms |
| R59 | AOSP `ViewConfiguration.java`（aosp-mirror） | https://github.com/aosp-mirror/platform_frameworks_base/blob/main/core/java/android/view/ViewConfiguration.java | touch slop、fling、长按/双击/tap 超时 |
| R60 | Android Developers: Gesture navigation（页面更新 2026-09-16） | https://developer.android.com/develop/ui/views/touch-and-input/gestures/gesturenav | 手势冲突与排除区 API |
| R61 | Android `View#setSystemGestureExclusionRects` 参考 | https://developer.android.com/reference/android/view/View | 排除区纵向 200dp 上限 |
| R62 | Apple HIG: Gestures | https://developer.apple.com/design/human-interface-guidelines/gestures | 快捷手势补充而非替代、避免与系统手势冲突、自定义手势要求 |
| R63 | Apple HIG: Playing haptics | https://developer.apple.com/design/human-interface-guidelines/playing-haptics | 触感补充、可关闭、一致 |
| R64 | Apple HIG: Motion | https://developer.apple.com/design/human-interface-guidelines/motion | 有目的的动效、频繁交互少动效、可选 |
| R65 | Apple HIG: Accessibility | https://developer.apple.com/design/human-interface-guidelines/accessibility | 44×44pt、手势替代、Reduce Motion、VoiceOver |
| R66 | Apple 文档：`CADisableMinimumFrameDurationOnPhone` | https://developer.apple.com/documentation/bundleresources/information-property-list/cadisableminimumframedurationonphone | ProMotion 高帧率需 plist 键（iOS 15+） |
| R67 | Apple 文档：`sensoryFeedback(_:trigger:)`、`UIImpactFeedbackGenerator`、`matchedGeometryEffect`、`navigationTransition`/`.zoom`、`scrollTargetBehavior`、`accessibilityReduceMotion` | https://developer.apple.com/documentation/swiftui/view/sensoryfeedback(_:trigger:) ；https://developer.apple.com/documentation/uikit/uiimpactfeedbackgenerator ；https://developer.apple.com/documentation/swiftui/navigationtransition/zoom(sourceid:in:) | API 与引入版本 |
| R68 | WebKit `Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml` | https://github.com/WebKit/WebKit/blob/main/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml | `PreferPageRenderingUpdatesNear60FPSEnabled` 默认 true |
| R69 | WebKit Blog, *Web Push for Web Apps on iOS and iPadOS*, 2023-02-16 | https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/ | iOS 16.4 Home Screen web app 推送与 Badging |
| R70 | WebKit Blog, *WebKit Features in Safari 26.0* | https://webkit.org/blog/17333/webkit-features-in-safari-26-0/ | 主屏幕默认以 web app 打开；scroll-driven animations |
| R71 | Fyrd/caniuse `features-json`（view-transitions、cross-document-view-transitions、vibration、css-overscroll-behavior、css-snappoints、prefers-reduced-motion、css-touch-action、push-api、css-content-visibility、avif、webp、loading-lazy-attr、intersectionobserver、link-rel-preload） | https://github.com/Fyrd/caniuse/tree/main/features-json | 浏览器支持版本与全球占比 |
| R72 | MDN: `touch-action` | https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action | pan-x/pan-y 等取值；Baseline |
| R73 | MDN: `Navigator.deviceMemory` | https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory | 有限可用、近似值、HTTPS |
| R74 | MDN: `Navigator.vibrate()` | https://developer.mozilla.org/en-US/docs/Web/API/Navigator/vibrate | 有限可用、需粘性用户激活 |
| R75 | web.dev, *Stick to Compositor-Only Properties and Manage Layer Count*（2015） | https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count | transform/opacity、图层管理 |
| R76 | web.dev, *How to create high-performance CSS animations* | https://web.dev/articles/animations-guide | 避免触发布局/绘制的属性 |
| R77 | web.dev, *Interaction to Next Paint (INP)*（更新 2025-09-02） | https://web.dev/articles/inp | 200ms/500ms 阈值 |
| R78 | React 博客, *React 19.3*, 2026-09-09 | https://react.dev/blog/2026/09/09/react-19-3 | `<ViewTransition>` 稳定 |
| R79 | Reanimated 文档：Shared Element Transitions | https://docs.swmansion.com/react-native-reanimated/docs/shared-element-transitions/overview | 实验特性、需 feature flag |
| R80 | W3C, WCAG 2.2 | https://www.w3.org/TR/WCAG22/ | SC 2.5.1、2.5.7、2.1.1、2.5.8、2.3.3、4.1.3、2.2.2 |
| R81 | React Native 文档：Accessibility；AccessibilityInfo | https://reactnative.dev/docs/accessibility ；https://reactnative.dev/docs/accessibilityinfo | accessibilityActions；isReduceMotionEnabled |
| R82 | Expo 文档：Haptics | https://docs.expo.dev/versions/latest/sdk/haptics/ | API 与 iOS 不触发条件 |
| R83 | Aza Raskin, *Never Use a Warning When you Mean Undo*, A List Apart, 2007-07-21 | https://alistapart.com/article/neveruseawarning/ | 撤销优于警告/确认 |
| R84 | YouTube 官方博客, *Five Stars Dominate Ratings*, 2009-09-22 | https://blog.youtube/news-and-events/five-stars-dominate-ratings/ | 星级评分两极化 |
| R85 | Netflix, *Goodbye Stars, Hello Thumbs*, 2017-04-05 | https://about.netflix.com/en/news/goodbye-stars-hello-thumbs | 二元评分使评分活动增加 200% |
| R86 | TikTok Newsroom, *Learn why a video is recommended For You*, 2022-12-20 | https://newsroom.tiktok.com/en-us/learn-why-a-video-is-recommended-for-you | "Why this video" |
| R87 | EU Regulation 2022/2065（DSA） | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2065 | 第 27 条（含第 3 款界面直达要求）、第 38 条（核验：浏览器渲染读取正文；curl 遇 AWS WAF 挑战未绕过） |
| R88 | 国家互联网信息办公室等，《互联网信息服务算法推荐管理规定》（2021-12-31 公布，2022-03-01 施行） | http://www.cac.gov.cn/2022-01/04/c_1642894606364259.htm | 第十二、十六、十七条 |
| R89 | Herlocker, Konstan, Riedl, *Explaining Collaborative Filtering Recommendations*, CSCW 2000 | https://doi.org/10.1145/358916.358995 | 推荐解释经典研究（仅核验题录） |
| R90 | Tintarev & Masthoff, *A Survey of Explanations in Recommender Systems*, ICDE Workshops 2007 | https://doi.org/10.1109/icdew.2007.4401070 | 解释目标（题录经 Crossref 核验；七项名称经 R115 旁证） |
| R91 | Cachola, Lo, Cohan, Weld, *TLDR: Extreme Summarization of Scientific Documents*, arXiv:2004.15011（Findings of EMNLP 2020） | https://arxiv.org/abs/2004.15011 | TLDR 任务与 SciTLDR 规模 |
| R92 | arXiv, License and copyright | https://info.arxiv.org/help/license/index.html | 许可选项；非独占许可限制他人再利用 |
| R93 | arXiv, Terms of Use for arXiv APIs | https://info.arxiv.org/help/api/tou.html | 元数据 CC0；不得存储并提供 e-print 内容；限速 |
| R94 | OpenAlex API：`/works?group_by=open_access.oa_status`；`/works/doi:10.48550/arXiv.2504.08385` | https://api.openalex.org/works?group_by=open_access.oa_status | oa_status 枚举；license 缺失示例 |
| R95 | npm registry 与 npm downloads API；pub.dev API | https://registry.npmjs.org/ ；https://api.npmjs.org/downloads/point/2026-09-18:2026-09-24/ ；https://pub.dev/api/packages/ | 版本、发布日期、周下载（核验按固定窗口复查）、pub 指标 |
| R96 | Flutter releases JSON | https://storage.googleapis.com/flutter_infra_release/releases/releases_macos.json | Flutter 3.47.5（2026-09-18） |
| R97 | Flutter 文档：Impeller（更新 2026-08-21）；Hero animations | https://docs.flutter.dev/perf/impeller ；https://docs.flutter.dev/ui/animations/hero-animations | Impeller 默认/唯一；Hero |
| R98 | Lynx 博客 *Lynx: Unlock Native for More*, 2025-03-05；lynx-family/lynx 及其 Releases | https://lynxjs.org/blog/lynx-unlock-native-for-more ；https://github.com/lynx-family/lynx ；https://github.com/lynx-family/lynx/releases | 双线程（主线程 PrimJS + 后台运行时）；TikTok 使用面（Search 面板、TikTok Studio、Shop、LIVE）；latest release 4.1.0（2026-09-07） |
| R99 | react-native-reanimated README（Compatibility） | https://github.com/software-mansion/react-native-reanimated | 4.x 仅新架构 |
| R100 | emilkowalski/vaul README；mui/base-ui | https://github.com/emilkowalski/vaul ；https://github.com/mui/base-ui | vaul 不再维护；Base UI 状态 |
| R101 | GitHub REST API（`gh api repos/{owner}/{repo}`） | https://docs.github.com/rest/repos/repos#get-a-repository | §2.2.2、§2.8 的 star/许可/推送时间 |
| R102 | HN Algolia Search API | https://hn.algolia.com/api | Show HN 帖子日期、分数、评论 |
| R103 | HN 帖：*ACM Digital Library started showing AI summaries of articles with abstracts*, 2025-12-17（原文页受 Cloudflare 挑战未访问） | https://news.ycombinator.com/item?id=46298556 | AI 摘要争议的线索（⚠） |
| R104 | Covidence 帮助中心：*How to screen by title and abstract*（核验补充） | https://support.covidence.org/help/screening-by-title-and-abstract | Yes/Maybe/No 三态投票；默认双人盲审 |
| R105 | Rayyan 帮助中心：*How to Screen References in Rayyan*；*How to Use Keyboard Shortcuts in Rayyan*（核验补充，浏览器渲染读取） | https://help.rayyan.ai/hc/en-us/articles/45703234075281-How-to-Screen-References-in-Rayyan ；https://help.rayyan.ai/hc/en-us/articles/25199470983185-How-to-Use-Keyboard-Shortcuts-in-Rayyan | Include/Maybe/Exclude；Maybe 独立列表；快捷键面板（V）；自定义仅限 Essential 及以上方案 |
| R106 | karpathy/arxiv-sanity-lite README 与 requirements.txt（核验补充） | https://github.com/karpathy/arxiv-sanity-lite | 标签 → 每标签 tf-idf SVM 推荐；每日邮件；Flask/scikit-learn/sqlitedict |
| R107 | expo/expo：`templates/expo-template-bare-minimum/ios/HelloWorld/Info.plist`；`packages/@expo/config-plugins/src/plugins/withIosBaseMods.ts`（核验补充） | https://github.com/expo/expo | Expo 模板默认 `CADisableMinimumFrameDurationOnPhone = true` |
| R108 | MDN browser-compat-data：`css/properties/animation-timeline.json`、`api/Element.json`（scrollsnapchange/scrollsnapchanging/scrollend）（核验补充） | https://github.com/mdn/browser-compat-data | 滚动驱动动画与 scroll-snap/scrollend 事件支持版本 |
| R109 | TikTok Newsroom, *TikTok's new features to help you "Control your scroll"*, 2025-06-03（核验补充） | https://newsroom.tiktok.com/tiktoks-new-features-to-help-you-control-your-scroll?lang=en-AU | Manage Topics、Smart Keyword Filters（≤200）、长按 Not interested、重置 For You |
| R110 | Instagram, *Control Your Instagram Reels Algorithm*（2025-12-10 发布，2026-04-15、2026-06-10 更新）（核验补充） | https://about.instagram.com/blog/announcements/reels-algorithm-control | "Your Algorithm"：查看/增加/调多调少兴趣主题，覆盖 Feed/Reels/Explore |
| R111 | JetBrains Kotlin 博客, *Compose Multiplatform 1.8.0 Released: Compose Multiplatform for iOS Is Stable and Production-Ready*, 2025-05（核验补充） | https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/ | CMP iOS Stable |
| R112 | Flutter API：`HapticFeedback` class（核验补充） | https://api.flutter.dev/flutter/services/HapticFeedback-class.html | lightImpact/mediumImpact/heavyImpact/selectionClick/vibrate |
| R113 | Semantic Scholar Graph API swagger（核验补充） | https://api.semanticscholar.org/graph/v1/swagger.json | `tldr` 字段 `{model, text}`（模型如 tldr@v2.0.0，源自 SciTLDR） |
| R114 | Jack Davidson & Wayne Graves, *Evolving the ACM Digital Library*, Communications of the ACM, 2026-03-03（核验补充，浏览器渲染读取；未操作 Cookie 弹窗） | https://cacm.acm.org/opinion/evolving-the-acm-digital-library/ | DL Premium 的 AI 长/短摘要、社区质疑、免责声明与反馈机制 |
| R115 | Nava Tintarev, *Explanations of Recommendations*, RecSys 2007 Doctoral Symposium（核验补充） | https://www.macs.hw.ac.uk/~dwcorne/ACMRecSys07/p203-tintarev.pdf | Table 1 七项解释目标，引 R90 详述 |

## 核验记录

> 核验角色：对抗式事实核验（opus5.5-verify），核验日期 **2026-09-26**。本节是全文唯一的核验记录，文中此前没有核验章节，也没有中断核验留下的半截修改（逐段检查，未发现"核验"字样或不一致的残留编辑）。
> 结论口径：**确认**＝与一手来源原文一致；**修正**＝已就地更正，正文标"核验修正"；**删除**＝查无实据、已删；**部分确认**＝核心事实成立，细节仍标 ⚠；**未核验**＝保留 ⚠。本轮**没有删除项**：抽查到的仓库、产品、论文和 HN 帖全部存在。
> 核验补充（正文标"核验补充"）：Covidence 与 Rayyan 的三态筛选、karpathy/arxiv-sanity-lite、scroll-snap 事件与滚动驱动动画的支持度、TikTok Manage Topics 等控制项、Instagram "Your Algorithm"、R Discovery "Research in Shorts"，另有 R104–R115 共 12 条新来源。

**核验过程（可复现）**

- GitHub：`gh api repos/{owner}/{repo} --jq '.stargazers_count,.license.spdx_id,.pushed_at,.archived'` 逐仓查询 44 个仓库（其中有 6 个 0★ 原型；alexbrillant/react-native-deck-swiper 返回 404，npm 包实际指向 webraptor 仓库；另查 aosp-mirror 的归档状态）；`gh api repos/.../contents/<path>` 读源码常量和 README（motion、react-spring、react-tinder-card、react-native-deck-swiper、rn-swiper-list、reanimated、RNGH 文档、papertok、arxivtok、wikitok、WikWok、papr、x-algorithm、vaul、base-ui、arxiv-sanity-lite、expo）；`gh api search/code` 用于定位文件；另查 `gh api repos/lynx-family/lynx/releases`。
- 公开 API：npm registry 查版本与发布时间；`api.npmjs.org/downloads/point/2026-09-18:2026-09-24/<pkg>`（20 个包）和 `/downloads/range/2026-09-17:2026-09-25/motion`（按日对账）；pub.dev 的 `/api/packages/<pkg>` 与 `/score`；HN Algolia `/api/v1/items/<id>`（10 帖）；Crossref `/works/<doi>`（4 篇）；arXiv export API（2004.15011）；OpenAlex（`group_by=open_access.oa_status` 与 arXiv:2504.08385）；iTunes Lookup（alphaXiv）；Flutter releases JSON；Fyrd/caniuse `features-json`；mdn/browser-compat-data；Semantic Scholar swagger。
- curl 直读：WebKit `UnifiedWebPreferences.yaml`、AOSP `ViewConfiguration.java`、androidx 的 `ItemTouchHelper.java`/`dimens.xml`/`SwipeToDismissBox.kt`/M3 tokens、W3C WCAG 2.2、网信办规定原文、webkit.org 两篇、web.dev INP、MDN、Expo Haptics、Flutter 文档（Impeller、HapticFeedback）、Apple 文档 JSON（HIG、SwiftUI、plist 键）、Tinder 订阅页、Google Play（R Discovery）、YouTube 博客、人民网、A List Apart、NN/g。
- WebFetch：react.dev 19.3 博客、PR Newswire、Netflix、Instagram（3 篇）、TikTok（2 篇）、HF changelog、S2 FAQ、arXiv 许可页与 API ToU、Editage、T&F、motion.dev 可访问性文档、WWDC18 803 和 WWDC23 10158 的文字稿、Covidence。
- 浏览器面板渲染（用于 JS 站点）：抖音安全与信任中心 15364、15358；EUR-Lex DSA（curl 遇 AWS WAF 挑战，改用普通浏览器渲染，未做任何绕过）；aizk.sh WikiTok 复盘；Rayyan 帮助中心两篇；CACM。全程不登录，不点击 Cookie 或同意弹窗。
- WebSearch 检索式：`alphaXiv iOS app launch July 2026`；`"Papers with Code" sunset redirect Hugging Face trending July 2025`；`R Discovery Prime price per month 2026`；`"Scrolling in the Deep" Meinhardt CHI 2025 infinite scrolling intervention participants`；`Covidence title and abstract screening vote Yes No Maybe keyboard shortcuts`；`Rayyan screening include exclude maybe keyboard shortcuts help`；`TikTok newsroom "Manage topics" For You feed control announcement`；`Instagram "Your Algorithm" Reels topics control launch`；`Compose Multiplatform 1.8.0 iOS stable production-ready JetBrains blog May 2025`；`ACM Digital Library AI-generated summaries articles announcement 2025 abstracts backlash`；`Tintarev Masthoff 2007 "A Survey of Explanations in Recommender Systems" ...`。
- 受阻情况：dl.acm.org 有 Cloudflare 挑战，未访问；apps.apple.com 被重定向到区域首页，改用 iTunes Lookup API；researcher-app.com 无法连接；S2 Graph API 返回 429；papers.infitok.com 不可达，与原文一致。

| # | 断言（原文位置） | 结论 | 依据来源 URL | 核验日期 |
|---|---|---|---|---|
| 1 | React 19.3 于 2026-09-09 发布，`<ViewTransition>` 转为稳定（§0、§2.3.6、§2.7.1） | 确认 | https://react.dev/blog/2026/09/09/react-19-3 ；https://registry.npmjs.org/react | 2026-09-26 |
| 2 | npm 周下载：motion 约 2,004 万、framer-motion 约 4,331 万、@base-ui/react 约 1,300 万等 20 个包（§2.7.1、§2.8） | 修正：用同一窗口（2026-09-18 至 09-24）复查，各包数值都比原文高约 20%（原值平均偏低约 17%）。按日数据看，疑为抓取时某日尚未入账。已全表更正（motion 2,407 万、framer-motion 5,198 万、base-ui 1,570 万……），各包排序不变 | https://api.npmjs.org/downloads/point/2026-09-18:2026-09-24/motion ；https://api.npmjs.org/downloads/range/2026-09-17:2026-09-25/motion | 2026-09-26 |
| 3 | 各库版本与发布日：motion 13.4.4、@base-ui/react 1.8.0、next 16.3.6、expo 57.0.25、react-native 0.87.1、reanimated 4.7.0、worklets 0.13.0、RNGH 3.3.0、@capacitor/core 8.5.2、@capacitor/haptics 8.0.2、@lynx-js/react 0.126.2、swiper 14.2.0（§2.7.1、§2.8） | 确认 | https://registry.npmjs.org/ | 2026-09-26 |
| 4 | Lynx 当前版本为 4.0.3（2026-09-11）（§2.7.1） | 修正：GitHub 标记的 latest release 是 4.1.0（2026-09-07），4.0.3 只是 release/4.0 分支的补丁；4.0.0 发布于 2026-07-20 | https://github.com/lynx-family/lynx/releases | 2026-09-26 |
| 5 | Lynx 于 2025-03-05 开源，采用双线程（PrimJS 主线程 + 后台运行时）；TikTok 在 Search 面板、TikTok Studio、Shop、LIVE 中使用，未声明用于主推荐流（§2.7.1） | 确认 | https://lynxjs.org/blog/lynx-unlock-native-for-more | 2026-09-26 |
| 6 | Base UI 有 Drawer 组件，支持 swipe-to-dismiss 和 snap points（§2.7.1、§2.8） | 确认 | https://github.com/mui/base-ui （docs/src/app/(docs)/react/components/drawer/page.mdx） | 2026-09-26 |
| 7 | vaul 的 README 声明不再维护；use-gesture 最近推送为 2024-07-15；react-tinder-card 最近推送为 2024-06-21（§2.8、§4） | 确认 | https://github.com/emilkowalski/vaul ；https://github.com/pmndrs/use-gesture ；https://github.com/3DJakob/react-tinder-card | 2026-09-26 |
| 8 | §2.2.2 和 §2.8 中共 35 个仓库的 star、许可与最近推送（如 wikitok 1,324/MIT、motion 33,736、base-ui 11,000、x-algorithm 创建于 2026-01-19） | 确认：star 只有个位数漂移；react-native-deck-swiper 的 npm 包确实指向 webraptor 仓库（178★）；aosp-mirror 镜像已归档，但常量有效。另核 §2.2.2 文末 6 个 0★ 原型仓库均存在；其中 paper-scroll 创建于 2024-10，已把"2025–2026 年原型"改为"多数创建于 2025–2026 年" | https://docs.github.com/rest/repos/repos#get-a-repository （gh api 逐仓查询） | 2026-09-26 |
| 9 | PaperTok（mugar123）实现细节：scroll-snap 用 mandatory + stop always，100dvh，overscroll contain，overflow-anchor none；320ms / 0.32–0.36s 的 `cubic-bezier(0.16,1,0.3,1)`，45ms 错峰；有 reduced-motion 分支；使用 Base UI Drawer；README 的"Honest labels"；2026-08-25 的设计变更（§2.2.3） | 确认 | https://github.com/mugar123/papertok | 2026-09-26 |
| 10 | 各 HN 帖的日期与分数：Papel 2026-05-11 200 分、42 条顶层评论；WikiTok 1,459 分；Gist、ArTok、Open Paper Digest、PapersTok、pokepaper、papr、ArxivTok、ACM 帖（§2.2） | 确认 | https://hn.algolia.com/api/v1/items/48096842 （及另外 9 个 item id） | 2026-09-26 |
| 11 | Scholar Inbox：80 万条评分、1.43 万评分用户、2.3 万注册、30 日活跃 8 千（35%）；GTE-Large F1 84.51；300 万篇论文的 t-SNE 地图；前五张图表由 papermage 抽取；相关度缩放到 [-100,100]；分层采样主动学习；按工作日发 digest；ACL 2025 Demo（§2.2.1） | 确认 | https://arxiv.org/html/2504.08385 ；https://aclanthology.org/2025.acl-demo.30/ | 2026-09-26 |
| 12 | alphaXiv 于 2025-11-19 宣布 700 万美元种子轮，由 Menlo Ventures 和 Haystack 领投（§2.2.1） | 确认（原文为 co-led，已改为"共同领投"） | https://www.prnewswire.com/news-releases/alphaxiv-raises-7m-seed-round-to-bridge-the-ai-research-to-practice-divide-302619615.html | 2026-09-26 |
| 13 | alphaXiv iOS 版 2026-07-13 发布；商店细节"未能直读"（§2.2.1） | 修正：App Store 首发为 2026-07-08，2026-07-13 是官方 X 帖的日期；现版本 1.4.0（2026-09-01），需 iOS 17+；商店描述已逐字读取 | https://itunes.apple.com/lookup?id=6782411985&country=us ；https://x.com/askalphaxiv/status/2076679038408572943 | 2026-09-26 |
| 14 | HF Trending Papers 于 2025-07-28 上线；Papers with Code 于 2025-07-24/25 下线并重定向（原标 ⚠ 二手）（§2.2.1） | 确认，并补强证据：changelog 说明 Trending 按 GitHub star 活跃度排序；AK 在 2025-07-25 的 X 帖称"昨日"下线；paperswithcode.com 现 302 到 /papers/trending（实测） | https://huggingface.co/changelog/trending-papers ；https://x.com/_akhaliq/status/1948729112626946080 ；https://paperswithcode.com/ | 2026-09-26 |
| 15 | S2 Research Feeds 官方建议起步评 5 篇相关 + 3 篇不相关（§2.2.1、§3） | 确认 | https://www.semanticscholar.org/faq/create-research-feeds | 2026-09-26 |
| 16 | R Discovery Prime "每月 12 美元起"（§2.2.1） | 修正：Editage 页标价为 $5/月、$12/季、$39/年；价格随促销和地区变动，标 ⚠ | https://www.editage.com/r-discovery | 2026-09-26 |
| 17 | R Discovery 可经 GetFTR/LibKey 用机构凭证解锁全文（原标 ⚠ 检索摘要）（§2.2.1） | 确认：已逐字读取 Google Play 描述；另补充 "Research in Shorts" 使用类 Instagram Story 的格式 | https://play.google.com/store/apps/details?id=com.rdiscovery | 2026-09-26 |
| 18 | Researcher：2019-10-10 T&F 新闻稿称覆盖 15,000+ 期刊、有 100 万+ 学者（§2.2.1） | 确认；"18,000+/200 万"这一新口径仍未核验（官网无法连接） | https://newsroom.taylorandfrancisgroup.com/access-taylor-francis-research-easily-on-the-move-with-researcher/ | 2026-09-26 |
| 19 | Pronk & Denissen：三项研究中，从首个到末个选项的接受概率平均下降 27%；SPPS 2019 在线、2020 年 11(3):388–396（§2.1、§4） | 确认 | https://doi.org/10.1177/1948550619866189 （Crossref 摘要） | 2026-09-26 |
| 20 | 无限滚动"被实证与懊悔的会话延长相关"（Rixen 2023）（§2.1.3） | 修正措辞：摘要说的是此前已有报告；该文是一周田野研究（N=46），刻画了内外循环及退出原因 | https://doi.org/10.1145/3604275 | 2026-09-26 |
| 21 | Meinhardt 等 CHI 2025：干预效果受情境影响，N=72，为期 7 天（§2.1.3） | 确认 | https://doi.org/10.1145/3706598.3713187 ；https://arxiv.org/abs/2501.11814 | 2026-09-26 |
| 22 | Netflix 2017-04-05 测试用 thumbs 替代星级，评分活动增加 200%；YouTube 2009-09-22 发现星级评分"几乎全有或全无"（§2.6.4） | 确认 | https://about.netflix.com/en/news/goodbye-stars-hello-thumbs ；https://blog.youtube/news-and-events/five-stars-dominate-ratings/ | 2026-09-26 |
| 23 | Instagram 2018-07-02 推出 "You're All Caught Up"（看完近两天内容后提示）；Reels 于 2020-08-05 以竖向 feed 放在 Explore 中；TikTok 于 2022-12-20 在分享面板加入 "Why this video"（§2.1、§2.6.5） | 确认 | https://about.instagram.com/blog/announcements/introducing-youre-all-caught-up-in-feed ；https://about.instagram.com/blog/announcements/introducing-instagram-reels-announcement ；https://newsroom.tiktok.com/en-us/learn-why-a-video-is-recommended-for-you | 2026-09-26 |
| 24 | 快手 8.0 于 2020-09-03 上线，兼容双列点选和单列上下滑，新增"精选"（§2.1.1） | 确认 | http://finance.people.com.cn/n1/2020/0903/c1004-31848521.html | 2026-09-26 |
| 25 | 抖音：官方称"不感兴趣"是强负反馈，并有独立打分模型；支持屏蔽词；多样性实验显示推送越多元，长期活跃越高（2025-01-20）；推荐系统基于点击、浏览等行为建模，预测是否看完/点赞/收藏（2025-03-30）（§2.1、§2.6.4、§3） | 确认 | https://95152.douyin.com/article/15364 ；https://95152.douyin.com/article/15358 | 2026-09-26 |
| 26 | X 开源排序：四个动作族（含 dwell、not dwelled），最终分 = Σ 权重 × 预测概率（§2.1.1、§2.9.6） | 确认 | https://github.com/xai-org/x-algorithm | 2026-09-26 |
| 27 | Tinder 把 Unlimited Rewinds 作为 Plus 权益（§2.1、§2.5.3） | 确认；补充页脚注：Rewinds 可能在部分市场以测试形式提供 | https://tinder.com/feature/subscription-tiers | 2026-09-26 |
| 28 | arXiv 提供 6 种许可选项；非独占许可会限制他人任何形式的再利用（§2.6.6） | 确认 | https://info.arxiv.org/help/license/index.html | 2026-09-26 |
| 29 | arXiv API ToU：元数据按 CC0；不得在自有服务器存储并提供 e-print；每 3 秒 1 次请求、单连接（§2.6.6） | 确认；措辞细化为 legacy APIs（OAI-PMH、RSS、arXiv API） | https://info.arxiv.org/help/api/tou.html | 2026-09-26 |
| 30 | OpenAlex 的 oa_status 取值为 diamond/gold/green/hybrid/bronze/closed；arXiv:2504.08385 的 license 为 null、oa_status 为 green（§2.6.2、§2.6.6） | 确认 | https://api.openalex.org/works?group_by=open_access.oa_status ；https://api.openalex.org/works/doi:10.48550/arXiv.2504.08385 | 2026-09-26 |
| 31 | 网信办《算法推荐管理规定》第十二、十六、十七条；令第 9 号，2021-12-31 公布，2022-03-01 施行（§2.6.5、§3） | 确认；另核第二十四条（10 个工作日内备案）与第二十七条（安全评估）原文。本平台是否适用仍标 ⚠，需法务判断 | http://www.cac.gov.cn/2022-01/04/c_1642894606364259.htm | 2026-09-26 |
| 32 | DSA 第 27、38 条；原文称"序言指出应能在推荐呈现界面直接访问"（§2.6.5） | 修正：这一要求出自第 27 条第 3 款正文，不是序言；第 38 条只适用于超大平台和超大搜索引擎 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2065 | 2026-09-26 |
| 33 | WCAG 2.2 各项级别：2.5.1 A、2.5.7 AA（2.2 新增）、2.1.1 A、2.5.8 AA（24×24，同为新增）、2.3.3 AAA、4.1.3 AA、2.2.2 A；HIG 在 iOS 上默认 44×44pt、最小 28×28pt（§2.5.1） | 确认 | https://www.w3.org/TR/WCAG22/ ；https://developer.apple.com/design/human-interface-guidelines/accessibility | 2026-09-26 |
| 34 | WebKit 偏好 `PreferPageRenderingUpdatesNear60FPSEnabled` 默认为 true，visionOS 为 false（§2.4.2） | 确认（源码） | https://github.com/WebKit/WebKit/blob/main/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml | 2026-09-26 |
| 35 | iOS 26 起，加到主屏幕的网站默认以 web app 打开；iOS 16.4 起 Home Screen web app 支持 Web Push 与 Badging（WebKit 2023-02-16 公布）（§2.7.1） | 确认 | https://webkit.org/blog/17333/webkit-features-in-safari-26-0/ ；https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/ | 2026-09-26 |
| 36 | caniuse 支持数据：View Transitions 同文档为 Chrome 111、Safari 18、Firefox 144，全球 91.75%；跨文档为 Chrome 126、Safari 18.2，Firefox 144 仅部分；Safari 不支持 Vibration；overscroll-behavior 为 Safari 16；content-visibility 为 Safari 18、Firefox 125；AVIF 95.35%；loading=lazy 为 iOS 16.4；prefers-reduced-motion 96.45%（§2.3–§2.4） | 确认 | https://github.com/Fyrd/caniuse/tree/main/features-json | 2026-09-26 |
| 37 | ProMotion 需在 plist 设 `CADisableMinimumFrameDurationOnPhone`（iOS 15+）；原文标 ⚠ 的"Expo 模板是否默认开启"（§2.4.2） | 确认；原 ⚠ 项已核实：Expo 模板与 config-plugins 默认均为 true | https://developer.apple.com/documentation/bundleresources/information-property-list/cadisableminimumframedurationonphone ；https://github.com/expo/expo | 2026-09-26 |
| 38 | Expo Haptics 在 iOS 低电量模式、Taptic 被关闭、相机或听写进行中时不触发；Android 推荐用 `performAndroidHapticsAsync`（§2.3.7） | 确认 | https://docs.expo.dev/versions/latest/sdk/haptics/ | 2026-09-26 |
| 39 | Android 平台手势常数：touch slop 8/16dp；fling 50–8000；长按/双击/tap 为 400/300/100ms；ItemTouchHelper 为 0.5、120/800dp、250ms；SwipeToDismissBox 为 56dp、125dp；排除区纵向合计上限 200dp，且不必为整块 ScrollView 注册（§2.3.1） | 确认 | https://github.com/aosp-mirror/platform_frameworks_base/blob/main/core/java/android/view/ViewConfiguration.java ；https://github.com/androidx/androidx ；https://developer.android.com/reference/android/view/View | 2026-09-26 |
| 40 | Material 3 motion tokens：Standard 与 Expressive 的弹簧参数、Short/Medium/Long 时长、Emphasized 系列缓动（§2.3.3） | 确认 | https://github.com/androidx/androidx/tree/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens | 2026-09-26 |
| 41 | Motion 默认值：spring 100/10/1（bounce 0.3、visualDuration 0.3）；变换属性 500/25；缩放到 0 时为 550/2√550；dragElastic 0.35；timeConstant 750；有 elastic 时为 200/40。原文称 100/10/1 为"早期默认"（§2.3） | 确认参数；修正表述：100/10/1 是 Motion 现行物理默认，并非"早期"默认 | https://github.com/motiondivision/motion | 2026-09-26 |
| 42 | 开源卡片组件的默认参数：react-spring 预设与 cards-stack；react-tinder-card（25°、0.5、2000/50、400/30、200/10）；deck-swiper（W/4、H/5、±10°、350ms、10 与 3%、7/40）；rn-swiper-list（±π/20、50/20/1）；flutter_card_swiper（30°、0.9、200ms、50、undo）（§2.3.2） | 确认 | https://github.com/pmndrs/react-spring ；https://github.com/3DJakob/react-tinder-card ；https://github.com/webraptor/react-native-deck-swiper ；https://github.com/Skipperlla/rn-swiper-list ；https://github.com/ricardodalarme/flutter_card_swiper | 2026-09-26 |
| 43 | Reanimated 4 的 Gentle/Snappy/Wiggly 参数、3.x 旧默认，以及迁移文档称旧默认"用处不大"；4.x 仅支持新架构和最近三个 RN 版本；共享元素转场为实验特性、需 feature flag、不建议用于生产（§2.3、§2.3.6、§2.7） | 确认；补注 Snappy 设了 overshootClamping，实际超调为 0 | https://github.com/software-mansion/react-native-reanimated ；https://docs.swmansion.com/react-native-reanimated/docs/shared-element-transitions/overview | 2026-09-26 |
| 44 | SwiftUI 各函数默认参数（0.5/0、0.15/0.86/0.25、0.5/0.825）与 API 引入版本（14/17/18）；WWDC18 的 10pt 滞后、100%/80% 阻尼与动量投影；WWDC23 的 bounce 指南；FloatingPanel 投影公式（§2.3） | 确认 | https://developer.apple.com/documentation/swiftui/animation ；https://developer.apple.com/videos/play/wwdc2018/803/ ；https://developer.apple.com/videos/play/wwdc2023/10158/ ；https://github.com/scenee/FloatingPanel | 2026-09-26 |
| 45 | Flutter 3.47.5（2026-09-18，Dart 3.13.4）；Impeller 自 3.27 起在 iOS 与 Android API 29+ 默认启用，iOS 上是唯一渲染器；原文标 ⚠ 的触感 API（§2.4.2、§2.7） | 确认；触感 API 已核实（HapticFeedback） | https://storage.googleapis.com/flutter_infra_release/releases/releases_macos.json ；https://docs.flutter.dev/perf/impeller ；https://api.flutter.dev/flutter/services/HapticFeedback-class.html | 2026-09-26 |
| 46 | 原文标 ⚠：Compose Multiplatform 在 iOS 上的成熟度（§2.7.2） | 已核实：CMP 1.8.0（2025-05）起 iOS 为 Stable | https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/ | 2026-09-26 |
| 47 | INP 在 p75 ≤200ms 为良好、>500ms 为差（页面更新于 2025-09-02）；deviceMemory 可用性有限、仅 HTTPS、取近似 2 的幂（§2.4） | 确认 | https://web.dev/articles/inp ；https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory | 2026-09-26 |
| 48 | SciTLDR 含 3.2K 篇论文的 5.4K 条 TLDR；Raskin 那篇 A List Apart 文章发表于 2007-07-21；NN/g 两文分别发表于 2022-09-04 和 2017-02-12（§2.5–§2.6） | 确认 | https://arxiv.org/abs/2004.15011 ；https://alistapart.com/article/neveruseawarning/ ；https://www.nngroup.com/articles/infinite-scrolling-tips/ ；https://www.nngroup.com/articles/contextual-swipe/ | 2026-09-26 |
| 49 | WikiTok 作者复盘（2025-02-27）：约 2 小时用 Claude + Cursor 搭出；IntersectionObserver 每次拉 5 条；后期丢弃无缩略图的条目；拒绝加入"算法"和存储用户数据。README 写明 14 种语言、预加载、PWA（§2.2.2） | 确认 | https://www.aizk.sh/posts/reflecting-on-wikitok ；https://github.com/IsaacGemal/wikitok | 2026-09-26 |
| 50 | 其余开源与产品描述：arxivtok 的多源与双击点赞、SolidJS 栈；WikWok 使用 Kotlin 2.4.0 与 CMP 1.12.0-alpha02、iOS 走 PWA；papr 的 2×2 评分；ASReview 快捷键 r/i/n 与异步重训；HF 论文页指南（2025-11-25）；Papel 着陆页 | 确认；Papel 补注"候补名单" | https://github.com/Miguel07Alm/arxivtok ；https://github.com/terrakok/WikWok ；https://github.com/jtleek/papr ；https://asreview.readthedocs.io/en/stable/lab/screening.html ；https://huggingface.co/blog/AdinaY/a-guide-to-hugging-faces-papers-page ；https://andreaturchet.github.io/website/index.html | 2026-09-26 |
| 51 | Gist Discover 为一次一篇 + Next，采用分层 gist（Gist → Logic → Counter-argument → Steelman）（§2.2.1） | 部分确认：页面元数据写有 "fast layered Gists"，并有 Next 按钮；各层名称沿用调研员的浏览器实测（B 级），本轮未复测 | https://gist.is/discover | 2026-09-26 |
| 52 | ACM DL 曾以 AI 摘要替代作者摘要，并引发反弹（原标 ⚠）（§2.2.4、§4） | 部分确认：CACM 2026-03-03 确认 AI 长/短摘要存在、社区提出质疑，ACM 随后加了免责声明和反馈入口；"替代作者摘要"的细节仍标 ⚠（dl.acm.org 有 Cloudflare 挑战，未访问） | https://cacm.acm.org/opinion/evolving-the-acm-digital-library/ | 2026-09-26 |
| 53 | Tintarev & Masthoff 的七项解释目标（原标 ⚠，据既有知识）（§2.6.5） | 确认：见 Tintarev 在 RecSys'07 博士论坛论文的 Table 1，该文注明详见此综述 | https://www.macs.hw.ac.uk/~dwcorne/ACMRecSys07/p203-tintarev.pdf ；https://doi.org/10.1109/icdew.2007.4401070 | 2026-09-26 |
| 54 | S2 的 `tldr` 字段可作参考（原标 ⚠，API 限流）（§2.6.2） | 部分确认：swagger 中有 `tldr {model, text}` 字段；实际取值仍因 429 未取回，展示许可也未核 | https://api.semanticscholar.org/graph/v1/swagger.json | 2026-09-26 |
| 55 | iPhone 上的 PWA 用 JS 驱动动画，上限约 60Hz（⚠ 推断）；Android Chrome 在高刷屏上的 rAF 节拍（⚠）；Tinder 自身的手势参数（⚠）（§2.3.2、§2.4.2） | 未核验：无公开一手来源，需真机实测，保留 ⚠ | — | 2026-09-26 |

**核验结论摘要**：共核验 55 组断言，涉及上百个原子事实（版本号、参数、日期、数字）。其中 **7 组修正**（#2、#4、#13、#16、#20、#32、#41，均已改正文）；9 组确认，同时补强了证据或细化了措辞（#12、#14、#17、#27、#29、#31、#37、#43、#50）；3 组把原文的 ⚠ 项核实为确认（#45、#46、#53）；3 组部分确认（#51、#52、#54）；1 组仍未核验（#55）；删除 0 项。对设计影响最大的修正有三处：一是 Motion 现行默认弹簧并未收敛到 ζ≈0.8–1.0，Deck 动效必须显式传参；二是 DSA 的"界面直达"来自第 27 条第 3 款正文，属于硬性义务；三是 npm 周下载整体低估了约 17%，但各库排序不变，§2.8 的取舍结论不受影响。
