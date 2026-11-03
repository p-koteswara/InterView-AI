from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    institution: str = Field(description="Name of the university, college, or school")
    degree: Optional[str] = Field(default=None, description="Degree type (e.g. B.S., M.S., B.Tech)")
    field_of_study: Optional[str] = Field(default=None, description="Major, department or specialization")
    start_year: Optional[str] = Field(default=None, description="Start year or date")
    end_year: Optional[str] = Field(default=None, description="Graduation year or date (or 'Present')")
    grade: Optional[str] = Field(default=None, description="GPA, percentage, or honors if mentioned")


class ExperienceItem(BaseModel):
    company: str = Field(description="Name of the organization or company")
    role: str = Field(description="Job title or role")
    duration: Optional[str] = Field(default=None, description="Duration or dates of employment (e.g. '2022 - 2024')")
    description: list[str] = Field(default_factory=list, description="Key responsibilities, achievements, or project highlights")


class ProjectItem(BaseModel):
    title: str = Field(description="Project name or title")
    description: Optional[str] = Field(default=None, description="Short summary of what was built and impact")
    technologies: list[str] = Field(default_factory=list, description="Technologies, languages, or tools utilized")


class CandidateProfile(BaseModel):
    name: Optional[str] = Field(default=None, description="Candidate's full name")
    email: Optional[str] = Field(default=None, description="Primary email address")
    phone: Optional[str] = Field(default=None, description="Contact phone number if available")
    location: Optional[str] = Field(default=None, description="City, country, or location if mentioned")
    education: list[EducationItem] = Field(default_factory=list, description="Academic history")
    work_experience: list[ExperienceItem] = Field(default_factory=list, description="Professional work experience")
    technical_skills: list[str] = Field(default_factory=list, description="Core technical competencies")
    programming_languages: list[str] = Field(default_factory=list, description="Programming languages (e.g. Python, Go, C++)")
    frameworks_and_tools: list[str] = Field(default_factory=list, description="Frameworks, libraries, and developer tools")
    projects: list[ProjectItem] = Field(default_factory=list, description="Personal, academic, or professional projects")
    certifications: list[str] = Field(default_factory=list, description="Accreditations and certifications")
    relevant_domains: list[str] = Field(default_factory=list, description="Domain areas (e.g. Backend Engineering, AI/ML, Cloud Infrastructure)")


class ResumeUploadResponse(BaseModel):
    candidate_id: str
    filename: str
    extracted_text: str
    profile: CandidateProfile
    created_at: datetime
