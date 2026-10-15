from pydantic import BaseModel, HttpUrl


class PDFItem(BaseModel):
    url: HttpUrl
    id: str
