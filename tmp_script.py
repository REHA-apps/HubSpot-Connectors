import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

supabase = create_client(url, key)

response = (
    supabase.table("thread_mappings").select("channel_id,thread_ts").limit(10).execute()
)
for r in response.data:
    print(
        "Channel: "
        + getattr(r, "get", lambda x: "")("channel_id")
        + " | TS: "
        + getattr(r, "get", lambda x: "")("thread_ts")
    )
