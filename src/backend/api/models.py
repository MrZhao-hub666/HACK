from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Channel = Literal[
    "facebook_comment",
    "dy",
    "xhs",
    "messenger",
    "facebook_form",
    "whatsapp",
    "instagram",
    "x_dm",
    "x_post",
    "tiktok",
    "telegram",
    "line",
    "wechat_kf",
    "wechat_comment",
    "manual",
]
CompanyKind = Literal[
    "车队", "维修厂", "维修及配件", "配件门店", "贸易商", "渠道伙伴", "待识别",
    "批发进口商", "经销代理商", "车桥厂", "OEM采购商", "ODM采购商",
]
Procurement = Literal["待核实", "可直接采购", "委托采购", "仅转售"]
ContactGender = Literal["", "女", "男", "其他", "不便透露"]
ContactAgeBand = Literal["", "under25", "25-34", "35-44", "45-54", "55-64", "65+"]
State = Literal["待处理", "跟进中", "等客户补充", "已结束"]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Event(Input):
    channel: Channel
    account: str = Field(default="kooying", min_length=1, max_length=120)
    event_id: str = Field(min_length=1, max_length=220)
    thread_key: str = Field(min_length=1, max_length=240)
    sender: str = Field(min_length=1, max_length=160)
    body: str = Field(default="", max_length=8000)
    attachment: str = Field(default="", max_length=1700)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("请提供带时区的时间")
        return value


class Discovery(Input):
    market: str = Field(min_length=1, max_length=70)
    kind: CompanyKind = "待识别"
    keywords: str = Field(default="", max_length=180)
    mode: Literal["samples", "live"] = "samples"


class Company(Input):
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(default="", max_length=80)
    kind: CompanyKind = "待识别"
    procurement: Procurement = "待核实"
    website: str = Field(default="", max_length=1400)
    social: str = Field(default="", max_length=1400)
    contact: str = Field(default="", max_length=350)
    contact_gender: ContactGender = ""
    contact_age_band: ContactAgeBand = ""
    evidence: str = Field(default="", max_length=2000)
    evidence_url: str = Field(default="", max_length=1400)
    notes: str = Field(default="", max_length=2000)
    next_action: str = Field(default="", max_length=500)


class InquiryEdit(Input):
    owner: str | None = Field(default=None, max_length=80)
    state: State | None = None
    intent: str | None = Field(default=None, max_length=40)
    next_action: str | None = Field(default=None, max_length=500)
    company_id: int | None = None
    actor: str = Field(
        default="销售",
        min_length=1,
        max_length=80,
        deprecated=True,
        description="旧客户端兼容字段，经办人以登录会话为准",
    )


class Note(Input):
    actor: str = Field(
        default="销售",
        min_length=1,
        max_length=80,
        deprecated=True,
        description="旧客户端兼容字段，经办人以登录会话为准",
    )
    text: str = Field(min_length=1, max_length=4000)


class Reply(Note):
    through_message_id: int | None = Field(default=None, gt=0)


class Merge(Input):
    target_id: int = Field(gt=0)
    actor: str = Field(
        default="销售",
        min_length=1,
        max_length=80,
        deprecated=True,
        description="旧客户端兼容字段，经办人以登录会话为准",
    )
