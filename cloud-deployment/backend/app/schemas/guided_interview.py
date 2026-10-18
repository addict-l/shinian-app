"""Evidence contracts and durable state shared by all six life modules."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

InterviewModule = Literal['childhood', 'growth', 'work', 'family', 'later_life', 'reflection']


class GuidedQuote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: UUID
    quote: str = Field(min_length=1, max_length=12000)


class GuidedFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: Literal['activity', 'participants', 'self_role', 'before', 'after', 'choice', 'expression', 'wording']
    status: Literal['present', 'missing', 'partial', 'unknown', 'declined', 'conflict']
    evidence: list[GuidedQuote] = Field(default_factory=list, max_length=8)
    # A revision must cite a current, explicit correction; missing cannot erase facts.
    replaces_previous: bool = False


class GuidedUnit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=50)
    actor: Literal['self', 'other']
    kind: Literal['actual', 'request', 'assignment', 'static', 'summary']
    operation: str = Field(min_length=1, max_length=200)
    evidence: GuidedQuote


class GuidedLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: str
    end: str
    relation: Literal['sequence', 'response', 'state_change']
    evidence: list[GuidedQuote] = Field(min_length=1, max_length=4)


class GuidedEventAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    facts: list[GuidedFact] = Field(max_length=8)
    units: list[GuidedUnit] = Field(default_factory=list, max_length=24)
    links: list[GuidedLink] = Field(default_factory=list, max_length=24)
    process_unavailable: Literal['no', 'unknown', 'declined'] = 'no'
    unavailable_evidence: list[GuidedQuote] = Field(default_factory=list, max_length=4)


class GuidedQuestion(BaseModel):
    key: str
    target: str
    text: str
    accept_rule: str
    anchor: GuidedQuote | None = None


class GuidedAnswerAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['answered', 'partial', 'off_target', 'unknown', 'declined', 'paused']
    evidence: list[GuidedQuote] = Field(min_length=1, max_length=5)


class GuidedModuleAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    duplicate_memory_ids: list[UUID] = Field(default_factory=list, max_length=12)
    conflicting_memory_ids: list[UUID] = Field(default_factory=list, max_length=12)
    evidence: list[GuidedQuote] = Field(default_factory=list, max_length=12)


def _default_version():
    from app.services.contract_interview_state import enabled
    return 3 if enabled() else 2


def _default_runtime_version():
    from app.services.contract_interview_state import enabled, runtime
    return runtime().version if enabled() else None


class GuidedInterviewState(BaseModel):
    version: Literal[1, 2, 3] = Field(default_factory=_default_version)
    module: InterviewModule = 'childhood'
    module_selected: bool = True
    topic_index: int = Field(default=0, ge=0, le=100)
    runtime_version: str | None = Field(default_factory=_default_runtime_version)
    last_topic_skipped: bool = False
    contract_state: dict = Field(default_factory=dict)
    contract_history: dict[str, dict] = Field(default_factory=dict)
    legacy_checkpoint: dict | None = None
    phase: Literal['opening', 'exploring', 'supplement', 'review', 'paused', 'saved', 'module_review', 'finished'] = 'opening'
    resume_phase: str | None = None
    facts: list[GuidedFact] = Field(default_factory=list)
    units: list[GuidedUnit] = Field(default_factory=list)
    links: list[GuidedLink] = Field(default_factory=list)
    pending_question: GuidedQuestion | None = None
    answered_targets: list[str] = Field(default_factory=list)
    asked_targets: dict[str, int] = Field(default_factory=dict)
    unavailable_targets: list[str] = Field(default_factory=list)
    answer_status: str | None = None
    coverage: dict[str, bool] = Field(default_factory=dict)
    process_closed: bool = False
    background_sources: list[GuidedQuote] = Field(default_factory=list)
    saved_memory_ids: list[UUID] = Field(default_factory=list)
    qualified_memory_ids: list[UUID] = Field(default_factory=list)
    module_assessment: GuidedModuleAssessment | None = None
    module_assessed_count: int = 0
    chapter_ready: bool = False
    # Namespaced topic IDs and material counts remain distinct from story counts.
    processed_topics: dict[str, Literal['saved', 'skipped', 'reused']] = Field(default_factory=dict)
    material_memory_ids: list[UUID] = Field(default_factory=list)
    completed_modules: list[InterviewModule] = Field(default_factory=list)
    # Each module's durable checkpoint is restored explicitly when switching back.
    module_checkpoints: dict[str, dict] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def preserve_saved_catalog(cls, data):
        if isinstance(data, dict) and data.get('version') == 3 and 'runtime_version' not in data:
            return {**data, 'runtime_version': 'full-interview-v1.29.1'}
        return data

    @model_validator(mode='after')
    def migrate_childhood_counts(self):
        if self.version == 3 and self.runtime_version is None:
            # Missing marker means a persisted pre-v2 catalog, never the new
            # catalog at the same integer index. New creation pins explicitly.
            self.runtime_version = 'full-interview-v1.29.1'
        if self.version == 1:
            # Pilot v1 accepted story materials only. Preserve those verified IDs
            # without turning skipped or incomplete records into qualified ones.
            self.material_memory_ids = list(dict.fromkeys([*self.material_memory_ids, *self.qualified_memory_ids]))
            self.version = 2
        return self


class InterviewSwitch(BaseModel):
    module: InterviewModule
    expected_version: int = Field(ge=1)
