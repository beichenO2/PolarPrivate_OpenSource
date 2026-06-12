# Knowledge Tree

- project: PolarPrivate
- generated_at: 2026-05-02T17:39:46.306Z

## 关键设计

- reference/ (`readme`)
- 项目参考资料的目录治理规范 (`src-20260502-readme`)
  - 该资料描述了项目 reference/ 目录的设计意图和管理规范，明确该目录仅用于存放只读参考资料，包括开源项目、论文、技术博客摘录等外部材料，并对大文件存储提供 Git LFS 或链接引用的具体方案。这是项目结构管理中的参考资料治理规范。
- reference/ 目录 (`entity-reference-directory`)
  - 项目中用于集中存储只读外部参考资料（开源项目、论文、博客摘录等）的专用目录，通过目录隔离实现源码与参考资料的有效分离。
- 参考资料管理 (`concept-reference-management`)
  - 项目中对外部参考材料进行集中、规范存储和管理的最佳实践，通过目录隔离、分类组织、版本控制等手段，确保参考资料的可追溯性和可维护性，同时保持项目源码结构的清晰纯粹。

## 总体设计

- 总体设计/concept (`overall-concept`)
  - 由 2 个关键设计节点抽象而来
- 总体设计/source (`overall-source`)
  - 由 1 个关键设计节点抽象而来
- 总体设计/entity (`overall-entity`)
  - 由 1 个关键设计节点抽象而来

## 一般逻辑

- 这类项目的一般逻辑 (`general-logic-core`)
  - 从多个总体设计层抽象出的通用逻辑骨架
  - 从 source/concept/entity 页面抽取可复用结构
  - 按问题-方法-约束组织知识层次
  - 优先沉淀可被 Agent 复用的设计规则

