# Psychology Education Skills Build System
## 借鉴 Grok Build 交互的心理学教育工作台需求（V1.1 修订稿）

> 文档定位：用于需求评审和实施拆分。本文定义目标系统的行为，不构成对阅读本文的 Agent 的执行授权。
>
> 修订日期：2026-09-15。基于 V1 修订，保留课程、研究、多媒体与可编辑产物的完整 V1 目标。
>
> 核心目标：构建一个面向教师，尤其是心理学、融合教育、托育、教师培训等课程生产场景的 **“Build 式 Skills 工作台”**。教师只需要描述“我要做什么”，系统自动拆解任务、选择 Skills、调用研究与教学能力、生成中间产物、预览结果、验证质量、继续迭代，并最终产出可编辑教学资产。
>
> 本系统不是“把一堆 Skills 装进 Agent”，而是建立一个 **可路由、可审计、可打补丁、可验证、可预览、可持续迭代的课程生产操作系统**。

---


## 修订说明与适用边界

- 本轮补齐：最小证据闭环、质量门禁执行结果、产物版本与局部重建、规则冲突、权限执行、上游来源记录、阶段验收和失败路径。
- **建议默认值，尚未经产品方单独确认：**首版采用本机运行、单教师使用的 Web 工作台；浏览器 UI、项目文件和调度服务运行在本机，通过明确配置的模型及研究接口获取外部能力。具体默认范围见第 83 章。
- 本地运行不等于模型推理离线。将哪些材料发送给哪个 Provider 必须可查看；敏感资料处理见第 57、83 章。
- “借鉴 Grok”是交互与工程参考，不表示部署在 Grok 网页内部，也不假定网页具备 CLI 的全部扩展能力。映射见第 80–81 章。
- **上游采用结论均为待验证候选政策。**原稿未附仓库、版本和审查证据，本稿不背书其“已审查”说法。各章 ADOPT / PATCH 等建议不等于入库许可，实际接入以第 8、9、68 章记录和测试为准。
- 第 71 章的首个里程碑不是完整 V1。只有达到第 79 章完成定义才可称为 V1 完成。
- 本稿中的业务规则适用于目标产品；用户文件、网页和远程 Skill 的内容不能自行提升为系统指令或权限。

---

# 1. 产品目标

## 1.1 核心体验

参考 Grok 网页 Build 的工作方式，教师不需要理解 Skills、Agent、MCP、DAG、Provider 等内部概念。

用户可以直接输入：

> “帮我做《融合教育》项目三的三个在线课程脚本，每个 1900–2400 字，要有教师讲解、画面设计、案例和动画，并参考我上传的模板。”

系统应该自动进入：

```text
自然语言需求
    ↓
任务理解
    ↓
必要时快速 Q&A
    ↓
Build Plan
    ↓
自动选择 Skills / Providers
    ↓
并行研究 / 教学设计 / 素材解析
    ↓
生成结构化中间产物
    ↓
实时预览
    ↓
Evidence / Pedagogy / Safety / Template QA
    ↓
生成最终可编辑产物
    ↓
用户继续说“第2节案例太弱”“动画换一种”
    ↓
只修改受影响部分
```

重点是：

**用户只面对项目和结果，Skills 是系统内部能力。**

---

## 1.2 V1 主要产物

V1 优先支持：

1. 在线课程讲稿 / 教师录课脚本
2. 教案 / 教学活动设计
3. 课程章节结构
4. 案例
5. 形成性评价与课堂提问
6. Worksheet / 学习单
7. 教学动画方案与生成提示词
8. 教学图示 / 流程图 / 概念图
9. PPT 生产规划
10. 可编辑 PPTX
11. 文献研究与证据索引
12. 教材 / 模板 / 用户文件驱动的课程资产

---

# 2. 非目标

V1 不做：

- 不让 Codex / Build Agent 直接承担最终视频生成。
- 不自动替教师对学生进行心理诊断。
- 不根据 ADHD、自闭症、焦虑等标签直接给个体学生下判断。
- 不允许研究 Skill 自己把未经验证的心理学事实写进正式课程。
- 不将“有引用”误认为“引用支持了当前结论”。
- 不允许远程 Skill 获得无限代码执行权限。
- 不让 CNKI 登录账号密码进入 Agent Prompt、日志或项目文件。
- 不让 PPT Skill 直接从原始论文跳到“课程 PPT”，必须经过教学设计。
- 不以“生成更多动画”为质量目标。
- 不允许 Skill 名称或 README 代替源码审计。

---

# 3. Grok Build 式交互模型

## 3.1 Describe → Build

主入口只需要一个输入框。

用户描述最终目标，例如：

> “按这个模板写第八章四个课程脚本。”

Build Engine 自动识别：

- 任务类型
- 文件输入
- 用户模板
- 输出形式
- 学科领域
- 学习对象
- 字数
- 是否需要案例
- 是否需要动画
- 是否需要研究
- 是否需要 PPT
- 是否需要最终文档

系统不能要求用户先选择：

```text
backwards-design
dual-coding
PCK
UDL
hinge-question
scientific-review
```

这些应该自动路由。

---

## 3.2 Plan Mode

复杂任务默认生成可查看的 Build Plan。

例如：

```text
01 解析模板
02 提取课程结构
03 识别每节学习目标
04 建立需要核验的心理学 Claim
05 调用研究层
06 形成 Evidence Artifacts
07 教学设计
08 案例设计
09 判断是否需要动画
10 生成脚本
11 UDL / Evidence / Template QA
12 导出 DOCX
```

Plan 必须支持：

- 查看
- 单步评论
- 修改顺序
- 禁用某一步
- 锁定某一步
- 重新运行某一步

### Plan 不应暴露内部低级实现

用户看到：

> “核验核心心理学结论”

而不是：

> “run grounded-citations → sci-extract → pck-developer”。

---

# 4. 快速 Q&A

参考 Grok Build 的 Q&A 机制。

当需求存在会显著改变产物的歧义时，可给用户 2–4 个快速选项。

例如：

```text
课程主要面向：

A. 高职师范学生
B. 本科师范生
C. 在职教师
D. 自定义
```

但是：

- 已经从用户文件或上下文得到的信息不能重复询问。
- 能安全推断的内容直接采用默认值。
- 不能为了“完整”而把 Build 变成问卷。
- 用户可以选择“按你判断”。

---

# 5. Live Build Workspace

每个课程任务形成一个 Project Workspace。

建议结构：

```text
/project
├─ project.yaml
├─ requirements.md
├─ sources/
├─ templates/
├─ evidence/
├─ curriculum/
├─ pedagogy/
├─ cases/
├─ assessments/
├─ media/
│  ├─ diagrams/
│  ├─ animations/
│  └─ storyboard/
├─ presentation/
├─ outputs/
├─ qa/
├─ memory/
└─ runs/
```

用户不一定看到文件树，但系统必须在内部保持这些 Durable Artifacts。

---

# 6. Build 中间产物

重要中间结果必须持久化；聊天记录不是系统状态的唯一来源。各产物的 ID、版本、依赖和提交规则统一见第 48 章。

## 6.1 Project Requirements Artifact

记录课程名称、章节、学习对象、语言、输出类型、字数规则、必需组成、禁用词、模板约束和用户要求。每条要求附来源、作用范围及确认状态，区分用户明确要求、材料提取结果和系统建议默认值。

## 6.2 Learning Design Artifact

记录学习目标、知识类型、先备知识、理解难点、迁移目标、评价证据和教学顺序。对预测的理解难点标记依据，不把模型假设写成已证实的学习规律。

## 6.3 Evidence Artifacts

采用三个有关联的记录类型，支持一个结论对应多份证据以及同一来源支持多个结论：

| 记录 | 必需信息 |
|---|---|
| Claim | 稳定 ID、版本、结论文本、结论类型、适用人群、使用位置 |
| Source | 稳定 ID、来源类型、标题、URL/DOI 等标识、发布日期（未知须标明）、获取时间、实际取得的内容层级、快照位置及 SHA-256 |
| Evidence Assessment | Claim 版本、Source 版本、原文片段及位置、支持关系、研究设计/证据强弱的说明、适用范围、局限、不确定性、评估方式及版本、核验时间、核验结果 |

Claim 类型枚举：descriptive / correlational / predictive / causal / mechanistic / theoretical / speculative。

支持关系枚举：direct / indirect / contextual / contradictory / insufficient。它表示一条证据与一个结论的关系，不等于最终批准状态。

核验结果枚举：PENDING / SUPPORTED / QUALIFY_REQUIRED / UNSUPPORTED / DISPUTED / HUMAN_REVIEW_REQUIRED。仅 SUPPORTED 且依赖版本仍有效的事实性结论可进入正式课程；其他结果按第 63 章处置。

这些枚举是字段的候选值，不是要求记录同时填入全部值。证据强弱须说明依据，不产生未经校准的可信概率分数。

实际取得的内容层级区分 metadata / abstract / full_text / user_excerpt。只有摘要时不能声称核验了全文的方法、结果或机制；用户摘录应保留其来源限制。

## 6.4 内容与证据的对应

