from supabase import create_client
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Create Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")   # Prefer your service role key for backend scripts
)

# Data to insert into the users table
data = {
    "full_name": "Yash Sharma",
    "email": "yash@example.com",
    "password": "hashed_password_here"   # Store hashed passwords only
}

# Insert row
response = supabase.table("users").insert(data).execute()

# Print inserted row
print(response.data)