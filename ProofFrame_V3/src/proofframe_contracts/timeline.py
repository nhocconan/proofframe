"""Exact mapping for one constant, positive-speed editorial segment only."""
from fractions import Fraction

from pydantic import Field, model_validator

from .models import Record


class TimelineSpan(Record):
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(gt=0)
    timeline_start_ms: int = Field(ge=0)
    speed_numerator: int = Field(default=1, gt=0)
    speed_denominator: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def increasing(self) -> "TimelineSpan":
        if self.source_end_ms <= self.source_start_ms:
            raise ValueError("source interval must be increasing")
        return self

    @property
    def speed(self) -> Fraction:
        return Fraction(self.speed_numerator, self.speed_denominator)

    def to_timeline(self, source_ms: int | Fraction) -> Fraction:
        if not self.source_start_ms <= source_ms <= self.source_end_ms:
            raise ValueError("source time is outside the trimmed segment")
        return self.timeline_start_ms + (Fraction(source_ms) - self.source_start_ms) / self.speed

    def to_source(self, timeline_ms: int | Fraction) -> Fraction:
        end = self.to_timeline(self.source_end_ms)
        if not self.timeline_start_ms <= timeline_ms <= end:
            raise ValueError("timeline time is outside the segment")
        return self.source_start_ms + (Fraction(timeline_ms) - self.timeline_start_ms) * self.speed
