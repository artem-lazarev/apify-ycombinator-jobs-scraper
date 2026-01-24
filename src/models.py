"""Pydantic models for data validation and structure."""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class SocialLinks(BaseModel):
    """Company social media links."""
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    github: Optional[str] = None
    facebook: Optional[str] = None
    crunchbase: Optional[str] = None


class Founder(BaseModel):
    """Founder information."""
    name: str
    role: Optional[str] = None
    description: Optional[str] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None


class Salary(BaseModel):
    """Salary range information."""
    min: Optional[int] = None
    max: Optional[int] = None
    currency: str = "USD"
    period: str = "yearly"  # "monthly", "yearly", etc.


class Equity(BaseModel):
    """Equity range information."""
    min: Optional[float] = None
    max: Optional[float] = None


class Job(BaseModel):
    """Job listing information."""
    jobId: str
    title: str
    jobUrl: str
    location: Optional[str] = None
    salary: Optional[Salary] = None
    equity: Optional[Equity] = None
    jobType: Optional[str] = None
    roleCategory: Optional[str] = None
    experience: Optional[str] = None
    visa: Optional[str] = None
    description: Optional[str] = None
    interviewProcess: Optional[str] = None


class Company(BaseModel):
    """Company information from hiring.json and scraped data."""
    id: int
    name: str
    slug: str
    formerNames: List[str] = Field(default_factory=list)
    tagline: Optional[str] = None
    longDescription: Optional[str] = None
    website: Optional[str] = None
    logoUrl: Optional[str] = None
    ycUrl: Optional[str] = None
    ycBatch: Optional[str] = None
    foundedYear: Optional[int] = None
    teamSize: Optional[int] = None
    status: Optional[str] = None
    stage: Optional[str] = None
    industry: Optional[str] = None
    subindustry: Optional[str] = None
    industries: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    topCompany: bool = False
    allLocations: Optional[str] = None
    regions: List[str] = Field(default_factory=list)
    socialLinks: SocialLinks = Field(default_factory=SocialLinks)


class CompanyOutput(BaseModel):
    """Complete output structure for a company with jobs and founders."""
    company: Company
    founders: List[Founder] = Field(default_factory=list)
    jobs: List[Job] = Field(default_factory=list)
    scrapedAt: datetime
