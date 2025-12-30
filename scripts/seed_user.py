#!/usr/bin/env python3
"""
Seed user script for IDE Orchestrator.

This script provides parity with the Go implementation's seed-user utility
found in archived/cmd/seed-user/main.go

Usage:
    python scripts/seed_user.py --email user@example.com --username testuser --password password123
    python scripts/seed_user.py --dev  # Creates default dev user
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import psycopg
from psycopg.rows import dict_row
from passlib.context import CryptContext
import uuid
from datetime import datetime


def get_database_url() -> str:
    """Get database URL from environment variables."""
    # Try DATABASE_URL first (production pattern)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    
    # Construct from individual components (development pattern)
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    database = os.getenv("POSTGRES_DB", "ide_orchestrator")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def create_user(email: str, username: str, password: str, database_url: str) -> str:
    """
    Create a new user in the database.
    
    Returns:
        User ID of created user
    """
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash(password)
    user_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            # Check if user already exists
            cur.execute(
                "SELECT id FROM users WHERE email = %s OR username = %s",
                (email, username)
            )
            existing_user = cur.fetchone()
            
            if existing_user:
                print(f"❌ User with email '{email}' or username '{username}' already exists")
                return str(existing_user["id"])
            
            # Create new user
            cur.execute(
                """
                INSERT INTO users (id, username, email, password_hash, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, username, email, hashed_password, now, now)
            )
            
            result = cur.fetchone()
            conn.commit()
            
            print(f"✅ Created user: {username} ({email}) with ID: {user_id}")
            return str(result["id"])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed user for IDE Orchestrator")
    parser.add_argument("--email", help="User email address")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", help="User password")
    parser.add_argument("--dev", action="store_true", help="Create default development user")
    
    args = parser.parse_args()
    
    # Handle dev mode
    if args.dev:
        email = "dev@example.com"
        username = "devuser"
        password = "devpassword"
        print("🔧 Creating default development user...")
    else:
        if not all([args.email, args.username, args.password]):
            print("❌ Error: --email, --username, and --password are required (or use --dev)")
            sys.exit(1)
        
        email = args.email
        username = args.username
        password = args.password
    
    # Get database URL
    try:
        database_url = get_database_url()
        print(f"🔗 Connecting to database...")
    except Exception as e:
        print(f"❌ Error getting database URL: {e}")
        sys.exit(1)
    
    # Create user
    try:
        user_id = create_user(email, username, password, database_url)
        print(f"🎉 User seeding completed successfully!")
        
        if args.dev:
            print("\n📝 Development user credentials:")
            print(f"   Email: {email}")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
            print(f"   User ID: {user_id}")
            print("\n💡 You can now use these credentials to test the API")
        
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()