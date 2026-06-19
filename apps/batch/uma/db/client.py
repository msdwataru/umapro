from functools import lru_cache
from supabase import create_client, Client
from uma.config import config


@lru_cache(maxsize=1)
def get_client() -> Client:
    """service_role キーを使ったSupabaseクライアント（RLSをバイパス）"""
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
