# 采访 V6 冻结版本

用户于 2026-10-27 将“先接住回答再追问”候选冻结为 **V6**，批准发布真实阿里云并同步共享分支和 main。完整定位见 [release.json](release.json)，生产结果见[发布回执](../../phase-2/interview-optimization/handoffs/2026-10-27-v6-release.md)。

V6 是冻结发布名。为保留用户审阅时的实际行为、缓存与请求审计，内部仍使用 `v3j_v5f` 和独立 `interview_runtime_v3j_v5f_listening`，运行包 pin `1062b6c2158fa8132c0a6ea9541a4dcdbec80f6dd32d21cfda0d816cd2a76487` 不改名重建。模型仍为 DeepSeek v4-pro、thinking disabled，不传 reasoning_effort；83题、顺序与深挖上限保持已测值。

包含原因证据、首答深挖审计、否定补充意图修正与先承接再追问；源提示和构建入口见 [listening 原件](../full-interview-v5/listening/) 与 `scripts/build_interview_v3j_runtime.py --bundle v5f-listening --check`。冻结后继续优化应产生新版本，不回写此包。

已有 v4d / v2 进行中的题继续原流程。不能给已有旧 v5f 进行中题的环境直接换 pin；本次发布前检查生产状态。兼容回退保留新镜像与所有 runtime，开关切回 `v3j_v4d`，已经开始 V6 的题继续 V6。

本地与候选云端各 Ran130、skip1，最终重点8捕获51检查通过；原始全部43次尝试与已知问题另交证据包。V6冻结及发布不代表正式连续三轮质量门槛通过；第三方亲历选点、主观评价及补充邀请节奏仍是下一轮待办。