- 正式脚本、评价答案、图示标签和 PPT 中可核验的事实性陈述，关联到 Claim 版本；改写不得扩大其强度或适用范围。
- 教学安排、明确标注的虚构案例和开放反思问题可以没有研究引用，但其中新增的事实性陈述仍须核验。
- Source 快照和哈希用于定位核验所依据的内容，不表示该内容天然真实。无法保存全文时保留允许保存的定位信息和片段，并标明核验限制。
- 评估记录保留相互矛盾的证据，不用新记录覆盖不利证据。Claim 修改后必须产生新版本并重新核验。

**有 citation 不等于 Claim 已被支持；有 Evidence 文件也不等于通过 Evidence Gate。**

---

# 7. Skills Package 规范

每个 Skill 是独立目录，包含 SKILL.md、schema.json，以及实际需要的 references / scripts / examples / tests / patches。没有可用内容的目录无需预建。

SKILL.md 描述用途、输入输出、教学约束与调用方式；schema.json 是结构化输入输出的唯一类型来源。

自有 Registry 记录：name、description、version、domain、risk_level、user_invocable、auto_invocable、input_schema、output_schema、requires、produces、allowed_providers、allowed_tools、network_access、filesystem_access、external_side_effects、requires_evidence_gate、review_status、execution_policy。

- 这些字段属于本系统规范，不能假设第三方宿主会解释或执行。
- 工具及网络权限是声明，由第 55–56 章的调度层和沙箱执行；将字段写入 Prompt 不构成隔离。
- 若导出为第三方 Skill，适配器负责字段映射、类型校验和不支持能力的明确报错，不得把被宿主忽略的字段显示为“已生效”。
- Skill 的理论依据在 references 和审查记录中说明，不以 Skill 级别的 evidence_strength 代替逐条 Claim 核验。
- 工具调用、自动调用和显式调用遵守同一权限及质量规则。

---

# 8. Skill 生命周期与入库状态

每个候选 Skill 分别审查 metadata、prompt、examples、references、scripts、网络、文件、外部操作、理论主张及 schemas。

状态拆分为独立维度：

| 字段 | 值 | 含义 |
|---|---|---|
| review_status | UNVERIFIED / IN_REVIEW / APPROVED / REJECTED | 是否完成来源与内容审查 |
| adoption_decision | ADOPT / PATCH / REFERENCE_ONLY / DISABLED | 如何使用该组件 |
| role | REASONING_SKILL / ACTION_SKILL / PROVIDER | 系统中的职责 |
| execution_policy | NO_CODE / SANDBOX_ONLY / TRUSTED_RUNNER | 代码执行条件 |
| enabled_by_default | true / false | 默认是否参与路由 |

运行资格：review_status 为 APPROVED，版本及本地 Patch 基准匹配，必要检查通过，且当前调用满足 execution_policy。REFERENCE_ONLY、DISABLED 不进入运行路由。

未知来源默认为 UNVERIFIED、默认不启用。旧文中的 OPTIONAL、REWRITE、ADOPT CONDITIONAL 等为处理建议，不能作为 Registry 状态直接写入。

UNVERIFIED → IN_REVIEW → APPROVED 或 REJECTED。上游内容或补丁变化后，新版本重新审查；原批准版本可继续按固定版本运行，除非被明确撤销。

---

# 9. Skills Manager

`skills-mgr` 为待核实候选来源；无论是否采用该实现，系统都必须具备来源 allowlist、路径检查、文件数量/体积限制、隔离缓存、SHA-256、原子发布、版本 pin 和 Local Patch。

接入流程：候选来源 → 隔离下载 → 来源/许可/代码/Schema/领域审查 → 本地 Patch → 测试 → Approved Registry。

每项记录 repository_url、upstream_path、commit_sha、license、实际文件哈希、reviewed_at、reviewed_by、审查证据位置、测试结果及采用政策。没有源码或审查记录，不宣称“已审计”。

- 远程内容获取与脚本运行分开；下载后不执行安装钩子或脚本。
- 校验实际文件路径和解包结果，拒绝越出隔离目录的路径及链接。
- 只发布完整、校验通过的版本；失败时保留上一个已批准版本。
- 上游 SHA 与 Patch 基准不一致时停止新版本合成，不猜测套用补丁，也不静默改用未补丁版本。
- 教学 Prompt 也须领域审查；NO_CODE 不表示内容可信。

---

# 10. Local Patch Layer

不 fork 教育 Skill 仓库。

使用：

```text
Upstream Skill
   +
Local Patch
   ↓
Runtime Skill
```

Patch 必须记录：

```yaml
upstream_repo:
upstream_path:
upstream_sha:
patch_version:
patch_reason:
reviewed_by:
tests:
```

---

# 11. Psychology Education Router

按任务类型、知识类型和风险选择教学路径。关键词可用于候选检索，不能独立决定正式教学策略。

原稿关于某些 suggest_skills 实现只做关键词评分的说法缺少可追溯审查记录；本稿将其作为待核实项，不据此评价所有同名实现。

## 11.1 任务类型

research / curriculum / lesson-design / script / case / assessment / diagram / animation / presentation / review。

## 11.2 知识类型

concept / distinction / principle / procedure / skill / observation / case-analysis / reflection / attitude / critical-thinking / research-literacy / transfer。

## 11.3 教学策略候选

| 知识类型 | 候选策略 |
|---|---|
| Concept | explicit instruction、dual coding、hinge question、retrieval |
| Distinction | 对比案例、错误案例、hinge question |
| Procedure / Skill | worked example、fading、练习、反馈 |
| Observation | worked example、事实与判断对比、案例、错误分析 |
| Reflection / Attitude | 引导反思、视角转换、结构化讨论、案例 |

这些是候选映射，不是每节课必须执行的固定链。每次路由保存所依据的学习目标、知识类型、约束和选择理由。

信息不足且会改变教学策略时发起简短 Q&A。显式 Skill 调用允许高级用户指定能力，但仍受输入、权限及 Gate 约束。

---

# 12. Research Engine

推荐结构：

```text
User Material
Web
Academic Search
Paper Harvester
CNKI Connector
    ↓
Raw Evidence
    ↓
Semantic Analysis
    ↓
Psychology Evidence Gate
    ↓
Evidence Artifacts
    ↓
Curriculum / PCK / Authoring
```

---

# 13. Scientific Literature Review

Scientific Literature Review 为待验证研究框架候选；接入时必须增加 Psychology Profile。

## 13.1 原版不足

原稿将候选研究框架描述为偏 biomedical；该判断待上游版本核实。心理学 Profile 不应只依赖：

- PubMed
- Embase
- GEO
- 等

心理学 / 教育场景的检索 Profile 应能登记以下来源；实际可用性取决于已配置的连接器与访问条件，未接入来源明确标为不可用，不承诺首版全部开通：

```text
PsycINFO
ERIC
PubMed
Crossref
OpenAlex
Semantic Scholar
Google Scholar / Web Search fallback
CNKI optional
```

---

## 13.2 检索必须留下日志

```yaml
database:
query:
filters:
date:
results_count:
included:
excluded:
reason:
```

---

# 14. sci-extract 候选使用政策

原稿未提供源码版本与审查记录。以下为组件级接入建议，实际代码行为待核实：

| 组件 | 候选处理 |
|---|---|
| Prompt Paper Analysis | 领域审查和 Patch 后评估接入 |
| Paper Harvester | 作为数据获取 Provider，脚本限沙箱 |
| Python Insight Extractor | 默认不接入；重新审查后再决定 |
| Figure Downloader | 默认不启用；涉及下载须满足操作授权 |

任何基于字段存在、字段长度、章节命中等完整性检查生成的 coverage score，只能标为提取完整性提示，不能显示为事实置信度或支持强度。它也不能替代 Evidence Gate。

---

# 15. Paper Harvester

保留：

- DOI
- PMID
- PMCID
- arXiv
- title
- query

以及：

- Crossref
- OpenAlex
- Semantic Scholar
- PubMed
- Unpaywall
- WoS
- Scopus
- Springer
- Elsevier

等 metadata 聚合能力。

但它只是：

> Data Acquisition Provider

不是：

> Truth Provider

---

# 16. Citation Ledger

可吸收 Hermes `grounded-citations` 的思想。

用于：

- source registry
- exact quote
- snapshot
- source hash
- citation numbering

但是 Citation Ledger 不能取代 Evidence Gate。

结构：

```text
Citation Ledger
      ↓
确认“引用真实存在”

Psychology Evidence Gate
      ↓
确认“引用是否支持当前结论”
```

---

# 17. CNKI Connector

CNKI 不属于 Research Core。

定位：

> Optional Chinese Evidence Connector

---

## 17.1 可自动使用

允许：

```text
CNKI Search
CNKI Result Parse
CNKI Paper Detail
```

---

## 17.2 不稳定能力

Advanced Search 不能依赖：

```javascript
selects[14]
selects[15]
```

这类 DOM 位置索引作为唯一定位方法。

需要优先：

```text
id
name
label
semantic selector
```

如果 selector verification 失败：

```text
FAIL
```

而不是“猜测执行成功”。

---

## 17.3 登录

禁止硬编码学校。

禁止：

```text
National University of Defense Technology
```

