import os
from pathlib import Path
from typing import Optional

BASE_URL: str = "https://api.example.com"
MAX_RETRIES = 3


class BaseService:
    """Abstract base for all services."""

    def health_check(self) -> bool:
        return True


class UserService(BaseService):
    """Handles user operations."""

    @inject
    def __init__(self, repo: UserRepository, cache: CacheClient):
        self.repo = repo
        self.cache = cache

    def get_user(self, user_id: int) -> Optional[User]:
        cached = self.cache.get(user_id)
        if cached:
            return cached
        return self.repo.find_by_id(user_id)

    def create_user(self, name: str, email: str) -> User:
        user = User(name=name, email=email)
        self.repo.save(user)
        self.cache.set(user.id, user)
        return user

    @override
    def health_check(self) -> bool:
        return self.repo.ping() and self.cache.ping()

    def __repr__(self) -> str:
        return f"UserService(repo={self.repo})"


async def fetch_remote_config(url: str, timeout: int = 30) -> dict:
    """Fetch configuration from a remote endpoint."""
    response = await http_client.get(url, timeout=timeout)
    return response.json()


def calculate_score(values: list[float], weights: list[float]) -> float:
    """Compute weighted score."""
    total = sum(v * w for v, w in zip(values, weights))
    return round(total, 2)