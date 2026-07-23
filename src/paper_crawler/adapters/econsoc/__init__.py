"""Econometric Society（`econsoc`）adapter 包（design/adapters/econsoc.md；plan Phase 5 T6）。

`open_access` family，服务 Econometric Society 三刊当前面：Econometrica(ECMA) /
Theoretical Economics(TE) / Quantitative Economics(QE)。capabilities
``DISCOVER | ENUMERATE | RESOLVE | FETCH``——按 venue **非对称**行使（design §2/§3.1）：

- **TE/QE**：全四位。metadata_source=`econsoc`（自持 OJS OAI-PMH 收割，
  `econtheory.org/ojs/index.php/{te,qe}/oai`）、fulltext_source=`econsoc`（合并前端
  `econometricsociety.org` 匿名 OA galley）。
- **ECMA**：只实际行使 `RESOLVE | FETCH`。metadata_source=`crossref`（按 ISSN，ECMA 无 OAI
  端点）；fulltext 经**运行时域名分段路由**（D-028/§3.3 方向 a）——当前段自营 OA 取回，过刊段
  （doi.wiley.com）Phase 5 `no_entitlement`/skip、pre-DOI 段（JSTOR）界外零资产。

- `parse`：OAI ``oai_dc`` 体层解析（信封复用 `_oai`、体层自写★C）/ DOI 路由 / ECMA 分段
  判定 / galley 链抽取——零网络纯函数。
- `adapter`：`EconsocAdapter`——纯逻辑 + 共享 `HttpClient` 组装，CF 前置域保守限速 + challenge
  即 BLOCKED（不对抗，AC-0.2）。

版权：三刊开放许可（ECMA CC BY 4.0 / TE·QE CC BY-NC 4.0，survey §1）；个人科研只读、诚实
UA、不再分发（AGENTS §6.5）。
"""