或任何固定机构。以上为禁止硬编码的示例，不表示本稿已经确认某个上游实现存在该代码。

正确方式：

```text
用户选择机构
     ↓
浏览器页面
     ↓
用户手工输入凭据
```

账号、密码：

- 不进入 Prompt
- 不写文件
- 不记录日志
- 不保存 Memory
- 不传给 Subagent

---

## 17.4 CNKI Action Skills

以下属于 ACTION：

```text
Download
Zotero Export
```

必须用户明确请求才执行。

---

## 17.5 Zotero

允许默认：

```text
metadata only
```

PDF Attachment：

```text
OFF by default
```

如启用：

- 文件大小限制
- MIME 检查
- PDF magic check
- 最大下载时间
- 下载目标显式
- 不允许无限内存读取
- Cookie 不写日志

---

# 18. Curriculum Engine

主链建议：

```text
Backwards Design
     ↓
Competency Unpacker
     ↓
Learning Progression
     ↓
Curriculum Alignment
```

---

# 19. Learning Progression Builder

可用，但需要 Patch。

问题：

它容易把“模型认为常见的卡点”写成：

> 已被实证证明的常见学习路径。

必须标记：

```yaml
progression_basis:
  - evidence_supported
  - source_derived
  - instructor_provided
  - model_hypothesis
```

`model_hypothesis` 不得进入正式教材事实部分。

---

# 20. Pedagogical Content Knowledge Developer

PCK 负责“怎么教”，消费 Learning Design 和有效的 Evidence Artifacts。

可以设计类比、例子、解释、理解难点假设和表达方式；不得自行发明心理学事实、神经机制或“研究表明”的出处。

正式内容生成前，由 before_skill 中针对 PCK 的校验确认所引用 Claim 为 SUPPORTED、版本有效、范围匹配。不是仅检查 Evidence 文件存在。

生成过程中发现必须新增的事实时，登记为 PENDING Claim 并返回研究流程。草稿可显示待核验占位和原因，不能将其伪装为正式事实。生成后的事实性陈述还须通过第 63 章核验。

---

# 21. Explicit Instruction

作为核心教学 Provider。

适用于：

- 明确定义
- 程序性技能
- 观察训练
- 概念辨析
- 操作流程

但 Router 不能所有课程都强制 Explicit Instruction。

---

# 22. Worked Example / Fading

`worked-example-fading` 可以进入主能力库。

优先用于：

- 观察记录
- 事实与判断区分
- 个案分析
- 技能流程
- 结构化写作
- 操作任务

不自动用于：

- 价值澄清
- 开放反思
- 情绪表达
- 伦理判断

---

# 23. Hinge Question

保留概念，作为形成性评价能力候选。原稿对上游示例计算错误的判断缺少源码定位，不作为已复核事实。

- 上游 examples 在独立审查前不得成为可信 few-shot。
- 题目、答案、干扰项和解析共同校验；涉及计算须独立重算。
- 题目测量的目标应与 Learning Design 对应。
- 学科事实与答案中的事实性解释必须通过 Evidence Gate。

---

# 24. Cognitive Load Analyser

候选处理建议（实际入库待审查）：

> PATCH

保留：

- intrinsic / extraneous / germane 分析思路
- split attention
- redundancy
- element interactivity
- segmenting
- signalling

删除或降级：

- 伪精确 4–7 元素限制
- 把 load 当成可以精确打分的单一数字
- 将争议理论说成确定规律

输出应该是：

```text
LOW / MEDIUM / HIGH
+
原因
+
不确定性
```

而不是：

```text
认知负荷 = 7.8
```

---

# 25. Dual Coding Designer

候选处理建议（实际入库待审查）：

> ADOPT

它应成为 Multimedia Engine 核心。

核心原则：

```text
视觉必须承担知识功能
```

而不是：

```text
PPT 上放一张好看的插图
```

视觉作用分类：

```text
structure
comparison
sequence
causality
spatial relation
state change
hierarchy
example
counterexample
```

---

# 26. Inclusive Design

真正纳入系统的是教育 UDL Skills，而不是 HTML Accessibility。

主链：

```text
Design Before:
UDL Barrier Anticipator

Design:
UDL Options Designer

After Draft:
UDL Lesson Auditor
```

---

# 27. UDL Barrier Anticipator Patch

原版中的：

```text
specialist_referral_barriers
```

改为：

```text
individual_support_review_flags
```

禁止模型直接：

> “该学生需要转介”

只能：

> “该障碍可能无法仅通过通用课程设计解决；如已有专业评估、个别化教育计划或支持方案，应依据已有资料由教师及相关专业人员判断。”

---

# 28. UDL Options Designer

候选处理建议（实际入库待审查）：

> ADOPT WITH LIGHT PATCH

必须坚持：

```text
same learning goal
same core cognitive demand
different access path
```

不能把：

> 更简单的任务

伪装成：

> 更无障碍的任务。

---

# 29. UDL Lesson Auditor

候选处理建议（实际入库待审查）：

> ADOPT

最终检查：

- Engagement barriers
- Representation barriers
- Action / Expression barriers
- Constraints
- What to keep
- Priority modifications

不能变成“UDL 打勾表”。

---

# 30. Psychology Safety Layer

所有心理学教学内容必须经过：

```text
Psychology Safety QA
```

检测：

- 心理诊断措辞
- 过度病理化
- 标签化
- 单因果解释
- 神经科学过度简化
- 将相关说成因果
- 将理论模型说成已证事实
- 将群体趋势套到个体
- 把自助策略说成治疗
- 不恰当的 specialist referral

---

# 31. Trauma-Informed Skill

候选处理建议（实际入库待审查）：

> DISABLED BY DEFAULT

原因：

- 容易神经科学过度简化
- 容易把行为直接归因为 trauma
- 容易越过教师教学边界

只能：

```text
explicit manual enable
```

而且输出必须通过 Psychology Safety QA。

---

# 32. PERMA / Flow 等

定位：

> Optional Domain Plugins

不能成为心理学课程默认解释框架。

---

# 33. Implementation Intention / Self-Efficacy / Motivation Diagnostic

可以保留理论骨架。

但所有“diagnostic”措辞统一修改为：

```text
instructional hypothesis
learning-design hypothesis
```

禁止：

> “这个学生缺乏自我效能感。”

改为：

> “当前任务表现可能与自我效能相关因素有关，但现有信息不足以作个体判断。”

---

# 34. Multimedia Engine

结构：

```text
Teaching Artifact
      ↓
Cognitive Load Analysis
      ↓
Dual Coding
      ↓
Media Router
      ↓

┌────────────┬────────────┬────────────┐
│    Text    │  Diagram   │ Animation  │
└────────────┴────────────┴────────────┘
```

---

# 35. Media Router

对每个知识点判断：

```yaml
knowledge_function:
temporal_dependency:
spatial_dependency:
comparison_dependency:
persistence_need:
learner_interaction_need:
recommended_medium:
```

---

# 36. Diagram Design

参考 `diagram-design` 的：

> Knowledge Semantics → Visual Grammar

不继承原仓库固定技术风格。

教育图示支持：

```text
concept relationship
comparison
sequence
causality
timeline
hierarchy
state
part-whole
evidence map
case flow
observation flow
```

---

## 36.1 心理学视觉 Profile

例如：

### 概念辨析

```text
split comparison
Venn
contrast table
boundary example
```

### 观察技能

```text
event timeline
fact → interpretation separation
observation flow
```

### 理论比较

```text
parallel framework
matrix
layered model
```

### 因果与相关

```text
causal diagram
confounder diagram
correlation-vs-causation contrast
```

### 个案

```text
case timeline
evidence map
decision flow
```

---

# 37. Educational Animation Gate

借鉴 `find-animation-opportunities` 的“先拒绝动画”思想，但重写为教育版本。

动画必须通过：

```text
1 Knowledge Function
2 Temporal Necessity
3 Static Alternative
4 Cognitive Load
5 Narration Synchrony
6 Persistence Need
7 Generation Feasibility
8 Teaching Value
```

---

## 37.1 判断规则

如果：

```text
一张静态图能更清楚
```

则：

```text
REJECT ANIMATION
```

如果知识本身是：

- 时间变化
- 动态过程
- 逐步累积
- 状态转移
- 因果链展开
- 错误与正确过程对比

则可以进入 Storyboard。

---

# 38. Educational Storyboard

不直接使用影视 Storyboard Skill。

保留其：

- shot ID
- continuity
- targeted fix
- 小上下文文件化

重写字段：

```yaml
shot_id:
learning_goal:
narration:
visual_state_start:
visual_change:
visual_state_end:
labels:
on_screen_text:
duration:
knowledge_function:
cognitive_load_note:
continuity_from:
continuity_to:
```

不要求：

- 演员表演
- 服装
- cinematic lighting
- 情绪镜头

除非课程确有需要。

---

# 39. 视频边界

Build 系统做到：

```text
Educational Storyboard
        ↓
Video Generation Prompt
        ↓
STOP
```

后续视频模型由：

- Grok
- Veo
- Higgsfield
- MiniMax
- 其他外部视频系统

完成。

V1 不承担最终视频渲染。

---

# 40. Video Production Skill

原开源 `video-production-skill`：

