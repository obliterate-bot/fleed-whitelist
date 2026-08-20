import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime, timezone
from fleed_whitelist.database import db
from fleed_whitelist.crypto_engine import crypto_engine
from fleed_whitelist.server import check_and_enforce_anomalies

async def run_verification():
    await db.init()
    async with db.get_db() as conn:
        # Check watermark column
        c = await conn.execute('PRAGMA table_info(execution_logs);')
        cols = [r['name'] for r in await c.fetchall()]
        assert 'watermark' in cols, 'watermark column missing from execution_logs'
        print('[OK] Database schema migration verified: watermark column exists.')

        # 1. Create a dummy test script and license
        now_iso = datetime.now(timezone.utc).isoformat()
        await conn.execute('INSERT OR IGNORE INTO users (id, username, email, password_hash, salt, api_key, created_at) VALUES (999, "testuser", "test@test.com", "x", "y", "testkey", ?)', (now_iso,))
        await conn.execute('INSERT OR IGNORE INTO scripts (id, user_id, name, slug, raw_source, created_at, updated_at) VALUES (999, 999, "Test Script", "testslug", "print(1)", ?, ?)', (now_iso, now_iso))
        test_key = 'FLEED-TEST-AUTO-BAN-001'
        await conn.execute('INSERT OR REPLACE INTO licenses (id, script_id, license_key, note, is_banned, created_at) VALUES (999, 999, ?, "Test Key", 0, ?)', (test_key, now_iso))
        await conn.commit()

        # 2. Insert prior executions from 2 different Roblox accounts
        await conn.execute('INSERT INTO execution_logs (script_id, license_id, license_key, roblox_username, roblox_user_id, ip_address, status, timestamp) VALUES (999, 999, ?, "UserA", 1001, "1.1.1.1", "SUCCESS", ?)', (test_key, now_iso))
        await conn.execute('INSERT INTO execution_logs (script_id, license_id, license_key, roblox_username, roblox_user_id, ip_address, status, timestamp) VALUES (999, 999, ?, "UserB", 1002, "1.1.1.2", "SUCCESS", ?)', (test_key, now_iso))
        await conn.commit()

        # 3. Simulate 3rd distinct user executing -> triggers Anomaly Leak Shield
        c_lic = await conn.execute('SELECT * FROM licenses WHERE id = 999')
        lic_row = dict(await c_lic.fetchone())
        script_dict = {'id': 999, 'name': 'Test Script', 'slug': 'testslug', 'discord_webhook': None}

        err = await check_and_enforce_anomalies(
            conn=conn,
            script=script_dict,
            license_row=lic_row,
            roblox_username='UserC',
            roblox_user_id=1003,
            client_ip='1.1.1.3',
            executor='Synapse',
            place_id=12345,
            job_id='job-1',
            game_name='Test Game'
        )

        assert err is not None, 'Anomaly check should have triggered auto-ban for 3rd user!'
        print('[OK] Multi-account anomaly triggered successfully:', err)

        # 4. Verify license is now banned in DB
        c_banned = await conn.execute('SELECT is_banned, ban_reason FROM licenses WHERE id = 999')
        b_row = await c_banned.fetchone()
        assert b_row['is_banned'] == 1, 'License should be banned'
        print('[OK] License successfully auto-banned in database with reason:', b_row['ban_reason'])

        # 5. Test Watermark Trace Functionality
        wm = crypto_engine.generate_watermark(test_key, 'DEVICE_HWID_X')
        await conn.execute('INSERT INTO execution_logs (script_id, license_id, license_key, watermark, roblox_username, roblox_user_id, ip_address, status, details, timestamp) VALUES (999, 999, ?, ?, "BuyerUser", 5555, "8.8.8.8", "SUCCESS", ?, ?)', (test_key, wm, f"watermark={wm}", now_iso))
        await conn.commit()

        c_wm = await conn.execute('SELECT l.license_key, e.roblox_username, e.ip_address FROM execution_logs e JOIN licenses l ON e.license_id = l.id WHERE e.watermark = ?', (wm,))
        wm_row = await c_wm.fetchone()
        assert wm_row is not None and wm_row['license_key'] == test_key, 'Watermark lookup failed to match key'
        print('[OK] Forensic watermark trace matched buyer key:', wm_row['license_key'], 'User:', wm_row['roblox_username'])

        # Clean up test rows
        await conn.execute('DELETE FROM execution_logs WHERE script_id = 999')
        await conn.execute('DELETE FROM licenses WHERE script_id = 999')
        await conn.execute('DELETE FROM scripts WHERE id = 999')
        await conn.execute('DELETE FROM users WHERE id = 999')
        await conn.commit()
        print('[OK] Test cleanup completed. All anomaly & attribution tests passed!')

if __name__ == '__main__':
    asyncio.run(run_verification())
