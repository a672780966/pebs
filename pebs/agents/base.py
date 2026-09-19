from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

BLOCKED_ATTRS = frozenset(
    {"store", "evidence", "hooks", "permissions", "research", "llm", "providers", "registry"}
)


class AgentContractError(Exception):
    """Subagent 违反自己的 Skill Contract（未声明输入 / 未声明产出）。"""


class IsolationViolation(Exception):
    """Subagent 试图访问契约之外的上下文或能力。"""


@dataclass
class AgentBrief:
    agent: str
    goal: str
    inputs: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, int] = field(default_factory=dict)
    output_schema: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "goal": self.goal,
            "inputs": list(self.inputs),
            "constraints": self.constraints,
            "budget": self.budget,
            "output_schema": self.output_schema,
        }


@dataclass(frozen=True)
class AgentContract:
    agent: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    output_schema: str | None = None
    domain: str = ""
    strict_reads: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "output_schema": self.output_schema,
            "domain": self.domain,
            "strict_reads": self.strict_reads,
        }


class RestrictedContext:
    """把 PipelineContext 收窄到一个 Subagent 的契约之内。

    - 读：仅允许契约声明的输入 artifact 类型（strict_reads=True 时强制，用于外部 Skill）。
    - 写：只允许契约声明的产出 artifact 类型（始终强制，用于产物责任追溯）。
    - Subagent 之间不直接通信，只能通过 Store 中的 Artifact 交换信息。
    """

    def __init__(
        self,
        inner: Any,
        *,
        agent: str,
        allowed_inputs: tuple[str, ...],
        produces: tuple[str, ...],
        strict_reads: bool = True,
    ) -> None:
        self._inner = inner
        self.agent = agent
        self.allowed_inputs = set(allowed_inputs)
        self.produces = set(produces)
        self.strict_reads = strict_reads
        self.produced: list[str] = []

    # ---------------------------------------------------------------- guards
    @staticmethod
    def _artifact_type(artifact_id: str) -> str:
        return artifact_id.split(":", 1)[0]

    def _guard_read(self, artifact_type: str) -> None:
        if self.strict_reads and artifact_type not in self.allowed_inputs:
            raise IsolationViolation(
                f"{self.agent} 不允许读取 artifact 类型：{artifact_type}（契约输入：{sorted(self.allowed_inputs)}）"
            )

    def _guard_write(self, artifact_type: str) -> None:
        if artifact_type not in self.produces:
            raise AgentContractError(
                f"{self.agent} 不允许产出 artifact 类型：{artifact_type}（契约产出：{sorted(self.produces)}）"
            )

    # ------------------------------------------------- restricted interface
    def rev(self, artifact_id: str) -> str | None:
        self._guard_read(self._artifact_type(artifact_id))
        return self._inner.rev(artifact_id)

    def content(self, artifact_id: str) -> Any | None:
        self._guard_read(self._artifact_type(artifact_id))
        return self._inner.content(artifact_id)

    def artifact_ids_of_type(self, artifact_type: str) -> list[str]:
        self._guard_read(artifact_type)
        return self._inner.artifact_ids_of_type(artifact_type)

    def content_by_type(self, artifact_type: str) -> Any | None:
        self._guard_read(artifact_type)
        return self._inner.content_by_type(artifact_type)

    def emit(
        self,
        artifact_id: str,
        artifact_type: str,
        content: Any,
        produced_by: str,
        deps: list[str] | None = None,
    ) -> dict[str, Any]:
        self._guard_write(artifact_type)
        info = self._inner.emit(artifact_id, artifact_type, content, produced_by, deps=deps)
        self.produced.append(info["revision_id"])
        return info

    def sections(self) -> list[dict[str, Any]]:
        return self._inner.sections()

    @property
    def outputs(self) -> dict[str, str]:
        visible = self.allowed_inputs | self.produces
        return {
            artifact_id: revision_id
            for artifact_id, revision_id in dict(self._inner.outputs).items()
            if self._artifact_type(artifact_id) in visible
        }

    def __getattr__(self, item: str) -> Any:
        if item in BLOCKED_ATTRS and self.strict_reads:
            raise IsolationViolation(f"{self.agent} 不允许访问 ctx.{item}")
        attribute = getattr(self._inner, item)
        if callable(attribute) and self.strict_reads:
            raise IsolationViolation(f"{self.agent} 不允许直接调用 ctx.{item}，只能通过受限接口访问产物")
        return attribute


class Subagent:
    """一个受契约约束的执行单元。

    Subagent 不持有其它 Subagent 的引用：它们只通过 Artifact Store 通信（§28）。
    """

    name = "subagent"
    kinds = "subagent"
    domain = ""
    default_inputs: tuple[str, ...] = ()
    default_produces: tuple[str, ...] = ()
    description = ""

    def __init__(self, llm: Any = None):
        self.llm = llm

    def contract_for(self, record: dict[str, Any], *, strict_reads: bool = False) -> AgentContract:
        domain = str(record.get("domain") or self.domain)
        # `optional_requires` 是**已声明**的可选输入，必须算进契约输入：
        # RestrictedContext.outputs 只暴露 allowed_inputs | produces，若把可选输入排除，
        # 依赖它们的步骤（例如 gate-runner 读 requirements/teaching_plan 做 G1/G3）
        # 会拿到空产物并静默跳过检查——动态链路下门禁被悄悄削弱。
        required = list(record.get("requires") or self.default_inputs or ())
        optional = [item for item in (record.get("optional_requires") or []) if item not in required]
        return AgentContract(
            agent=self.name,
            inputs=tuple(required + optional),
            outputs=tuple(record.get("emits") or record.get("produces") or self.default_produces),
            output_schema=record.get("output_schema"),
            domain=domain,
            strict_reads=strict_reads,
        )

    def run_node(
        self,
        ctx: Any,
        *,
        node: dict[str, Any],
        record: dict[str, Any],
        handler: Callable[..., Any],
        strict_reads: bool | None = None,
        constraints: dict[str, Any] | None = None,
        budget: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        if strict_reads is None:
            strict_reads = str(record.get("runtime", "builtin")) != "builtin"
        contract = self.contract_for(record, strict_reads=strict_reads)
        restricted = RestrictedContext(
            ctx,
            agent=self.name,
            allowed_inputs=contract.inputs,
            produces=contract.outputs,
            strict_reads=strict_reads,
        )
        brief = AgentBrief(
            agent=self.name,
            goal=str(node.get("title") or record.get("description") or record.get("name") or ""),
            inputs=contract.inputs,
            constraints=constraints or {},
            budget=budget or {},
            output_schema=contract.output_schema,
        )
        result = handler(restricted, node, record)
        return {
            "brief": brief.to_dict(),
            "contract": contract.to_dict(),
            "produced": list(restricted.produced),
            "result": result or {},
        }

    def handler(self) -> Callable[..., Any]:
        raise NotImplementedError(f"{self.name} 未绑定执行处理器")
