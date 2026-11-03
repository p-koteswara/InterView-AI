"""Static job-role catalog.

The catalog is intentionally a plain Python constant: the MVP needs a fixed,
curated set of hiring tracks rather than editable role records, so there is no
database table and no admin surface. The `slug` doubles as the knowledge base
directory name (``knowledge_base/<slug>/``), which keeps ingestion, storage
metadata and retrieval filters on a single shared identifier.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobRole:
    """A single hiring track exposed to the frontend and used to scope retrieval."""

    slug: str
    title: str
    category: str
    description: str
    key_skills: tuple[str, ...]


JOB_ROLES: tuple[JobRole, ...] = (
    JobRole(
        slug="ai-ml-engineer",
        title="AI/ML Engineer",
        category="Artificial Intelligence",
        description=(
            "Builds, trains and deploys machine learning and deep learning systems, "
            "from data pipelines and feature engineering through model serving and monitoring."
        ),
        key_skills=(
            "Python",
            "PyTorch",
            "TensorFlow",
            "Scikit-Learn",
            "Deep Learning",
            "MLOps",
            "Model Evaluation",
        ),
    ),
    JobRole(
        slug="backend-engineer",
        title="Backend Engineer",
        category="Software Engineering",
        description=(
            "Designs and operates server-side services and APIs, balancing correctness, "
            "latency, data modelling and reliability at scale."
        ),
        key_skills=(
            "Python",
            "REST APIs",
            "SQL",
            "PostgreSQL",
            "Caching",
            "Concurrency",
            "Distributed Systems",
        ),
    ),
    JobRole(
        slug="data-scientist",
        title="Data Scientist",
        category="Data Science",
        description=(
            "Turns raw data into measurable product and business decisions through "
            "statistical analysis, experimentation and predictive modelling."
        ),
        key_skills=(
            "Statistics",
            "Python",
            "Pandas",
            "SQL",
            "A/B Testing",
            "Feature Engineering",
            "Data Visualization",
        ),
    ),
)

ROLE_BY_SLUG: dict[str, JobRole] = {role.slug: role for role in JOB_ROLES}


def list_roles() -> list[JobRole]:
    """Return every role in catalog order."""
    return list(JOB_ROLES)


def get_role(slug: str) -> JobRole | None:
    """Look up a role by slug, or None when the slug is not part of the catalog."""
    return ROLE_BY_SLUG.get(slug)


def role_slugs() -> list[str]:
    """Return the catalog slugs, which are also the knowledge base directory names."""
    return list(ROLE_BY_SLUG)
