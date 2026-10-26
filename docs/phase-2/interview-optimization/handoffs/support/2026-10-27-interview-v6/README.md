# V6 发布与回传支持资料

源码提交8799b52，V6运行包pin见上级回执。此处包含可读部署/测试工具和非秘密验证元数据；完整原始调用、API状态、合成问答、日志另交附件。不要把没有响应ID的失败虚构为成功调用。

生产工具为 prepare_v6_release.py → activate_v6_release.py → verify_v6_production.py。它们包含本次固定SHA与受控目录，拒绝错误生产基线；不是可以盲目再次执行的通用部署脚本。prepare 使用同一已测后端、最终镜像全量测试及316文件逐项校验；activate 备份、维护窗口指纹核对与保留新镜像的v4d-only回退。

首次并发入口发生MySQL死锁，原捕获保留。resume_v6_skeleton.py 复用同人物与原请求，完整骨架重试通过；complete_v6_draft.py 继续原工作采访完成生成/确认/重复确认。并发缺陷未修复，未做旧镜像同负载对照。

生产验证只有公开API写独立合成家庭，没有数据库夹具。verify_v6_production.py 的DB辅助逻辑只读且校验测试家庭和人物关系。cloud_fixture.py、verify_story_https.py 原版、候选fault工具仅用于旧独立候选，不能把它们的DB目标改成生产或在生产注入provider故障。生产测试脚本重用其判定断言但替换setup与只读审计。

完整附件及先前实时老人模拟附件由用户取得后转交Claude；只有本机路径不代表Claude云端已收到。离线回放仍依赖用户此前的两个缓存包，不使用holdout调参。对话质量结论、功能验证与生产切换状态分别记录。已开始旧题按旧流程答完。
