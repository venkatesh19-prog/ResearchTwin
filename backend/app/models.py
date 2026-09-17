from sqlalchemy import Column, Integer, String, Text

from .database import Base


class Researcher(Base):
    __tablename__ = "researchers"

    id = Column(Integer, primary_key=True, index=True)

    # Basic information
    name = Column(String(100), nullable=False)
    department = Column(String(150))
    designation = Column(String(100))
    experience = Column(Integer)

    # Research information
    research_areas = Column(Text)
    expertise = Column(Text)
    skills = Column(Text)

    # Research work
    publications = Column(Text)
    projects = Column(Text)

    # External profile
    profile_url = Column(String(300))