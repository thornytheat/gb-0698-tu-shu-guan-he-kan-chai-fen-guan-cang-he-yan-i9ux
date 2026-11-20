# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。`/api/5` 另返回 suspensions（每期刊年度的停刊声明与有效停刊范围）、suspension_conflicts（同一期多条起止不同的停刊声明）与逐期裁决（位于 report 年度记录的 issue_decisions：采用实物/停刊/缺期及依据）。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/export/{id}`：唯一证据CSV，含 manifest、suspension_scope、suspension_declaration、issue_decision、result、quarantine 六类行。`GET /health`：存活检查。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