> DISABLED AS RUNTIME

原因：

它会实际调用：

- 外部 API
- Image Generation
- TTS
- ASR
- FFmpeg

这些都越过本项目 V1 边界。

只提取方法论：

- 术语先白话
- 简化后再 fact-check
- 画面与讲解同步
- 真实证据优先

---

# 41. Presentation Composer

采用 `scholar-ppt-cn` 的生产思想。

但定位：

> Presentation Composer

不是：

> Curriculum Designer

---

# 42. PPT 前置链

必须是：

```text
Curriculum
   ↓
Pedagogy
   ↓
Teaching Artifact
   ↓
Media Router
   ↓
Slide Communication Plan
   ↓
Presentation Composer
```

禁止：

```text
Paper
 ↓
PPT Skill
 ↓
Course PPT
```

---

# 43. Evidence Index

PPT 前先形成：

```yaml
asset_id:
source:
figure_or_table:
content_summary:
clarity:
teaching_relevance:
role:
  - primary
  - support
  - unused
resolution:
risk:
```

---

# 44. Production Planning Table

每页至少：

| 字段 | 内容 |
|---|---|
| Slide | 页码 |
| Title | 标题 |
| Narrative Section | 教学段落 |
| Communication Task | 这一页要让学生理解什么 |
| Source Asset | 使用什么证据/素材 |
| Asset Geometry | 宽图/高图/表格等 |
| Core Message | 核心信息 |
| Layout Archetype | 版式 |
| Density | 信息密度 |
| Asset Handling | 保留/拆分/放大 |
| Risk | 事实/可读性/翻译等风险 |

---

# 45. PPT QA

必须真正检查：

- PPTX 能否打开
- 中文字体
- 粗体
- 溢出
- 遮挡
- 图像清晰度
- 图表标签
- 页码
- 标题系统
- 连续页面是否模板重复
- 是否出现内部术语
- 引用是否对应
- 教学逻辑是否连续

---

# 46. Build Preview

主要产物产生可预览草稿后立即展示：脚本使用结构化 Markdown 预览，PPT 使用真实文件渲染的缩略图，图示使用 SVG，动画使用分镜预览，评价题分教师/学生视图。

预览明确显示草稿、待核验、检查失败、已通过及已过期状态，不将“生成完成”等同于“验收通过”。

用户可选中案例、段落、评价题或幻灯片提出修改，使用稳定 ID 定位。只重建依赖受影响的产物；全局术语或模板规则变更可能合法地影响全项目，须先展示影响范围，不能承诺任何修改都只改变一个文件。

替换一个案例时，可重建相关脚本段落、评价题、分镜或幻灯片；不相关产物保持版本与内容不变。每次局部修改仍检查必要的章节或整份输出约束，例如术语一致性和总字数。

---

# 47. Diff 与修改提交

每次修改形成候选变更集，包含修改原因、内容 Diff、受影响产物、Gate 结果和预期替代的已接受版本。

- Accept：仅在没有版本冲突且必需检查通过时，将整组相关候选版本提交为已接受版本。
- Reject：丢弃候选变更对当前版本的影响，保留原已接受版本；候选记录保留在运行历史中。
- Edit：基于候选内容继续生成新候选，重新执行受影响检查。
- Accept 等用户操作不能绕过质量门禁。允许保留或下载明确标识的草稿，见第 62 章。

局部重建的下游结果不能在接受前混入正式产物。生成失败或被拒绝时，不留下半套已提交的新版本。

教师在工作台中的直接编辑同样进入候选版本与检查流程。V1 不承诺自动双向同步在外部 Office 中修改过的导出文件。

---

# 48. Artifact 版本与依赖图

由本系统 Orchestrator 维护产物依赖，不依赖上游 Registry 是否提供 chain_edges。

每个产物版本至少记录 artifact_id、artifact_type、revision_id、content_hash、内容位置、produced_by_run、上游产物版本、Skill/Provider 版本、相关规则版本和创建时间。已保存的 revision 不原位覆盖。

依赖边记录源产物版本、消费步骤、输入映射、产生的目标产物及所需校验。案例、脚本段落、题目、分镜和单页 PPT 等可被独立修改的单元必须可定位。

## 48.1 失效与锁定

- 上游内容或规则变化时，沿实际依赖标记下游为过期，并按顺序重建；只改变显示顺序不自动作废无关证据。
- 锁定表示不能自动修改，不表示永远有效。锁定节点依赖过期时显示冲突，并阻止其作为有效产物正式导出。
- 用户可解锁重建，或撤销上游候选修改。不能强制把旧的核验结果挂到新内容上。

## 48.2 并发与持久化

- 每次运行绑定启动时的输入和基线版本。提交前比较当前基线；旧任务完成时若基线已变化，结果进入历史候选，不能覆盖较新版本。
- 多个 Agent 通过不可变输入版本和候选输出协作，不直接并发覆盖同一文件。
- 内容先写临时文件，校验并完成后再发布版本及变更集索引；失败恢复不得出现索引指向半写入产物。
- Gate 结果绑定具体产物和规则版本；内容、证据或相关规则改变后，不复用已失效的通过结果。
- 取消、失败、重启和重试规则见第 84 章。

---

# 49. Schema Contract

Canonical JSON Schema 是本系统业务输入输出的唯一类型来源，Tool、UI 和 Prompt 适配器均由它生成或校验。

区分业务类型和传输表示：某协议要求字符串参数时，由适配器显式序列化/反序列化，再按 Canonical Schema 校验；不能要求所有宿主在传输层都保留同一类型，也不能把未经解析的字符串当数组、整数或布尔值。

测试覆盖数组、整数、布尔值、缺失值和非法参数在支持入口间的一致语义。类型错误应明确报错，不用猜测转换掩盖错误。

本章规定自有 Runtime 行为，不将原稿中未指明版本的 MCP 实现描述当作已审查缺陷。

---

# 50. Subagents

可并行安排没有未满足依赖的研究、模板解析、课程结构提取等任务。案例、教学解释和评价题若依赖已核验事实，应等待对应证据通过，不能把章节示意中的所有角色同时无条件启动。

每个 Subagent 仅获得 Task Brief、相关产物的具体版本、已批准 Skills、允许工具、适用项目规则和 Output Contract。

- 相关信息按任务需求提供，不传播整个聊天历史、凭据或不相关学生资料。
- 所有工具访问经统一权限执行层；不能依靠角色 Prompt 限制实际文件和网络访问。
- 输出进入候选产物，经 Schema、权限和质量检查后合并，遵守第 48 章的版本冲突规则。
- 某个 Agent 失败时，已完成的独立任务保留；依赖它的节点暂停。首版并行度和预算见第 83–84 章。

---

# 51. 推荐 Subagents

## Research Agent

只能生产：

```text
Evidence Artifacts
```

---

## Curriculum Agent

只能：

```text
Learning Goals
Progression
Alignment
```

---

## Pedagogy Agent

消费：

```text
Learning Design
Evidence Artifacts
```

输出：

```text
Teaching Strategy
```

---

## Script Agent

输出：

```text
Teacher Narration
Visual Cue
Case
Interaction
```

---

## Media Agent

只能决定：

```text
text / diagram / animation
```

---

## QA Agent

不能写新事实。

只能：

```text
flag
explain
propose correction
```

---

# 52. Skill Auto Invocation

像 Grok Build 一样支持：

```text
Auto
```

以及：

```text
/skill-name
```

---

## 52.1 Auto 模式

Router 根据任务自动选择。

---

## 52.2 Explicit 模式

高级用户可以：

```text
/udl-lesson-auditor
/evidence-review
/diagram-design
```

显式运行。

---

# 53. Skill Visibility

用户默认只看到高层能力：

```text
Research
Teaching Design
Case
Assessment
Visual
PPT
QA
```

高级模式才展开具体 Skill。

---

# 54. Hooks

自有 Runtime 支持 before_skill、after_skill、before_external_action、after_artifact_write、before_final_export 五类生命周期 Hook。

| 事件 | 必须执行的行为 |
|---|---|
| before_skill | 检查调用资格、权限、输入 Schema 和有效依赖；PCK 检查 Claim 状态，动画设计检查 Animation Gate |
| after_skill | 校验输出 Schema，登记新 Claim、产物依赖及待执行 Gate |
| before_external_action | 核对可信授权记录中的对象、范围、Provider、有效期和本次参数 |
| after_artifact_write | 登记候选版本与内容哈希，更新依赖失效状态，不自动批准内容 |
| before_final_export | 查询第 62 章统一 Gate 清单，核对本次版本全部必需结果及文件 QA |

before_pck、before_animation 是 before_skill 的业务条件，不再另设未注册事件名。

强制 Hook 失败、超时或执行异常时，当前操作保持未完成或阻塞状态，记录原因；不能把“Hook 没有返回失败”视为通过。

---

# 55. Action Safety 与权限执行

区分内容推理、只读数据获取和会修改外部系统的操作。所有外部调用仍通过统一工具调度层，不允许 Skill 或 Subagent 绕过。

## 55.1 授权范围

