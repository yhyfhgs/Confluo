"""AEA（American Economic Association）adapter 包（design/adapters/aea.md；phase5-plan T5）。

服务 8 刊：AER / AER:Insights / AEJ×4（Macro/Micro/Applied/Policy）/ JEL / JEP（§7 命名
清单）。**capabilities = RESOLVE(offline)**——ENUMERATE 不声明（元数据 100% 委 Crossref
标准 ISSN 路径，D-005；venue YAML `metadata_source: crossref`）；FETCH 本 Phase 不声明
（全文域 `pubs.aeaweb.org` 对 stateless 客户端恒 Cloudflare challenge，连 gold OA 的 JEP
亦然——D-006 禁对抗，声明恒 BLOCKED 的能力不诚实，aea.md §4 论证）。

- `parse`：DOI 双形态容错解析器（`10.1257/{code}.{suffix}`）+ code→venue 8 刊路由表
  （零网络纯函数，§3.2）。
- `adapter`：`AeaAdapter`——`resolve_assets` 全离线（`resolve_offline=True`）：DOI 形态
  解析 + venue `auth.level` 静态分类，订阅刊 raise `NO_ENTITLEMENT`、OA 刊（jel/jep）
  返回空列表，两者均先记一条 deferred 全文 URL 的 DEBUG 观测（供未来 browser-fetch
  通道消费，§3.3）。`healthcheck` 恒 raise `NotImplementedError`（→ canary SKIP，复用
  elsevier_sd/wiley keyless 先例，auth-framework §7）——本 Phase 无网络 FETCH 探针。

**★接缝 A-1**：aea.md §3.3 提及的 `url_strategy=BROWSER`/`AssetPlan.state=deferred`
是否入冻结件由 browser-fetch 通道详设（D1）统一定，本包不新增冻结件（`types.py`
零改动）——`resolve_assets` 因此从不返回非空 `AssetPlan` 列表，全部落 raise/空列表
两分支（结构性诚实：见 adapter.py 模块 docstring）。
"""
