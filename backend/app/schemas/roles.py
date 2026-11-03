from pydantic import BaseModel, Field


class JobRoleResponse(BaseModel):
    slug: str = Field(description="Stable identifier; also the knowledge base directory name")
    title: str = Field(description="Human readable role title")
    category: str = Field(description="Broad hiring category the role belongs to")
    description: str = Field(description="Short summary of the role's responsibilities")
    key_skills: list[str] = Field(default_factory=list, description="Core skills for the role")


class RoleCatalogResponse(BaseModel):
    roles: list[JobRoleResponse] = Field(default_factory=list, description="Available job roles")