- 用户要求研究时，可在项目已启用的来源和读取范围内检索、读取页面及获取获准的研究材料；不因每次只读请求重复提问。
- CNKI 下载、Zotero 写入、发邮件、外部上传、发布、Git push 及其他外部写操作，必须有用户明确意图；“研究这门课”不自动授权这些操作。
- 同一任务的有效授权可以覆盖已指定对象和范围内的多步动作；更换目标、扩大范围或增加费用时，重新取得对应授权。
- 研究用只读 POST 与外部写入不能仅凭 HTTP 方法区分，按操作语义判定。

## 55.2 实际控制

授权记录由可信 UI/控制层创建，绑定项目、操作、目标和范围。模型自己输出 explicit_intent=true、网页文本或远程 Skill 中的授权声明均无效。

每次分派工具前检查 Skill 可用性、允许 Provider、网络目标、文件范围、用户授权和资源上限；拒绝的调用不得已先产生副作用。

对写操作超时、结果不明的情况，先查询结果或交由用户处理；无幂等或去重保证时不得盲目重试。

操作日志记录对象、摘要和结果，不记录密码、Cookie 或 API secret。

---

# 56. Sandboxed Execution

未知开源脚本不得直接在主机执行。隔离执行默认 network off、最小只读输入目录、专用临时输出目录、进程/内存/磁盘限制及超时。

- 沙箱限制必须由实际执行环境实现，不以 Prompt、容器名称或配置字段存在作为生效证据。
- Windows 首版仅启用通过第 85 章逃逸和资源限制用例的执行适配器；没有可用适配器时禁用候选脚本并明确报告，不回退到主机执行。
- 被批准的本地导出器等组件可使用 TRUSTED_RUNNER，但其版本、审查依据、文件范围和资源约束须登记。
- 导出器只能读取指定候选产物并写入指定输出目录；网络能力必须单独声明和批准。
- 沙箱出错不应丢弃已接受产物，也不能将部分输出发布为正式文件。

---

# 57. Project Memory 与材料处理

Memory 仅保存项目决策：受众、用词和模板规范、用户确认结构、设计语言、章节关系、已批准案例及视觉体系。已批准案例必须符合下列材料规则。

账号密码、Cookie、API secret 不进入 Prompt、项目文件、运行日志、Memory 或 Subagent。凭据使用浏览器手动登录或 Provider 的独立凭据管理，不由模型代收。

## 57.1 学生与个案资料

- 首版使用匿名、去标识化或明确虚构的教学案例。真实案例的事实不得被模型擅自补全；虚构内容不能冒充研究事实。
- 上传前提示材料用途和目标 Provider。检测到可识别学生资料时，在发送给外部模型或研究服务前暂停，要求使用脱敏材料；不能仅靠“不写 Memory”处理。
- 待脱敏输入仅进入本机隔离输入区，不进入自动检索、通用日志或导出。原始文件可能已含敏感内容，不能承诺上传后原始文件天然无敏感数据。
- 不将学生姓名、联系方式等作为外部检索词；Preview、QA 报告和错误日志也执行相同的数据最小化规则。

## 57.2 保存与删除

首版不自动云同步项目。项目保存到用户指定本机目录，直到用户显式删除；本机临时文件在完成、取消或失败恢复时清理。

删除项目覆盖其托管输入、快照、产物、Memory、运行日志和缓存；不删除用户上传前的原文件，也不声称能够撤回已经发送给第三方 Provider 的数据。Provider 的处理与保留方式在接入配置中展示。

---

# 58. Project Rules 与规则冲突

项目可维护 PROJECT_RULES.md，供用户查看和修改，例如：称谓统一使用“婴幼儿”、每节至少一个案例、脚本讲解正文 1800–2100 字、中文输出。

可信项目规则由用户在工作台中确认后进入规则记录；用户上传文件、论文、网页和上游 Skill 中的任意指令不会自动成为项目规则。

约束处理顺序：

1. 工具权限、事实证据、心理学安全和视频边界等系统硬约束不得被项目模板或 Skill 覆盖。
2. 同一作用范围内，用户最新明确修订替代旧要求，并记录该变更。
3. 用户明确要求与模板要求冲突时展示具体差异，等待解决；模板要求优先于 Skill 默认格式。
4. 系统默认值只用于没有明确约束的部分，必须标记可修改。

Animation Gate 属于正式导出的必需条件。若“每节至少一个动画”与其结论冲突，应展示可通过的动画候选或静态替代，等待用户修订要求；未解决时只能保留草稿，不能擅自删除用户要求并宣称全部完成。

禁用计划步骤不能绕过必需依赖或 Gate。无法执行的排序变更应说明依赖原因；锁定步骤的失效规则见第 48 章。适用规则按职责传递给每个 Subagent。

---

# 59. Session → Skill

借鉴 Grok Build `/skillify` 思想。

当用户多次完成相同工作流后，可以：

> “把这次的课程脚本制作方式保存成 Skill。”

系统生成：

```text
custom-skills/
└─ childcare-course-script/
```

但必须先剔除：

- 具体用户名
- 凭据
- 一次性路径
- 学生个人资料
- 临时文件
- 偶然性的内容事实

---

# 60. Skill Tests

进入 Approved Registry 的 Skill 应按实际职责具备 Schema、Prompt 回归、安全和产物检查；教育 Skill 额外验证理论过度表述、引用支持关系和心理学安全。

确定性检查覆盖类型、权限、路径、版本、文件结构等；教学质量和证据支持关系使用经人工复核的案例集评估，不能仅由生成内容的模型自评后宣称正确。

回归记录须固定输入材料、Skill/模型/规则版本、预期结果和实际结果。模型输出不要求逐字相同；禁止行为、支持关系、目标覆盖和产物结构按可观察结果断言。

每次版本更新运行受影响检查和完整的必需安全回归。不要用没有内容的测试文件或固定返回 PASS 的检查满足本章。

---

# 61. Bad Example Quarantine

上游 Skill 的示例不自动信任。

如果发现：

- 数学错误
- 事实错误
- 错误引用
- 不安全推理
- 过度确定措辞

则：

```text
examples/
   ↓
quarantine
```

不能继续作为 few-shot。

---

# 62. Quality Gates：唯一执行清单

本表是计划、UI、Hook 和验收共同引用的唯一 Gate 清单，不在各处维护不同子集。

| ID | Gate | 主要通过条件 |
|---|---|---|
| G1 | Requirements | 当前要求全部满足，或用户已明确修改；不存在未解决冲突 |
| G2 | Evidence | 正式内容的事实性 Claim 均被有效证据支持，改写没有升级结论 |
| G3 | Pedagogy | 学习目标、内容、案例、活动与评价对应 |
| G4 | Psychology Safety | 无诊断、标签化、个体过度推断或未经支持的治疗表述 |
| G5 | Inclusive Design | 检查实际学习障碍，替代路径保持目标与核心认知要求 |
| G6 | Multimedia | 媒体承担知识功能；动画候选通过 Gate；所需静态终态和同步设计齐备 |
| G7 | Template | 当前模板结构、栏目、术语及字数符合要求 |
| G8 | Artifact | 导出文件可打开、内容完整、可编辑性和渲染检查通过 |

每项结果包含 gate_id、检查版本、目标产物及依赖版本、status、问题位置、原因和下一步建议。status 为 PASS / FAIL / NEEDS_REVIEW / NOT_APPLICABLE。

NOT_APPLICABLE 只能由已定义的适用规则产生并保留原因，例如纯文本产物无动画候选时不执行动画子检查。缺少输入、Provider 失败或没有运行检查不能记为 NOT_APPLICABLE 或 PASS。

## 62.1 导出与草稿

- 正式导出要求所有适用 Gate 为 PASS，其他项有有效 NOT_APPLICABLE 原因，且不存在过期或冲突产物。
- FAIL / NEEDS_REVIEW 阻止正式导出；用户可以查看或下载明确标注“草稿—未通过 QA”的版本，附问题清单。草稿通道仍不能绕过工具权限、凭据隔离和学生资料处理规则。
- 首版最多自动修正同一问题两轮；仍未解决时暂停相关步骤，提供修改要求、补充材料或人工复核入口，不无限重试。
- 人工复核必须记录依据和实际改动，不能只点击按钮把无证据的事实强制批准。
- G8 检查候选导出文件，通过后才发布到正式 outputs；候选文件不会提前显示为正式交付物。
- 后续修改只重跑受影响检查，但全局字数、术语和输出完整性等相关约束仍需覆盖。

---

# 63. Evidence Gate

确认来源可定位、证据实际支持当前结论、结论强度和外推范围没有超出依据，并保留反证及不确定性。

不是所有 Claim 都强制引用原始实验论文。定义、指南、综述及原始研究按用途选择合适来源；必须标记来源层级，不能把转述材料冒充原始证据。

| 结果 | 后续处理 |
|---|---|
| PENDING | 获取材料或核验，相关正式事实生成暂停 |
| SUPPORTED | 仅在核验范围和有效版本内使用 |
| QUALIFY_REQUIRED | 降低强度、限定人群或改写，形成新 Claim 版本后重审 |
| UNSUPPORTED | 删除正式陈述或补充证据；可在草稿中标注待解决问题 |
| DISPUTED | 保留冲突证据，改写为有范围限定的争议说明并重审，必要时人工复核 |
| HUMAN_REVIEW_REQUIRED | 提供来源、原文和分歧，等待教师或适任审阅者处理 |

