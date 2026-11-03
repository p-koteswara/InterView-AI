import logging

from fastapi import APIRouter

from app.core.job_roles import list_roles
from app.schemas.roles import JobRoleResponse, RoleCatalogResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "",
    response_model=RoleCatalogResponse,
    summary="List available job roles",
    description="Returns the static job-role catalog used to scope interview tracks and knowledge base retrieval.",
)
def list_job_roles() -> RoleCatalogResponse:
    roles = list_roles()
    logger.debug("Serving %d job roles", len(roles))
    return RoleCatalogResponse(
        roles=[
            JobRoleResponse(
                slug=role.slug,
                title=role.title,
                category=role.category,
                description=role.description,
                key_skills=list(role.key_skills),
            )
            for role in roles
        ]
    )
