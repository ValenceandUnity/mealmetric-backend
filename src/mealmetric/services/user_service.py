from mealmetric.models.user import User
from mealmetric.repos.user_repo import UserRepository


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    def get_user_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)