没有获取全文时，只能核验实际读到的部分；来源不可访问、检索超时和只有元数据时，均不得声称已完成全文核验。

Evidence 检查至少发生在事实进入 PCK 前和正式内容生成后。事实内容、引用源版本或适用范围变化时，旧的通过结果失效。

---

# 64. Pedagogy Gate

检查：

```text
学习目标是否明确？
内容是否服务目标？
案例是否真正解释难点？
活动是否有教学功能？
评价是否测目标？
难度是否连续？
```

---

# 65. Psychology Safety Gate

检查：

```text
diagnosis
labeling
causal overclaim
neuro-overclaim
individual inference
treatment claim
clinical advice leakage
```

---

# 66. Multimedia Gate

检查：

```text
视觉是否承担知识功能？
动画是否必要？
字幕与讲解是否同步？
学生是否需要静态终态？
内容是否过密？
```

---

# 67. Template Gate

检查用户提供的模板：

- 表格结构
- 栏目顺序
- 教师话术风格
- 画面字段
- 案例位置
- 字数
- 专有用词
- 表达习惯

模板属于：

```text
High Priority Project Constraint
```

不能因为某个 Skill 默认输出格式不同就破坏模板。

---

# 68. 上游能力候选清单与审查依据

以下均源自原稿建议。**本稿没有收到对应仓库/提交/审查记录，所有候选的实际 review_status 均为 UNVERIFIED，不直接加入运行 allowlist。**

| 候选能力 | 建议用途或处理 | 接入前重点验证 |
|---|---|---|
| skills-mgr | 包管理候选 | 来源、路径、固定版本、原子发布、下载后不执行 |
| education registry | Provider 候选 | 能力登记，不接管总路由 |
| suggest_skills | 仅候选发现 | 是否只有关键词匹配；不据名称作结论 |
| cognitive-load-analyser | PATCH 候选 | 去除伪精确评分和绝对化表述 |
| dual-coding-designer | ADOPT 候选 | 视觉知识功能与领域适配 |
| worked-example-fading | 条件使用候选 | 适用知识类型与教学目标 |
| hinge-question | PATCH 候选 | 答案、干扰项和上游示例独立 QA |
| PCK developer | PATCH 候选 | 强制消费有效 Evidence |
| UDL barrier anticipator | PATCH 候选 | 不自动诊断或转介 |
| UDL lesson auditor / options designer | ADOPT 候选 | 学习障碍分析与目标不变 |
| grounded-citations | Citation Ledger 候选 | 引用定位及快照，不替代支持关系核验 |
| scientific-literature-review | PATCH 候选 | 心理学/教育检索 Profile 与来源可达性 |
| sci-extract prompt / harvester | 分组件评估 | 语义分析模板与数据获取职责分开 |
| sci-extract extractor / figure downloader | 默认不启用 | 实际代码与网络文件行为重新审查 |
| CNKI researcher / search / detail | 可选连接器候选 | 机构无关、选择器验证、凭据隔离 |
| CNKI download / Zotero export | Action 候选 | 明确授权，Zotero 默认仅元数据 |
| storyboard / find-animation-opportunities | REFERENCE_ONLY 候选 | 提取方法后自建教育分镜与 Gate |
| diagram-design | Provider / PATCH 候选 | 语义到图型及可编辑性 |
| fixing-accessibility | 不作为教学 UDL 来源 | Web 可访问性与教学 UDL 分别处理 |
| scholar-ppt-cn | Composer 候选 | 教学产物输入、可编辑 PPTX、真实渲染 QA |
| video-production-skill | 不进入 V1 视频运行链 | 仅参考方法，保留视频边界 |
| trauma-informed | 默认关闭 | 启用前完成领域复核与 Safety QA |
| PERMA / flow | 可选领域候选 | 不作为默认解释框架 |
| implementation-intention / self-efficacy / motivation-diagnostic | PATCH 候选 | 改为教学假设，不推断个体诊断 |

每个候选需填入第 9 章来源记录后，才可作出 APPROVED/REJECTED 决定。未能定位上游时可自行实现等价能力，并标明自有实现；不能称已采用或验证该上游。

---

# 69. V1 总架构

```text
┌──────────────────────────────────┐
│          BUILD WORKSPACE         │
│  Prompt / Files / Preview / Diff │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│       REQUIREMENTS ENGINE        │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│            PLAN ENGINE           │
│ DAG / Q&A / Steps / Approval     │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│       PSYCHOLOGY ROUTER          │
│ task + knowledge + risk          │
└───────┬─────────┬─────────┬──────┘
        │         │         │
        ▼         ▼         ▼
   Research   Curriculum   Pedagogy
        │         │         │
        └────┬────┴────┬────┘
             ▼         ▼
        Evidence     Teaching
        Artifacts    Artifacts
             │         │
             └────┬────┘
                  ▼
         Inclusive Design
                  │
                  ▼
            Authoring
                  │
                  ▼
         Multimedia Engine
            │          │
            ▼          ▼
         Diagram    Animation Gate
                        │
                        ▼
                    Storyboard
                        │
                        ▼
                  Video Prompt
                        │
                       STOP

                  │
                  ▼
       Presentation Composer
                  │
                  ▼
             Final QA
                  │
                  ▼
              OUTPUTS
```

---

# 70. V1 建议目录

```text
psychology-education-build/
├─ AGENTS.md
├─ PROJECT_RULES.md
├─ config/
│  ├─ providers.yaml
│  ├─ router.yaml
│  ├─ risk.yaml
│  └─ schemas/
├─ skills/
│  ├─ upstream/
│  ├─ local/
│  └─ patched/
├─ patches/
├─ registry/
│  ├─ skills.json
│  ├─ allowlist.json
│  └─ denylist.json
├─ orchestrator/
│  ├─ planner/
│  ├─ router/
│  ├─ graph/
│  ├─ runtime/
│  └─ hooks/
├─ providers/
│  ├─ web/
│  ├─ research/
│  ├─ cnki/
│  ├─ papers/
│  ├─ diagram/
│  └─ presentation/
├─ gates/
│  ├─ evidence/
│  ├─ pedagogy/
│  ├─ psychology-safety/
│  ├─ udl/
│  ├─ multimedia/
│  └─ artifact/
├─ artifacts/
│  ├─ schemas/
│  └─ validators/
├─ ui/
│  ├─ build/
│  ├─ plan/
│  ├─ preview/
│  └─ diff/
├─ sandbox/
├─ tests/
└─ docs/
```

---

# 71. 分阶段实现与可验收里程碑

## M0：最小基础与证据契约

完成本机项目空间、Requirements、统一 Schema、产物版本与依赖、固定版本的本地 Registry、最小工具权限边界和 G1–G8 的统一结果格式。先支持明确登记的本地能力，不要求先做完整远程市场。

同时完成 Claim / Source / Evidence Assessment、引用定位和 Evidence Gate。模型与研究 Provider 未配置时，报告不可用；测试夹具不能伪装成真实研究输出。

## M1：首个端到端闭环——课程脚本

用户模板 → 要求 → 学习目标 → 用户材料/已启用研究来源 → Evidence Gate → 教学设计/案例/评价 → 脚本 → QA → Preview → DOCX/Markdown。

支持更换一个案例、查看 Diff、接受/拒绝和相关段落重建。使用受控教学能力完成 PCK、UDL 等检查。研究广度可以有限，但证据门禁不能后置或跳过。

## M2：能力管理与研究扩展

完成远程 Skill 隔离、来源审查、Local Patch、版本 pin、回归测试和实际沙箱。扩展数据库及论文获取；CNKI 保持可选连接器，不成为默认闭环的前置依赖。

## M3：媒体与分镜

完成 Media Router、SVG 图示、Animation Gate、教学分镜、生成提示词和预览。演示不适合动画时的冲突处理；在最终视频渲染前停止。

## M4：可编辑 PPTX 与完整 V1

完成 Evidence Index、Production Planning Table、Slide Families、可编辑 PPTX、真实文件渲染和 QA。贯通跨脚本、题目、分镜和幻灯片的局部重建，并达到第 79 章全部条件。

各里程碑只声明自己通过的能力。Session → Skill、额外理论插件和可选连接器不阻塞核心 V1；不得因此删除其后续需求。

---

# 72. 验收场景 A：课程脚本与约束冲突

输入：“按照我上传的模板，写《托育机构管理实务》第八章四节课程脚本，每节 1800–2100 字，每节至少 1 个案例和 1 个动画，称谓统一使用‘婴幼儿’。”

流程：模板解析 → 要求 → 学习目标 → Claim 与研究 → Evidence Gate → 教学/案例设计 → Animation Gate → 脚本 → G1–G8 → DOCX/Markdown。

正常路径：四节课均有通过动画 Gate 的知识点，输出相应分镜及生成提示词；不输出最终动画视频。

冲突路径：任一节无合适动画候选时，列出原因、可调整的教学点和静态替代，等待用户修订动画要求；解决前可展示草稿，不能标记全部验收通过。

