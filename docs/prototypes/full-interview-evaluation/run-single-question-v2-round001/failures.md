# 冻结失败记录与缺口索引

批次：run-single-question-v2-round001；模型：deepseek-v4-pro。

本表按原冻结金标准展示未通过项，可能含协议问题或待复核标注；不改写旧分数，也不提供给提取模型。字段预置小问仅说明缺口意图；实际流程由代码根据本题状态选择，已讲清材料但时期未明时只澄清时期。

| 题例 / 本轮 | 未过字段 | 协议错误 | 实际动作 / 目标 | 冻结预期动作 / 目标 |
| --- | --- | --- | --- | --- |
| [DEV-N-f3af6b6947-SK03-01--SK03d / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-N-f3af6b6947-SK03-01--SK03d/turn-000/result.json) | SK03-E4:state |  | ask / SK03-E4 | ['ask'] / ['SK03-E4'] |
| [DEV3-N-c5a5031a87-LT05-01--LT05b / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV3-N-c5a5031a87-LT05-01--LT05b/turn-000/result.json) | LT05-E2:state |  | ready / None | ['ask'] / ['LT05-E2'] |
| [DEV-SOURCES-N-9ff0b2f16e-RV03-01--RV03 / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-SOURCES-N-9ff0b2f16e-RV03-01--RV03/turn-000/result.json) | RV03-E2:state |  | ask / RV03-E2 | ['ask'] / ['RV03-E2'] |
| [DEV-SOURCES-N-6eec6bf458-RV09-01--RV09 / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-SOURCES-N-6eec6bf458-RV09-01--RV09/turn-000/result.json) | RV09-E1:state |  | ready / None | ['ask'] / ['RV09-E1'] |
| [DEV-SOURCES-N-6eec6bf458-RV09-01--RV09b / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-SOURCES-N-6eec6bf458-RV09-01--RV09b/turn-000/result.json) | RV09-E2:state,content_0,verbatim_evidence,evidence_fact_0,scope_subject,relation_evidence_valid,relation_evidence_0 | RV09-E2:literal_value_must_be_one_contiguous_source_span | invalid / None | ['ready'] / [None] |
| [DEV-SOURCES-N-6eec6bf458-RV09-01--RV09c / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-SOURCES-N-6eec6bf458-RV09-01--RV09c/turn-000/result.json) | RV09-E3:state |  | ready / None | ['ask'] / ['RV09-E3'] |
| [DEV-SOURCES-N-6eec6bf458-RV06-01--RV06b / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/DEV-SOURCES-N-6eec6bf458-RV06-01--RV06b/turn-000/result.json) | RV06-E2:state |  | ready / None | ['ask'] / ['RV06-E2'] |
| [ROOT-N-6eec6bf458-CH03--CH03 / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/ROOT-N-6eec6bf458-CH03--CH03/turn-000/result.json) | CH03-E3:state,content_0,verbatim_evidence,evidence_fact_0,scope_subject,relation_evidence_valid,relation_evidence_0 |  | ask / CH03-E3 | ['ready'] / [None] |
| [ROOT-N-6eec6bf458-CH03--CH03b / 0](/Users/student03/Documents/ChatGPT/ai memory/docs/prototypes/full-interview-evaluation/run-single-question-v2-round001/cases/ROOT-N-6eec6bf458-CH03--CH03b/turn-000/result.json) | CH03-E2:state |  | ready / None | ['ask'] / ['CH03-E2'] |

逐项原话、目标、小问题与失败维度见同名JSON；全部原始模型响应仍在各题例目录。
