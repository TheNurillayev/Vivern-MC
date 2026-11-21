from pydantic import BaseModel
from typing import Optional

class TelegramInitDataRequest(BaseModel):
    init_data: str

class UserInfo(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    language_code: Optional[str] = "uz"
    trial_count: int
    extra_trials: Optional[int] = 0
    save_trials: Optional[bool] = False
    is_blocked: Optional[bool] = False
    is_admin: bool
    avatar_url: Optional[str] = None

class AuthResponse(BaseModel):
    success: bool
    user: UserInfo
    token: str
