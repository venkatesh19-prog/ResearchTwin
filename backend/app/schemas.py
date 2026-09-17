from typing import Optional

from pydantic import BaseModel


class ResearcherBase(BaseModel):
    name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    experience: Optional[int] = None

    research_areas: Optional[str] = None
    expertise: Optional[str] = None
    skills: Optional[str] = None

    publications: Optional[str] = None
    projects: Optional[str] = None

    profile_url: Optional[str] = None


class ResearcherCreate(ResearcherBase):
    pass


class ResearcherResponse(ResearcherBase):
    id: int

    class Config:
        from_attributes = True