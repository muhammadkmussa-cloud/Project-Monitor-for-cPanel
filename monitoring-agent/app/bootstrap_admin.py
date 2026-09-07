"""Run interactively inside the agent: python -m app.bootstrap_admin."""
import asyncio
import getpass
from uuid import uuid4
from app.db import get_pool, close_pool
from app.services.rbac_service import RBACService

async def main():
    pool=await get_pool()
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(918245)")
            if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE role IN ('admin','owner') AND status='active')"):
                raise SystemExit('An active administrator already exists; no changes made.')
            email=input('Administrator email: ').strip()
            name=input('Administrator name: ').strip()
            password=getpass.getpass('Password (at least 10 characters): ')
            if len(password)<10 or '@' not in email or not name:
                raise SystemExit('Invalid administrator details; no changes made.')
            if password!=getpass.getpass('Confirm password: '):
                raise SystemExit('Passwords do not match; no changes made.')
            cid=await conn.fetchval("SELECT client_id FROM clients WHERE status='active' ORDER BY created_at LIMIT 1")
            if not cid:
                cid=uuid4()
                await conn.execute("INSERT INTO clients (client_id,client_name) VALUES ($1,'Default Client')",cid)
            digest=await asyncio.to_thread(RBACService()._hash_password,password)
            await conn.execute("INSERT INTO users (client_id,email,name,password_hash,role) VALUES ($1,$2,$3,$4,'admin')",cid,email,name,digest)
            print('Administrator created.')
    finally:
        await close_pool()

if __name__=='__main__':
    asyncio.run(main())
