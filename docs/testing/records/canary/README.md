---
title: Canary 健康矩阵记录目录
status: approved
owner: fable5
updated: 2026-07-22
---

# Canary 记录

本目录存放 `crawler canary --record` 生成的 adapter 健康矩阵快照，供追踪各 adapter 随时间的健康趋势。
文件名 `<YYYY-MM-DD>-canary.md`（本地日期，同日重复执行覆盖同名文件，不追加）；单个文件不带 front matter——见 [canary.py](../../../../src/paper_crawler/canary.py) `render_canary_record` docstring 的理由。