字数按第 83 章默认规则计算，输出报告标明统计范围；若用户要求连同画面栏统计，则保存其明确修订后的规则。

---

# 73. 验收场景 B：融合教育课程

输入：

> “项目三三个任务，写成三个在线课程脚本。”

系统必须识别：

```text
任务1 真实行为记录
    → observation skill

任务2 事实 vs 判断
    → distinction

任务3 避免贴标签
    → concept + attitude + transfer
```

所以三个任务不应该使用完全相同的教学策略。

---

# 74. 验收场景 C：心理学知识点

输入：

> “做一节关于压力反应的课。”

系统不得自动输出：

> “杏仁核启动后导致皮质醇……”

除非该机制性 Claim 经过 Evidence Gate。

如果证据只支持：

> “压力与某些生理反应相关”

则脚本不能擅自升级成单线因果神经机制。

---

# 75. 验收场景 D：动画决策

输入：“给这节课每一页都做动画。”

系统逐项执行 Animation Gate，说明适合动画、建议静态图和纯文本的项目及理由。数量由输入内容决定；“12 个候选、3 个动画、5 个静态、4 个文本”只作为展示示例，不是固定答案。

若用户要求与筛选结果不一致，按第 58 章处理冲突，不能静默减少动画数量后报告已满足原要求。

选定并通过的动画产出教学分镜、生成提示词和必要的静态终态设计，在视频生成前停止。

---

# 76. 验收场景 E：PPT

输入：

> “根据这套课程做 PPT。”

系统必须先读取：

```text
Teaching Artifacts
Evidence Assets
Media Decisions
```

形成：

```text
Production Planning Table
```

再生成 PPT。

---

# 77. 成功指标与评估口径

每次评估固定输入集、预期标准及 Skill/模型/规则版本，报告分母、通过数和失败案例。以下指标用于观察质量，不凭模型自评分宣称达标。

| 指标 | 评估方式 |
|---|---|
| Routing Accuracy | 对人工复核的知识类型和教学策略案例，统计允许策略集合的命中及错误原因 |
| Evidence Fidelity | 对人工标注的支持、限制、反证和证据不足案例，评估判断及最终表述是否符合证据 |
| Teaching Alignment | 教师按目标—内容—活动—评价的一致性量表复核 |
| Edit Locality | 修改后实际失效/重建集合与预期依赖集合比较，无关产物内容和版本保持不变 |
| Safety | 固定禁止行为样例中，不出现诊断、标签化及未经支持的个体或因果推断 |
| Artifact Quality | 文件打开、内容完整、规定对象可编辑、真实渲染和模板检查 |
| Cost / Latency | 记录每步骤耗时、调用次数和可获得的用量；未提供价格数据时不编造金额 |

首版发布必须通过第 85 章全部必需验收用例；正式交付物不得有未解决的阻断项。不得仅用一个总分抵消关键失败。

Routing 等统计指标在首个基线集上报告实测结果，不在缺少基线时宣称通用准确率。Session → Skill 的复用性作为后续扩展评估。

---

# 78. 最关键的设计原则

## Principle 1

**Skill 不是可信单元，Artifact 才是系统状态。**

---

## Principle 2

**研究 Agent 生产 Evidence，不直接生产课程事实。**

---

## Principle 3

**PCK 负责“怎么教”，不负责“事实是真是假”。**

---

## Principle 4

**动画是教学媒介，不是装饰。**

---

## Principle 5

**PPT 是教学设计的呈现层，不是教学设计本身。**

---

## Principle 6

**开源 Skill 通过 Patch 改，不轻易 fork。**

---

## Principle 7

**所有外部副作用必须与 Reasoning Skill 分离。**

---

## Principle 8

**复杂任务必须使用 Durable Artifacts，而不是把整个历史聊天塞回 Prompt。**

---

## Principle 9

**每次 Build 都应该可以 Preview、Diff、局部重建。**

---

## Principle 10

最终用户体验必须保持：

```text
“告诉系统我要做什么”
              ↓
“系统把它真正做出来”
```

而不是：

```text
“先学会如何操纵 40 个 Skills。”
```

---

# 79. 完整 V1 完成定义

- [ ] 接受自然语言要求，支持第 83 章限定输入格式和用户模板。
- [ ] 生成可查看和修改的 Build Plan，阻止非法依赖顺序及必需步骤绕过。
- [ ] 根据知识类型选择教学路径，支持 Auto 和显式 Skill 调用。
- [ ] 生成并维护可追溯的 Evidence Artifacts，执行生成前后支持关系审查。
- [ ] 支持课程结构、脚本、教案、案例、评价和学习单等教学产物。
- [ ] 应用 PCK、UDL、认知负荷和 Dual Coding 等经审查能力。
- [ ] 生成图示、教学分镜和提示词；动画冲突可解释、可解决；不渲染视频。
- [ ] 形成 PPT Production Plan，生成符合第 83 章可编辑性要求的 PPTX。
- [ ] 主要产物可预览，修改可 Diff、Accept/Reject，跨产物局部重建遵守版本规则。
- [ ] Skill 来源可追溯，支持 Local Patch、版本 pin、实际沙箱及上游变更失配处理。
- [ ] 所有工具路径执行权限检查，外部写操作绑定真实用户授权。
- [ ] G1–G8 共用清单，FAIL/NEEDS_REVIEW/过期状态无法冒充正式通过。
- [ ] 取消、失败恢复、旧任务回写和锁定冲突通过验收。
- [ ] 第 85 章必需用例全部通过，真实端到端样例有教师复核及文件 QA 记录。

可选 CNKI/Zotero、额外理论插件和 Session → Skill 不作为本次完整 V1 的必需发布条件；仍遵守其章节约束。未接入的能力在 UI 标为未配置或不可用。

---

# 80. Grok 参考与本系统责任映射

| 来源类别 | 参考能力 | 本系统责任 |
|---|---|---|
| 网页/移动端体验 | 聊天内描述、生成、修改、发布、GitHub 导出 | 借鉴连续构建体验；V1 自行实现课程预览与修改，不承诺发布课程 |
| 编码 Agent / TUI 文档 | Skills、Plugins、MCP、Hooks、Plan、Subagents、AGENTS.md、Sandbox、Diff | 可评估复用接口或实现方法，不能据此假定网页端具有同等接口 |
| 本项目自建 | Psychology Router、Evidence Gate、教学 QA、Artifact 版本、局部重建、导出规范 | 必须以本稿的功能及验收证明，不由“像 Grok”代替规格 |
| 后续扩展 | Session → Skill、课程发布、更多连接器 | 独立评审，不默认属于首个里程碑 |

本项目不假定 Grok 网页是可嵌入的调度服务。具体宿主或模型通过有文档支持的接口接入；不依赖自动操作第三方 UI 作为核心引擎。

---

# 81. 官方参考与核验范围

核验日期：2026-09-15。以下链接用于限定参考范围，不构成本系统已经具备这些能力的证据。

