from datetime import date, datetime

from pydantic import BaseModel


class DigestOut(BaseModel):
    id: int
    date: date
    content: str
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
