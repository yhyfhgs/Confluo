---
title: Adapter 设计 · CVF Open Access
status: review
owner: fable5
updated: 2026-07-20
---

# Adapter · `cvf`

## 1. 定位

- **family**: `open_access`
- **服务 venue**：CVPR、ICCV（奇数年）、WACV（~2020+）；ECCV 仅旧格式镜像（正式版在 Springer，见 catalog 备注）
- **capabilities**: `DISCOVER | ENUMERATE | RESOLVE | FETCH`
- 历史边界：CVF 收录 2013+；更早只在 IEEE Xplore（era 分段：2013 前 → `ieee_xplore`，D-012）。

## 2. 站点勘察摘要

来源：[research/site-survey/cs-ai-conferences.md](../../research/site-survey/cs-ai-conferences.md)（[LIVE] 2026-07-20）：

- 目录：`openaccess.thecvf.com/{CONF}{year}`（如 `CVPR2024`）；按 day/all 分页变体历年略有不同；
- 单篇：`/content/{CONF}{year}/html/{Author}_{Title}_{CONF}_{year}_paper.html`；PDF 在 `/papers/`同名 `.pdf`；supplemental 在 `/supplemental/`；
- 全静态 HTML、无认证、无防护；
- ECCV：CVF 镜像旧格式 `content_ECCV_{year}`，**ECCV2024 新路径实测 403** ⚠ 未核验——设计上 ECCV 的 fulltext_source 默认 springer，CVF 仅作 OA 兜底。

## 3. 各阶段实现方案

- **discover_timeline**：按 VenueSpec `first_year`（CVPR=2013）到当年生成年度 Issue；年度追新即"当年目录页 200 探测"（track 复用）。
- **enumerate_issue**：抓 `{CONF}{year}` 目录（含分日变体，quirks 声明该届目录形态）→ 解析条目链接与标题；`paper_count_claimed`=条目数；与 DBLP 卷数交叉对账（design/08 §6）。identifier：`cvf` scheme（路径 slug）。
- **resolve_assets**：由 html 路径规则改写出 pdf/supplemental URL（纯函数）；`url_strategy=direct`。
- **fetch_asset**：HttpFetcher 直取。
- **healthcheck**：GET 最近一届目录页 200 且条目 >0。

## 4. 限速与礼貌

- 默认 **1 req/2s，并发 1**（NFR-4 保守默认；站点为社区公益托管，克制体量：一届枚举≈数个目录请求）；
- robots ⚠ 实现期复核。

## 5. 失败模式映射

| 现象 | error_class |
|---|---|
| 当年目录 404（未上线） | `gone`（track 候选语义） |
| 目录结构漂移（分日页变化） | `parse` → quirks 按届覆盖目录形态 |
| PDF 路径改写 404 | `gone`（回退从 html 页内解析真实链接） |

## 6. Fixtures 与测试

- **T1 单元**：html→pdf/supp 路径改写矩阵（含 Unicode 作者名 slug）。
- **T3 fixture**：①CVPR 某届目录页 ②单篇 html 页 ③404 页。
- **T5 canary**：CVPR2023 论文数已知答案（±口径差）。
- **验收关联**：AC-2.4（`pull cvpr --year 2023 --filter "diffusion"` 过滤下载）。

## 7. 风险与维护

- 主要风险：各届目录页形态差异（Day1/Day2/all）；对策：quirks 按届声明 + fixture 覆盖两种形态；
- ECCV 新格式路径待核 → 列入实现期勘察清单（catalog 已标 ⚠）。