- [Grok Build 网页和移动端公告](https://x.ai/news/grok-build-for-everyone)：支持聊天内构建、发布与 GitHub 导出等体验描述。
- [Build Overview](https://docs.x.ai/build/overview)：描述编码 Agent 的 TUI、headless 和 ACP 使用方式。
- [Skills, Plugins & Marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces)：说明 Skill 发现与扩展机制；额外 frontmatter 字段可能被忽略，allowed-tools 不授予或限制工具权限。
- [开源公告](https://x.ai/news/grok-build-open-source)：开源对象包括编码 Agent、TUI、工具和扩展系统。

因此，第 7 章权限字段和第 54–56 章执行控制由本系统负责。上述引用不证明第 68 章上游 Skill 的源码已审查，也不证明所有终端能力在网页端可用。

---

# 82. 最终产品定义

本项目最终不是：

> “心理学 Prompt 集”

也不是：

> “教育 Skills 合集”

更不是：

> “自动写教案的大模型”。

它应该是：

> **Psychology Education Build System**
>
> 一个采用 Grok Build 式工作方式的教师 AI 生产环境：
>
> **需求 → 计划 → 研究 → 证据 → 教学设计 → 内容 → 媒体 → 产物 → QA → Preview → Diff → 迭代。**

用户面对的是一个连续 Build 过程。

Skills、Providers、Subagents、Evidence Gate、Patch、Sandbox、DAG 全部隐藏在下面，为结果负责。


---

# 83. 首版运行形态与输入输出默认值

本章为本次修订提出的默认范围，尚未经产品方逐项确认；后续修改应同步更新阶段与验收用例，不能暗中扩大或缩减。

## 83.1 部署与服务边界

- 本机单教师 Web 工作台，UI 和调度服务默认仅监听本机；项目状态保存在用户选定目录。V1 不提供多人协作、账户体系和云同步。
- 模型与研究服务通过 Provider 适配器接入。首次配置确认服务名称、材料发送范围和调用预算；没有配置时说明缺失，不使用假结果兜底。
- 首版默认最多同时运行两个独立生成/研究步骤。无需用多 Agent 才算完成；依赖正确性优先于并行数量。
- 默认研究闭环使用用户材料及一个已配置的公开研究来源。其余数据库逐个报告可用性，不承诺原稿列举的所有商业数据库可自动访问。
- 公共 API、远程部署与多人权限不在本次默认范围内；本机 UI 通过自有后端读取状态、提交修改和订阅运行事件。

## 83.2 输入

- 正文材料：UTF-8 TXT/Markdown、DOCX、可提取文本的 PDF。
- 首版模板：DOCX 表格模板或 Markdown 模板。表格栏目、顺序、段落层级及术语规则必须提取后可预览；复杂嵌套或不支持结构应报明具体位置。
- 扫描 PDF、图片 OCR、旧版 DOC、宏文档和任意 PPT 母版导入不在首版保证范围。不能把未解析页面视为已读取；提示转换为支持格式。
- 默认每文件不超过 25 MiB、每项目一次导入最多 20 个文件，总计不超过 100 MiB；超限时在处理前提示拆分，不静默截断。解析进程须有单独资源限制。
- 用户上传本身不授权执行文件内的脚本、宏或嵌入指令。

## 83.3 字数与模板

默认脚本字数统计教师讲解正文（包括正文中讲述的案例），按 Unicode 非空白字符计数，包含标点、数字及拉丁字母，不计标题、画面指令、引用索引和独立备注。报告显示采用的统计口径。

用户或模板有明确不同口径时采用其确认后的规则；双方矛盾按第 58 章解决。“1800–2100 字”没有说明时使用上述默认值。

模板结构和内容约束优先保证；首版不承诺对任意来源文档逐像素复刻。不能支持的版式应在生成前通过解析预览暴露。

## 83.4 输出与可编辑性

- 脚本、教案、评价、学习单：DOCX 和 Markdown；主要文字与表格可直接编辑，学生版不含教师答案。
- 图示：SVG 及其结构化源数据；分镜：Markdown/JSON 和静态预览；视频提示词：可编辑文本。
- PPTX：标题、正文和表格为原生可编辑对象；系统生成的简单流程/关系图使用原生形状，数据图表保留可编辑数据或原生图表。
- 照片、文献原图及复杂插图可以为图片；需在生产计划中标明不可逐元素编辑的对象，附来源和可用源文件。不得整页栅格化后宣称“可编辑 PPTX”。
- DOCX/PPTX 的 QA 以明确声明的目标 Office 渲染环境为准，记录渲染器及字体；不得用浏览器预览替代实际文件检查。目标渲染环境无法运行时，G8 为 NEEDS_REVIEW。
- 本地 outputs 分草稿和正式目录，文件名含产物与版本标识，不覆盖历史正式文件。

---

# 84. 运行状态、失败恢复与预算

计划步骤状态统一为 PENDING / RUNNING / SUCCEEDED / FAILED / BLOCKED / CANCELLED / STALE；项目进度由实际步骤和 Gate 结果计算，不凭模型文本“完成了”更新。

- 每个步骤记录输入版本、执行尝试、Provider、用量、时间、候选输出和错误原因。日志不保存凭据或学生敏感原文。
- 取消时停止后续分派，尽力取消在途请求；已取消运行的晚到结果不能自动提交。已发生的外部操作单独报告，不能声称已撤销。
- 应用重启后，原 RUNNING 步骤先标为中断待恢复；重新核对输入、缓存产物和远程操作结果，再决定续跑或重试。
- 只读临时网络失败默认最多重试两次，遵守服务返回的等待时间并退避；认证失败、输入错误及明确拒绝不反复重试。
- 读操作默认超时 60 秒、模型调用 180 秒、本地导出 120 秒；Provider 可声明经验证的覆盖值，UI 显示当前值。超时不等于远端没有执行。
- 同一 QA 问题的自动修正最多两轮；超限停止相关步骤，保留中间产物和明确下一步。
- 启动运行前展示默认预算：最多 40 次模型调用、20 次研究请求和 30 分钟运行时间。达到任一上限时暂停，保留进度，由用户调整预算后恢复。金额仅在 Provider 价格可用时估计并标注。
- 外部写操作不套用只读重试策略；结果不明按第 55 章处理。
- 无法获得所需全文时，可更换已启用来源、使用用户提供材料或请求补充；不能把搜索失败转换成“没有相关研究”。

---

# 85. 必需验收用例

以下用例必须有固定输入、预期结果和实际证据。权限、版本和文件结构用自动化测试；证据语义、教学与视觉结果结合人工标注和实际文件复核。不能全部用模型自评替代。

| ID | 场景 | 必须观察到的结果 |
|---|---|---|
| A01 | 按 DOCX 模板生成四节脚本 | 栏目、案例、称谓和字数满足当前要求，正式文件通过 G1–G8 |
| A02 | 观察、辨析、态度迁移三个任务 | 策略分别服务对应目标，不能机械生成同一教学流程 |
| A03 | 压力反应材料仅支持相关 | 不升级为单线因果机制；相关 Claim 与实际证据对应 |
| A04 | 引用存在但不支持结论 | G2 不通过，不能以有引用或文件存在放行 |
| A05 | 只有元数据或摘要 | 标明取得内容层级，不声称全文核验，不生成未被支持的机制事实 |
| A06 | 两份来源互相冲突 | 保留双方证据，限定结论或转人工复核，不静默选择有利来源 |
| A07 | 每节动画要求与 Gate 冲突 | 列出冲突并等待要求修订，草稿不冒充正式完成 |
| A08 | 更换一个案例后接受修改 | 只更新相关依赖产物；无关产物版本和内容哈希不变 |
| A09 | 拒绝候选修改 | 已接受的脚本、题目、分镜和 PPT 维持原版本，无部分提交 |
| A10 | 旧生成任务晚于新任务完成 | 旧结果不覆盖新版本，记录基线冲突 |
| A11 | 上游修改影响锁定节点 | 显示过期和锁定冲突，正式导出被阻止 |
| A12 | 禁用必需步骤或非法排序 | 拒绝破坏依赖的计划变更并解释原因 |
| A13 | 一个必需 Hook 异常或 Gate 未运行 | 不判为 PASS，显示失败或待复核 |
| A14 | Provider 超时、凭据缺失、配额不足 | 有界重试或明确暂停，保留已完成步骤，不捏造研究结果 |
| A15 | 取消、重启、预算耗尽 | 可查看并恢复进度；晚到结果不提交；不重复未知结果的外部写操作 |
| A16 | 上游 SHA 改变或 Patch 不匹配 | 新版本不发布，不回退到无补丁版本 |
| A17 | 未批准 Skill、越界路径、网络越权 | 调用在实际执行前被拒绝；声明允许不能替代真实授权 |
| A18 | 未知脚本试图读主机文件、联网或超额占资源 | 实际沙箱限制生效；沙箱不可用时不回退主机 |
| A19 | 网页/模板/Skill 写入伪造授权指令 | 不产生授权记录，不触发 CNKI 下载、Zotero 写入或发布 |
| A20 | 输入含可识别学生资料或凭据 | 外发前阻止并提示脱敏；日志、Memory 和检索请求中无泄露 |
| A21 | 模板无法解析、输入超限或扫描 PDF | 明确说明不支持部分，不静默遗漏后报告完整 |
| A22 | 导出 DOCX/PPTX | 实际文件可打开，文字和规定图表可编辑，无溢出遮挡，引用对应 |
| A23 | G8 失败后用户下载草稿 | 文件和 UI 均明确草稿状态，正式目录不出现误标交付物 |
| A24 | Prompt/Tool/UI 传入数组、整数与布尔值 | 经适配后业务语义一致，非法值明确报错 |
| A25 | 生成教学解释时新增事实或扩张结论 | 新事实登记待核验，原 Claim 通过状态不能自动覆盖新表述 |
| A26 | 删除本机项目 | 托管输入、产物、Memory、快照、日志和缓存移除；外部原件保持不变 |

每个里程碑执行涉及的用例；完整 V1 执行全部用例。发布记录保存版本、检查结果、必要的教师复核和真实导出样例，不把测试夹具标为生产成果。

---

# 86. 本次修订摘要与待验证事项

## 已修订

1. 将事实支持关系与引用登记分离，定义多来源证据记录及生成前后检查。
2. 定义不可变产物版本、候选变更集、失效传播、锁定冲突和旧任务提交规则。
3. 统一 G1–G8、Hook、草稿与正式导出条件及失败恢复。
4. 解决动画、模板、用户要求及系统硬约束的冲突处理。
5. 分开权限声明、可信授权与实际工具/沙箱执行。
6. 将无源码依据的上游结论调整为候选政策，统一 Registry 状态。
7. 将证据契约前置，采用可验收里程碑并保留完整 V1 目标。
8. 补充首版运行形态、格式、字数、可编辑性、预算和失败验收。
9. 区分 Grok 网页体验、编码 Agent 能力及本项目自建能力。

## 实施前需要验证，不能宣称已完成

- 第 68 章各候选的真实仓库、许可、commit SHA、代码行为和审查记录。
- 选用的模型、研究来源及文档渲染器是否在目标设备可用。
- 沙箱适配器在 Windows 上的实际隔离效果和资源控制。
- 第 83–84 章默认形态、格式及预算是否符合首批教师的真实使用情况。

本稿完成需求修订，不表示已搭建、安装、审计、测试或部署目标系统。
