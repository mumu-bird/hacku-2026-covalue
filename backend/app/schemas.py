from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Command(Input):
    expected_version: int = Field(ge=1)


class Login(Input):
    username: str
    case: str = "cash"


class ListingInput(Input):
    kind: Literal["REQUEST", "OFFER"] = "REQUEST"
    title: str = Field(min_length=2, max_length=120)
    category: Literal["spreadsheet", "tutoring", "english"]
    scenario: str = Field(default="", max_length=2000)
    difficulty: Literal["basic", "medium", "advanced"] = "basic"
    workload: Literal["small", "medium", "large"] = "medium"
    required_skills: list[str] = Field(default_factory=list, max_length=10)
    preferred_skills: list[str] = Field(default_factory=list, max_length=10)
    duration: int = Field(default=60, gt=0, le=1440)
    preparation: int = Field(default=0, ge=0, le=1440)
    travel: int = Field(default=0, ge=0, le=1440)
    include_preparation: bool = False
    include_travel: bool = False
    material_amount: int = Field(default=0, ge=0, le=10000000)
    transport_amount: int = Field(default=0, ge=0, le=10000000)
    delivery_standard: str = Field(default="", max_length=2000)
    service_mode: Literal["ONLINE", "OFFLINE"] = "ONLINE"
    location: str = Field(default="線上", max_length=200)
    start: datetime
    end: datetime
    accepted_modes: list[Literal["MONEY", "BARTER", "HYBRID"]] = Field(
        default_factory=lambda: ["MONEY", "BARTER", "HYBRID"], min_length=1
    )

    @model_validator(mode="after")
    def times(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("時段必須包含時區")
        if self.end <= self.start:
            raise ValueError("結束時間必須晚於開始")
        return self


class ListingPatch(ListingInput):
    expected_version: int = Field(ge=1)


class ProposalInput(Input):
    listing_id: str
    provider_id: str | None = None
    mode: Literal["MONEY", "BARTER", "HYBRID"] = "MONEY"
    negotiation_path: Literal["DIRECT", "ASSISTED"] = "DIRECT"
    reverse_listing_id: str | None = None


class Revise(Command):
    mode: Literal["MONEY", "BARTER", "HYBRID"] | None = None
    amount: int | None = Field(default=None, ge=0, le=10000000)
    reverse_minutes: int | None = Field(default=None, gt=0, le=1440)
    cash_payer_id: str | None = None
    scope: ListingInput | None = None


class Preference(Command):
    scope_version: int = Field(ge=1)
    value: int = Field(ge=0, le=10000000)


class SelectCandidate(Command):
    value: int = Field(ge=0, le=10000000)


class Perspective(Command):
    scope_version: int = Field(ge=1)
    received_value: int = Field(ge=0, le=10000000)
    reason: str = Field(min_length=5, max_length=1000)
    shared: bool = False


class MechanismInput(Input):
    quality: int = Field(default=90, ge=0, le=100)
    main_minutes: int = Field(default=60, ge=15, le=240)
    preparation: int = Field(default=0, ge=0, le=60)
    window_minutes: int = Field(default=240, ge=30, le=1440)
    lower: int = Field(default=60, ge=0, le=1440)
    upper: int = Field(default=120, ge=0, le=1440)
    evidence_mode: Literal["VERIFIED", "MISSING"] = "VERIFIED"


class AgreementInput(Input):
    proposal_id: str
    expected_version: int = Field(ge=1)
    stage_amounts: list[int] | None = None
    rounds: int = Field(default=2, ge=1, le=20)
    first_provider_id: str | None = None


class Confirm(Command):
    terms_version: int = Field(ge=1)


class EvidenceInput(Input):
    category: Literal["spreadsheet", "tutoring", "english"]
    kind: Literal["WORK", "ASSESSMENT"]
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=5, max_length=5000)
    skills: list[str] = Field(default_factory=list, max_length=10)
    difficulty: Literal["basic", "medium", "advanced"] = "basic"


class Scores(Input):
    correctness: int = Field(ge=0, le=100)
    completeness: int = Field(ge=0, le=100)
    independence: int = Field(ge=0, le=100)


class EvidenceReview(Input):
    approve: bool = True
    scores: Scores
    basis: str = Field(min_length=5, max_length=2000)


class Submit(Command):
    evidence: str = Field(min_length=5, max_length=5000)
    execution_minutes: int = Field(gt=0, le=1440)
    preparation_minutes: int = Field(default=0, ge=0, le=1440)
    travel_minutes: int = Field(default=0, ge=0, le=1440)


class Accept(Command):
    scores: Scores
    note: str = Field(default="符合約定交付標準", max_length=2000)


class Reason(Command):
    reason: str = Field(min_length=3, max_length=2000)


class DisputeInput(Reason):
    obligation_id: str | None = None


class Review(Command):
    outcome: Literal["RESUME", "ACCEPT", "REDO", "CLOSEOUT", "UNRESOLVED"]
    basis: str = Field(min_length=5, max_length=3000)
    confirmed_breach_user_id: str | None = None
    scores: Scores | None = None


class CloseoutAction(Input):
    obligation_id: str
    action: Literal["CONTINUE", "WAIVE"]


class FundAction(Input):
    payment_id: str
    action: Literal["RELEASE", "REFUND", "HOLD"]


class CloseoutInput(Command):
    obligations: list[CloseoutAction]
    payments: list[FundAction] = Field(default_factory=list)
    reason: str = Field(min_length=3, max_length=2000)


class CloseoutConfirm(Command):
    agreement_version: int = Field(ge=1)


class Reopen(Command):
    pass
