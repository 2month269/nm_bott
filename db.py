# db.py
import os
import time
import ssl
import logging
from urllib.parse import urlparse, unquote
import pg8000.dbapi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DatabaseEngine")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Переменная DATABASE_URL не задана в настройках Railway!")

db_info = urlparse(DATABASE_URL)

def get_conn():
    """Создает SSL подключение к Supabase через pg8000"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    return pg8000.dbapi.connect(
        user=db_info.username,
        password=unquote(db_info.password) if db_info.password else None,
        host=db_info.hostname,
        port=db_info.port or 5432,
        database=db_info.path[1:],
        ssl_context=ctx
    )

def init_db():
    """Инициализирует все таблицы базы данных при старте приложения"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        # 1. Основная таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance DOUBLE PRECISION DEFAULT 10000,
                nmp_balance DOUBLE PRECISION DEFAULT 10, 
                exchange_balance DOUBLE PRECISION DEFAULT 0,
                exchange_nmp_balance DOUBLE PRECISION DEFAULT 0,
                games_played INT DEFAULT 0,
                lost_coins DOUBLE PRECISION DEFAULT 0,
                turnover DOUBLE PRECISION DEFAULT 0,
                is_blocked INT DEFAULT 0,
                last_bonus_time INT DEFAULT 0,
                last_daily_bonus_time INT DEFAULT 0,
                savings_balance DOUBLE PRECISION DEFAULT 0,
                savings_last_claim INT DEFAULT 0,
                has_chequebook INT DEFAULT 0,
                sell_rate DOUBLE PRECISION DEFAULT 2100, 
                buy_rate DOUBLE PRECISION DEFAULT 2100,  
                exchange_notifications INT DEFAULT 1, 
                rating INT DEFAULT 114, 
                total_rating_sum INTEGER DEFAULT 0,
                total_ratings_count INTEGER DEFAULT 0,
                referrer_id BIGINT DEFAULT NULL,
                ref_count INT DEFAULT 0,
                ref_earned DOUBLE PRECISION DEFAULT 0,
                ref_bonus_claimed INT DEFAULT 0,
                first_name VARCHAR(255) DEFAULT NULL,
                username VARCHAR(255) DEFAULT NULL,
                bricks INT8 DEFAULT 0,
                lightnings INT8 DEFAULT 0,
                last_brick_time INT8 DEFAULT 0,
                created_at VARCHAR(50) DEFAULT TO_CHAR(NOW(), 'DD-MM-YYYY HH24:MI')
            )
        """)
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(255);")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bricks INT8 DEFAULT 0;")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lightnings INT8 DEFAULT 0;")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_brick_time INT8 DEFAULT 0;")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_rating_sum INTEGER DEFAULT 0;")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_ratings_count INTEGER DEFAULT 0;")

        # 2. Таблица NFT экспонатов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_nfts (
                nft_id SERIAL PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                nft_name VARCHAR(100) DEFAULT 'Драко',
                serial_number INT NOT NULL,
                purchase_date VARCHAR(50) NOT NULL,
                is_equipped BOOLEAN DEFAULT FALSE,
                color VARCHAR(50) DEFAULT 'Простой зелёный',
                pattern VARCHAR(50) DEFAULT 'Без узора',
                outfit VARCHAR(50) DEFAULT 'Без одежды',
                rarity VARCHAR(50) DEFAULT 'Обычный',
                estimated_price VARCHAR(100) DEFAULT '999,000 nCoin',
                level INT DEFAULT 1,
                image_key VARCHAR(100) DEFAULT 'base_green'
            )
        """)
        cursor.execute("ALTER TABLE user_nfts ADD COLUMN IF NOT EXISTS outfit VARCHAR(50) DEFAULT 'Без одежды';")
        cursor.execute("ALTER TABLE user_nfts ADD COLUMN IF NOT EXISTS rarity VARCHAR(50) DEFAULT 'Обычный';")
        cursor.execute("ALTER TABLE user_nfts ADD COLUMN IF NOT EXISTS estimated_price VARCHAR(100) DEFAULT '999,000 nCoin';")
        
        # 3. Таблица истории игр
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                history_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                game_name VARCHAR(100) NOT NULL,
                bet DOUBLE PRECISION NOT NULL,
                win DOUBLE PRECISION DEFAULT 0,
                is_win BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS basketball_rounds (
                round_id VARCHAR(32) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                bet DOUBLE PRECISION NOT NULL,
                choice VARCHAR(10) NOT NULL,
                dice_value INT NOT NULL,
                server_seed VARCHAR(128) NOT NULL,
                server_hash VARCHAR(64) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Таблица чеков
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cheques (
                cheque_id VARCHAR(50) PRIMARY KEY,
                creator_id BIGINT,
                total_amount DOUBLE PRECISION,
                activations_total INT,
                activations_left INT,
                password VARCHAR(100),
                description TEXT,
                target_user_id BIGINT,
                notifications BOOLEAN DEFAULT TRUE,
                created_at INT
            )
        """)

        # 5. Регистрация активаций чеков
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cheque_claims (
                cheque_id VARCHAR(50),
                user_id BIGINT,
                claimed_at INT8,
                PRIMARY KEY (cheque_id, user_id)
            )
        """)
        cursor.execute("ALTER TABLE cheque_claims ADD COLUMN IF NOT EXISTS claimed_at INT8;")

        # 6. Срочные депозиты в банке
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                end_time INT,
                payout DOUBLE PRECISION,
                days INT
            )
        """)

        # 7. История P2P сделок в обменнике
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exchange_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username VARCHAR(255),
                nmp_amount DOUBLE PRECISION,
                ncoin_amount DOUBLE PRECISION,
                tx_type VARCHAR(10), 
                timestamp INT
            )
        """)

        # 8. Логирование действий пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                action VARCHAR(100),
                amount DOUBLE PRECISION DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 9. Таблица промокодов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code VARCHAR(100) PRIMARY KEY,
                amount DOUBLE PRECISION,
                max_activations INT,
                activations_left INT,
                created_at INT
            )
        """)

        # 10. Логи активации промокодов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promocode_claims (
                code VARCHAR(100),
                user_id BIGINT,
                PRIMARY KEY (code, user_id)
            )
        """)

        # 11. Таблица идей еженедельного турнира
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournament_ideas (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                first_name VARCHAR(255),
                idea_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 12. Таблица рейтингов сделок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY,
                deal_id INTEGER,
                from_user_id BIGINT,
                to_user_id BIGINT,
                stars INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(deal_id, from_user_id)
            )
        """)
        
        conn.commit()
        logger.info("Все таблицы базы данных успешно проверены и инициализированы.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
    finally:
        cursor.close()
        conn.close()


# --- СИСТЕМА ОЦЕНОК И РЕЙТИНГА ---

def get_user_rating(user_id: int) -> str:
    """Возвращает форматированную строку со средним рейтингом пользователя"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT total_rating_sum, total_ratings_count FROM users WHERE user_id = %s", (user_id,))
        res = cursor.fetchone()
        if res and res[1] and res[1] > 0:
            avg = res[0] / res[1]
            return f"{avg:.1f} ({res[1]} отз.)"
        return "Нет оценок"
    except Exception as e:
        logger.error(f"Ошибка получения рейтинга: {e}")
        return "Нет оценок"
    finally:
        cursor.close()
        conn.close()

def add_rating(deal_id: int, from_user_id: int, to_user_id: int, stars: int) -> bool:
    """Добавляет оценку за сделку от 1 до 5 звезд"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ratings (deal_id, from_user_id, to_user_id, stars) VALUES (%s, %s, %s, %s)",
            (deal_id, from_user_id, to_user_id, stars)
        )
        cursor.execute("""
            UPDATE users 
            SET total_rating_sum = COALESCE(total_rating_sum, 0) + %s, 
                total_ratings_count = COALESCE(total_ratings_count, 0) + 1 
            WHERE user_id = %s
        """, (stars, to_user_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления рейтинга: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        conn.close()


# --- БЛОК СИСТЕМНЫХ ФУНКЦИЙ ПОЛЬЗОВАТЕЛЕЙ ---

def get_user(user_id: int, first_name: str = None, username: str = None) -> dict:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if first_name or username:
            cursor.execute(
                "UPDATE users SET first_name = COALESCE(%s, first_name), username = COALESCE(%s, username) WHERE user_id = %s",
                (first_name, username, user_id)
            )
            conn.commit()

        cursor.execute("""
            SELECT balance, nmp_balance, games_played, lost_coins, turnover, created_at, is_blocked, 
                   last_bonus_time, last_daily_bonus_time, savings_balance, savings_last_claim, has_chequebook, 
                   sell_rate, buy_rate, exchange_notifications, exchange_balance, exchange_nmp_balance, 
                   referrer_id, ref_count, ref_earned, ref_bonus_claimed, first_name, username, bricks, last_brick_time, lightnings,
                   total_rating_sum, total_ratings_count
            FROM users WHERE user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            now_ts = int(time.time())
            cursor.execute("""
                INSERT INTO users (user_id, savings_last_claim, first_name, username) 
                VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING
            """, (user_id, now_ts, first_name, username))
            cursor.execute("INSERT INTO activity_logs (user_id, action) VALUES (%s, 'register')", (user_id,))
            conn.commit()
            return get_user(user_id, first_name, username)

        return {
            "balance": row[0], "nmp_balance": row[1], "games_played": row[2], "lost_coins": row[3], "turnover": row[4],
            "created_at": row[5], "is_blocked": bool(row[6]), "last_bonus_time": row[7], "last_daily_bonus_time": row[8],
            "savings_balance": row[9], "savings_last_claim": row[10], "has_chequebook": bool(row[11]),
            "sell_rate": row[12], "buy_rate": row[13], "exchange_notifications": bool(row[14]),
            "exchange_balance": row[15], "exchange_nmp_balance": row[16], "referrer_id": row[17],
            "ref_count": row[18], "ref_earned": row[19], "ref_bonus_claimed": bool(row[20]),
            "first_name": row[21], "username": row[22], 
            "bricks": row[23] if len(row) > 23 and row[23] is not None else 0,
            "last_brick_time": row[24] if len(row) > 24 and row[24] is not None else 0,
            "lightnings": row[25] if len(row) > 25 and row[25] is not None else 0,
            "total_rating_sum": row[26] if len(row) > 26 and row[26] is not None else 0,
            "total_ratings_count": row[27] if len(row) > 27 and row[27] is not None else 0
        }
    finally:
        cursor.close()
        conn.close()

def find_user_by_username_or_id(identifier: str):
    """Поиск пользователя по ID или @username"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        clean_id = identifier.strip().lstrip("@")
        if clean_id.isdigit():
            cursor.execute("SELECT user_id, first_name, username FROM users WHERE user_id = %s", (int(clean_id),))
        else:
            cursor.execute("SELECT user_id, first_name, username FROM users WHERE LOWER(username) = LOWER(%s)", (clean_id,))
        row = cursor.fetchone()
        if row:
            return {"user_id": row[0], "first_name": row[1], "username": row[2]}
        return None
    finally:
        cursor.close()
        conn.close()

def update_balance(user_id: int, amount: float):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_nmp_balance(user_id: int, amount: float):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET nmp_balance = nmp_balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_bricks(user_id: int, amount: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET bricks = GREATEST(0, COALESCE(bricks, 0) + %s) WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_lightnings(user_id: int, amount: int):
    """Обновляет количество Грозовых Разрядов у пользователя"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET lightnings = GREATEST(0, COALESCE(lightnings, 0) + %s) WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def check_brick_cooldown(user_id: int, cooldown_seconds: int = 450) -> tuple[bool, int]:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COALESCE(last_brick_time, 0) FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        last_time = row[0] if row else 0
        now = int(time.time())
        elapsed = now - last_time
        if elapsed >= cooldown_seconds:
            return True, 0
        else:
            return False, cooldown_seconds - elapsed
    finally:
        cursor.close()
        conn.close()

def update_last_brick_time(user_id: int, timestamp: int = None):
    if timestamp is None:
        timestamp = int(time.time())
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET last_brick_time = %s WHERE user_id = %s", (timestamp, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_user_field(user_id: int, field_name: str, value):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(f"UPDATE users SET {field_name} = %s WHERE user_id = %s", (value, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_last_daily_bonus_time(user_id: int, timestamp: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET last_daily_bonus_time = %s WHERE user_id = %s", (timestamp, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# --- NFT ФУНКЦИИ ---

def get_total_nfts_count(nft_name: str = "Драко") -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM user_nfts WHERE nft_name = %s", (nft_name,))
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        cursor.close()
        conn.close()

def create_nft(owner_id: int, nft_name: str = "Драко", image_key: str = None) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COALESCE(MAX(serial_number), 0) + 1 FROM user_nfts WHERE nft_name = %s", (nft_name,))
        serial_num = cursor.fetchone()[0]
        purchase_date = time.strftime("%d.%m.%Y %H:%M")
        
        if not image_key:
            if "car" in nft_name.lower() or "hypercar" in nft_name.lower():
                image_key = "base_car"
            else:
                image_key = "base_green"
                
        est_price = "149,900,000 nCoin" if ("car" in nft_name.lower() or "hypercar" in nft_name.lower()) else "999,000 nCoin"
        
        cursor.execute("""
            INSERT INTO user_nfts (owner_id, nft_name, serial_number, purchase_date, color, pattern, outfit, rarity, estimated_price, level, image_key)
            VALUES (%s, %s, %s, %s, 'Простой зелёный', 'Без узора', 'Без одежды', 'Обычный', %s, 1, %s)
            RETURNING nft_id
        """, (owner_id, nft_name, serial_num, purchase_date, est_price, image_key))
        
        nft_id = cursor.fetchone()[0]
        conn.commit()
        return nft_id
    finally:
        cursor.close()
        conn.close()

def get_user_nfts(owner_id: int) -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT nft_id, nft_name, serial_number, purchase_date, is_equipped, color, pattern, outfit, rarity, estimated_price, level, image_key
            FROM user_nfts WHERE owner_id = %s ORDER BY nft_id ASC
        """, (owner_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "nft_id": r[0], "nft_name": r[1], "serial_number": r[2], "purchase_date": r[3],
                "is_equipped": bool(r[4]), "color": r[5], "pattern": r[6], "outfit": r[7], 
                "rarity": r[8], "estimated_price": r[9], "level": r[10], "image_key": r[11]
            })
        return result
    finally:
        cursor.close()
        conn.close()

def get_nft_by_id(nft_id: int) -> dict:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT nft_id, owner_id, nft_name, serial_number, purchase_date, is_equipped, color, pattern, outfit, rarity, estimated_price, level, image_key
            FROM user_nfts WHERE nft_id = %s
        """, (nft_id,))
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "nft_id": r[0], "owner_id": r[1], "nft_name": r[2], "serial_number": r[3],
            "purchase_date": r[4], "is_equipped": bool(r[5]), "color": r[6], "pattern": r[7],
            "outfit": r[8], "rarity": r[9], "estimated_price": r[10], "level": r[11], "image_key": r[12]
        }
    finally:
        cursor.close()
        conn.close()

def get_equipped_nft(owner_id: int) -> dict:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT nft_id, owner_id, nft_name, serial_number, purchase_date, is_equipped, color, pattern, outfit, rarity, estimated_price, level, image_key
            FROM user_nfts WHERE owner_id = %s AND is_equipped = TRUE LIMIT 1
        """, (owner_id,))
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "nft_id": r[0], "owner_id": r[1], "nft_name": r[2], "serial_number": r[3],
            "purchase_date": r[4], "is_equipped": bool(r[5]), "color": r[6], "pattern": r[7],
            "outfit": r[8], "rarity": r[9], "estimated_price": r[10], "level": r[11], "image_key": r[12]
        }
    finally:
        cursor.close()
        conn.close()

def toggle_equip_nft(owner_id: int, nft_id: int) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_equipped FROM user_nfts WHERE nft_id = %s AND owner_id = %s", (nft_id, owner_id))
        r = cursor.fetchone()
        if not r:
            return False
        curr_status = bool(r[0])
        
        cursor.execute("UPDATE user_nfts SET is_equipped = FALSE WHERE owner_id = %s", (owner_id,))
        
        if not curr_status:
            cursor.execute("UPDATE user_nfts SET is_equipped = TRUE WHERE nft_id = %s AND owner_id = %s", (nft_id, owner_id))
            
        conn.commit()
        return not curr_status
    finally:
        cursor.close()
        conn.close()

def update_nft_attrs(nft_id: int, color: str = None, pattern: str = None, outfit: str = None, rarity: str = None, estimated_price: str = None, level: int = None, image_key: str = None):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        fields = []
        values = []
        if color is not None:
            fields.append("color = %s"); values.append(color)
        if pattern is not None:
            fields.append("pattern = %s"); values.append(pattern)
        if outfit is not None:
            fields.append("outfit = %s"); values.append(outfit)
        if rarity is not None:
            fields.append("rarity = %s"); values.append(rarity)
        if estimated_price is not None:
            fields.append("estimated_price = %s"); values.append(estimated_price)
        if level is not None:
            fields.append("level = %s"); values.append(level)
        if image_key is not None:
            fields.append("image_key = %s"); values.append(image_key)
            
        if not fields:
            return
            
        values.append(nft_id)
        sql = f"UPDATE user_nfts SET {', '.join(fields)} WHERE nft_id = %s"
        cursor.execute(sql, tuple(values))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def transfer_nft_owner(nft_id: int, new_owner_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE user_nfts 
            SET owner_id = %s, is_equipped = FALSE 
            WHERE nft_id = %s
        """, (new_owner_id, nft_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# --- РЕФЕРАЛЫ И СТАТИСТИКА ИГР ---

def qualify_referral(uid: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT referrer_id, ref_bonus_claimed FROM users WHERE user_id = %s", (uid,))
        row = cursor.fetchone()
        if row and row[0] and not row[1]:
            cursor.execute("""
                UPDATE users 
                SET balance = balance + 100000, ref_earned = ref_earned + 100000, ref_count = ref_count + 1 
                WHERE user_id = %s
            """, (row[0],))
            cursor.execute("UPDATE users SET ref_bonus_claimed = 1 WHERE user_id = %s", (uid,))
            conn.commit()
    finally:
        cursor.close()
        conn.close()

def log_game_result(user_id: int, game_name: str, bet: float, win: float, is_win: bool):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO game_history (user_id, game_name, bet, win, is_win) VALUES (%s, %s, %s, %s, %s)",
            (int(user_id), str(game_name), float(bet), float(win), bool(is_win))
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка log_game_result: {e}")
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def add_stats(uid: int, is_lost: bool, lost_amount: float = 0, bet_amount: float = 0, game_name: str = "game", win_amount: float = 0):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if is_lost:
            cursor.execute("""
                UPDATE users 
                SET games_played = games_played + 1, lost_coins = lost_coins + %s, turnover = turnover + %s 
                WHERE user_id = %s
            """, (lost_amount, bet_amount, uid))
            
            cursor.execute("SELECT referrer_id FROM users WHERE user_id = %s", (uid,))
            ref = cursor.fetchone()
            if ref and ref[0]:
                ref_reward = round(lost_amount * 0.02, 2)
                cursor.execute("""
                    UPDATE users 
                    SET balance = balance + %s, ref_earned = ref_earned + %s 
                    WHERE user_id = %s
                """, (ref_reward, ref_reward, ref[0]))
        else:
            cursor.execute("""
                UPDATE users 
                SET games_played = games_played + 1, turnover = turnover + %s 
                WHERE user_id = %s
            """, (bet_amount, uid))
            
        cursor.execute("INSERT INTO activity_logs (user_id, action, amount) VALUES (%s, 'game_play', %s)", (uid, bet_amount))
        
        cursor.execute(
            "INSERT INTO game_history (user_id, game_name, bet, win, is_win) VALUES (%s, %s, %s, %s, %s)",
            (int(uid), str(game_name), float(bet_amount), float(win_amount if not is_lost else 0), not is_lost)
        )
        
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка add_stats: {e}")
    finally:
        cursor.close()
        try: conn.close()
        except: pass
    qualify_referral(uid)

def get_user_game_history(user_id: int, hours: int = 72):
    """Возвращает историю игр пользователя за указанное число часов (по умолчанию 72ч)"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT game_name, bet, win, is_win, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI') as date_str
            FROM game_history
            WHERE user_id = %s AND created_at >= NOW() - (INTERVAL '1 hour' * %s)
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (int(user_id), int(hours))
        )
        rows = cursor.fetchall()
        
        result = []
        game_titles = {
            "mines": "💣 Мины", "crash": "🚀 Краш", "dice": "🎲 Кубик",
            "darts": "🎯 Дартс", "slots": "🎰 Слоты", "coin": "🪙 Монетка",
            "basketball": "🏀 Баскетбол", "tower": "🗼 Башня", "frog": "🐸 Квак",
            "sharik": "🔮 Шарик", "hypercar": "🏎️ Гиперкар", "smart": "📺 Всезнайка",
            "roulette": "🎡 Рулетка"
        }
        
        for r in rows:
            g_code, bet_val, win_val, is_win_val, date_s = r
            result.append({
                "game_name": game_titles.get(g_code, g_code),
                "bet": float(bet_val),
                "win": float(win_val),
                "is_win": bool(is_win_val),
                "date": date_s
            })
        return result
    except Exception as e:
        logger.error(f"Ошибка get_user_game_history: {e}")
        return []
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def get_user_transfers_history(user_id: int, hours: int = 72) -> list:
    """Возвращает историю всех переводов и финансовых операций пользователя за последние 72 часа"""
    conn = get_conn()
    cursor = conn.cursor()
    transfers = []
    try:
        # 1. Логи из activity_logs (переводы, донаты, бонусы)
        cursor.execute(
            """
            SELECT action, amount, TO_CHAR(timestamp, 'DD.MM.YYYY HH24:MI') as date_str
            FROM activity_logs
            WHERE user_id = %s AND action != 'game_play' AND action != 'register'
              AND timestamp >= NOW() - (INTERVAL '1 hour' * %s)
            ORDER BY timestamp DESC
            LIMIT 30
            """,
            (int(user_id), int(hours))
        )
        rows = cursor.fetchall()
        for r in rows:
            act, amt, dt = r
            transfers.append({
                "action": act,
                "amount": float(amt or 0),
                "date": dt
            })

        # 2. История P2P обменника
        cursor.execute(
            """
            SELECT tx_type, nmp_amount, ncoin_amount, TO_CHAR(TO_TIMESTAMP(timestamp), 'DD.MM.YYYY HH24:MI') as date_str
            FROM exchange_history
            WHERE user_id = %s AND TO_TIMESTAMP(timestamp) >= NOW() - (INTERVAL '1 hour' * %s)
            ORDER BY timestamp DESC
            LIMIT 20
            """,
            (int(user_id), int(hours))
        )
        ex_rows = cursor.fetchall()
        for r in ex_rows:
            tx_type, nmp_amt, ncoin_amt, dt = r
            transfers.append({
                "action": f"Обмен P2P ({tx_type})",
                "amount": float(ncoin_amt or 0),
                "date": dt
            })

        # 3. Активированные чеки
        cursor.execute(
            """
            SELECT c.cheque_id, c.total_amount, TO_CHAR(TO_TIMESTAMP(cc.claimed_at), 'DD.MM.YYYY HH24:MI') as date_str
            FROM cheque_claims cc
            JOIN cheques c ON LOWER(cc.cheque_id) = LOWER(c.cheque_id)
            WHERE cc.user_id = %s AND cc.claimed_at IS NOT NULL
              AND TO_TIMESTAMP(cc.claimed_at) >= NOW() - (INTERVAL '1 hour' * %s)
            ORDER BY cc.claimed_at DESC
            LIMIT 20
            """,
            (int(user_id), int(hours))
        )
        ch_rows = cursor.fetchall()
        for r in ch_rows:
            cid, amt, dt = r
            transfers.append({
                "action": f"Активация чека #{cid}",
                "amount": float(amt or 0),
                "date": dt
            })

        transfers.sort(key=lambda x: x["date"], reverse=True)
        return transfers[:30]
    except Exception as e:
        logger.error(f"Ошибка get_user_transfers_history: {e}")
        return transfers
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def get_user_game_stats(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT game_name, COUNT(*) FROM game_history WHERE user_id = %s GROUP BY game_name",
            (int(user_id),)
        )
        rows = cursor.fetchall()
        return {str(row[0]): int(row[1]) for row in rows}
    except Exception as e:
        logger.error(f"Ошибка get_user_game_stats: {e}")
        return {}
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def get_user_rank(user_id: int) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) + 1 FROM users WHERE balance > COALESCE((SELECT balance FROM users WHERE user_id = %s), 0)",
            (user_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 1
    except Exception as e:
        logger.error(f"Ошибка get_user_rank: {e}")
        return 1
    finally:
        cursor.close()
        conn.close()

def get_top_players(limit: int = 10) -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id, balance, nmp_balance, first_name, username FROM users ORDER BY balance DESC LIMIT %s",
            (int(limit),)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка get_top_players: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# --- ФУНКЦИИ ТУРНИРОВ ИДЕЙ ---

def get_all_user_ids() -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        try:
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0 OR is_blocked IS FALSE")
        except Exception:
            conn.rollback()
            cursor.execute("SELECT user_id FROM users")
            
        rows = cursor.fetchall()
        return [int(row[0]) for row in rows if row[0]]
    except Exception as e:
        logger.error(f"Ошибка get_all_user_ids: {e}")
        return []
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def add_tournament_idea(user_id: int, username: str, first_name: str, idea_text: str) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO tournament_ideas (user_id, username, first_name, idea_text) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, username, first_name, idea_text)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка add_tournament_idea: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def has_user_submitted_idea(user_id: int) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM tournament_ideas WHERE user_id = %s", (user_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка has_user_submitted_idea: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_all_tournament_ideas() -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id, username, first_name, idea_text FROM tournament_ideas ORDER BY id ASC")
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка get_all_tournament_ideas: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_tournament_idea(idea_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id, username, first_name, idea_text FROM tournament_ideas WHERE id = %s", (idea_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "user_id": row[1], "username": row[2], "first_name": row[3], "idea": row[4]}
        return None
    except Exception as e:
        logger.error(f"Ошибка get_tournament_idea: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def delete_tournament_idea(idea_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM tournament_ideas WHERE id = %s", (idea_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка delete_tournament_idea: {e}")
    finally:
        cursor.close()
        conn.close()

def clear_tournament_ideas():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE tournament_ideas")
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка clear_tournament_ideas: {e}")
    finally:
        cursor.close()
        conn.close()


# --- ЧЕКИ ---

def normalize_cheque_id(cheque_id: str) -> str:
    if not cheque_id:
        return ""
    cid_str = str(cheque_id).strip().lower()
    if cid_str.startswith("c_"):
        return cid_str[2:]
    return cid_str

def add_cheque(cheque_id: str, creator_id: int, amount: float, activations: int, password: str = None, description: str = None, target_user_id: int = None):
    conn = get_conn()
    cursor = conn.cursor()
    cid = str(cheque_id).strip()
    try:
        cursor.execute("""
            INSERT INTO cheques (cheque_id, creator_id, total_amount, activations_total, activations_left, password, description, target_user_id, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (cid, creator_id, amount, activations, activations, password, description, target_user_id, int(time.time())))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def create_cheque_db(cheque_id: str, creator_id: int, total_amount: float, activations_total: int, password=None, description=None, target_user_id=None, notifications=True) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    cid = str(cheque_id).strip()
    try:
        cursor.execute(
            "INSERT INTO cheques (cheque_id, creator_id, total_amount, activations_total, activations_left, password, description, target_user_id, notifications, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (cid, int(creator_id), float(total_amount), int(activations_total), int(activations_total), password, description, target_user_id, notifications, int(time.time()))
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка create_cheque_db: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def get_cheque(cheque_id: str):
    conn = get_conn()
    cursor = conn.cursor()
    raw_cid = str(cheque_id).strip()
    norm_cid = normalize_cheque_id(raw_cid)
    try:
        cursor.execute(
            "SELECT cheque_id, creator_id, total_amount, activations_total, activations_left, password, description, target_user_id, notifications "
            "FROM cheques WHERE LOWER(cheque_id) = %s OR LOWER(cheque_id) = %s OR cheque_id = %s", 
            (norm_cid, f"c_{norm_cid}", raw_cid)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "cheque_id": row[0],
                "creator_id": int(row[1]) if row[1] else None,
                "total_amount": float(row[2]),
                "activations_total": int(row[3]),
                "activations_left": int(row[4]),
                "password": row[5],
                "description": row[6],
                "target_user_id": int(row[7]) if row[7] else None,
                "notifications": bool(row[8]) if row[8] is not None else True
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка get_cheque: {e}")
        return None
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def register_cheque_claim(cheque_id: str, user_id: int) -> bool:
    uid = int(user_id)
    raw_cid = str(cheque_id).strip()
    norm_cid = normalize_cheque_id(raw_cid)
    conn = get_conn()
    cursor = conn.cursor()
    now_ts = int(time.time())
    try:
        cursor.execute(
            "SELECT cheque_id, activations_left FROM cheques WHERE LOWER(cheque_id) = %s OR LOWER(cheque_id) = %s OR cheque_id = %s",
            (norm_cid, f"c_{norm_cid}", raw_cid)
        )
        row = cursor.fetchone()
        if not row:
            return False

        exact_cid, activations_left = row[0], row[1]
        if activations_left <= 0:
            return False

        cursor.execute(
            "SELECT 1 FROM cheque_claims WHERE user_id = %s AND (LOWER(cheque_id) = %s OR LOWER(cheque_id) = %s OR cheque_id = %s)", 
            (uid, norm_cid, f"c_{norm_cid}", exact_cid)
        )
        if cursor.fetchone():
            return False

        cursor.execute(
            "UPDATE cheques SET activations_left = activations_left - 1 WHERE cheque_id = %s AND activations_left > 0", 
            (exact_cid,)
        )
        if cursor.rowcount == 0:
            return False

        try:
            cursor.execute(
                "INSERT INTO cheque_claims (cheque_id, user_id, claimed_at) VALUES (%s, %s, %s)", 
                (exact_cid, uid, now_ts)
            )
        except Exception:
            cursor.execute(
                "INSERT INTO cheque_claims (cheque_id, user_id) VALUES (%s, %s)", 
                (exact_cid, uid)
            )

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка register_cheque_claim: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def get_user_created_cheques(user_id: int) -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT cheque_id, total_amount, activations_total, activations_left, password, description, target_user_id
            FROM cheques 
            WHERE creator_id = %s AND activations_left > 0
            ORDER BY cheque_id DESC
        """, (int(user_id),))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "cheque_id": row[0],
                "total_amount": float(row[1]),
                "activations_total": int(row[2]),
                "activations_left": int(row[3]),
                "has_password": bool(row[4]),
                "description": row[5] or "Без описания",
                "target_user_id": row[6]
            })
        return result
    except Exception as e:
        logger.error(f"Ошибка get_user_created_cheques: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def delete_cheque(cheque_id: str):
    conn = get_conn()
    cursor = conn.cursor()
    raw_cid = str(cheque_id).strip()
    norm_cid = normalize_cheque_id(raw_cid)
    try:
        cursor.execute("DELETE FROM cheques WHERE LOWER(cheque_id) = %s OR LOWER(cheque_id) = %s OR cheque_id = %s", (norm_cid, f"c_{norm_cid}", raw_cid))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка delete_cheque: {e}")
        try: conn.rollback()
        except: pass
    finally:
        cursor.close()
        try: conn.close()
        except: pass

def update_cheque_field(cheque_id: str, field: str, value):
    conn = get_conn()
    cursor = conn.cursor()
    raw_cid = str(cheque_id).strip()
    norm_cid = normalize_cheque_id(raw_cid)
    try:
        cursor.execute(f"UPDATE cheques SET {field} = %s WHERE LOWER(cheque_id) = %s OR cheque_id = %s", (value, norm_cid, raw_cid))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# --- БАНК ---

def update_savings(user_id: int, balance: float, last_claim: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users 
            SET savings_balance = %s, savings_last_claim = %s 
            WHERE user_id = %s
        """, (balance, last_claim, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def create_deposit(user_id: int, amount: float, days: int, payout: float):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        end_time = int(time.time()) + (days * 86400)
        cursor.execute("""
            INSERT INTO deposits (user_id, amount, end_time, payout, days) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, amount, end_time, payout, days))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_user_deposits(user_id: int) -> list:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, amount, end_time, payout, days 
            FROM deposits WHERE user_id = %s
        """, (user_id,))
        rows = cursor.fetchall()
        return [{"id": r[0], "amount": r[1], "end_time": r[2], "payout": r[3], "days": r[4]} for r in rows]
    finally:
        cursor.close()
        conn.close()

def close_deposit(deposit_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM deposits WHERE id = %s", (deposit_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# --- ОБМЕННИК ---

def update_exchange_balance(user_id: int, amount: float):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET exchange_balance = exchange_balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_exchange_nmp_balance(user_id: int, amount: float):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET exchange_nmp_balance = exchange_nmp_balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_exchange_history(page: int = 0, per_page: int = 5):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT username, nmp_amount, ncoin_amount, tx_type, timestamp 
            FROM exchange_history ORDER BY timestamp DESC LIMIT %s OFFSET %s
        """, (per_page, page * per_page))
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM exchange_history")
        total = cursor.fetchone()[0] or 0
        return rows, total
    finally:
        cursor.close()
        conn.close()

def add_exchange_history(user_id: int, username: str, nmp_amount: float, ncoin_amount: float, tx_type: str) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO exchange_history (user_id, username, nmp_amount, ncoin_amount, tx_type, timestamp) 
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, username, nmp_amount, ncoin_amount, tx_type, int(time.time())))
        deal_id = cursor.fetchone()[0]
        conn.commit()
        return deal_id
    finally:
        cursor.close()
        conn.close()


# --- ПРОМОКОДЫ ---

def create_promocode(code: str, amount: float, max_activations: int) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        code_lower = code.lower().strip()
        cursor.execute("SELECT 1 FROM promocodes WHERE code = %s", (code_lower,))
        if cursor.fetchone():
            return False
        cursor.execute("""
            INSERT INTO promocodes (code, amount, max_activations, activations_left, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (code_lower, amount, max_activations, max_activations, int(time.time())))
        conn.commit()
        return True
    finally:
        cursor.close()
        conn.close()

def claim_promocode_db(code: str, user_id: int) -> float:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        code_lower = code.lower().strip()
        cursor.execute("SELECT amount, activations_left FROM promocodes WHERE code = %s", (code_lower,))
        promo = cursor.fetchone()
        if not promo:
            return 0.0
        amount, left = promo
        if left <= 0:
            return 0.0
        cursor.execute("SELECT 1 FROM promocode_claims WHERE code = %s AND user_id = %s", (code_lower, user_id))
        if cursor.fetchone():
            return -1.0
        cursor.execute("UPDATE promocodes SET activations_left = activations_left - 1 WHERE code = %s AND activations_left > 0", (code_lower,))
        if cursor.rowcount == 0:
            return 0.0
        cursor.execute("INSERT INTO promocode_claims (code, user_id) VALUES (%s, %s)", (code_lower, user_id))
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        return amount
    finally:
        cursor.close()
        conn.close()


# --- АДМИНИСТРИРОВАНИЕ ---

def set_block_status(user_id: int, block: bool):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        status = 1 if block else 0
        cursor.execute("UPDATE users SET is_blocked = %s WHERE user_id = %s", (status, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def is_user_blocked(user_id: int) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_blocked FROM users WHERE user_id = %s", (user_id,))
        res = cursor.fetchone()
        return bool(res[0]) if res else False
    finally:
        cursor.close()
        conn.close()

def get_admin_stats(period_hours: int = 24) -> dict:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM activity_logs 
            WHERE action = 'register' AND timestamp >= NOW() - (INTERVAL '1 hour' * %s)
        """, (period_hours,))
        new = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT COUNT(*) FROM activity_logs 
            WHERE action = 'game_play' AND timestamp >= NOW() - (INTERVAL '1 hour' * %s)
        """, (period_hours,))
        games = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT CAST(COALESCE(SUM(amount), 0) AS DOUBLE PRECISION) FROM activity_logs 
            WHERE action = 'game_play' AND timestamp >= NOW() - (INTERVAL '1 hour' * %s)
        """, (period_hours,))
        turnover = cursor.fetchone()[0] or 0.0
        
        return {"total_users": total, "new_users": new, "games_played": games, "turnover": turnover}
    finally:
        cursor.close()
        conn.close()

def get_random_winner():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, balance FROM users WHERE is_blocked = 0 ORDER BY RANDOM() LIMIT 1")
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_user_game_percentages(user_id: int, hours: int = 48) -> dict:
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_games,
                COALESCE(SUM(CASE WHEN is_win = TRUE THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN is_win = FALSE THEN 1 ELSE 0 END), 0) AS losses
            FROM game_history
            WHERE user_id = %s
              AND created_at >= NOW() - (INTERVAL '1 hour' * %s)
            """,
            (int(user_id), int(hours))
        )

        total, wins, losses = cursor.fetchone()
        total = int(total or 0)
        wins = int(wins or 0)
        losses = int(losses or 0)

        if total == 0:
            return {
                "total": 0, "wins": 0, "losses": 0, "win_percent": 0.0, "loss_percent": 0.0
            }

        return {
            "total": total, "wins": wins, "losses": losses,
            "win_percent": round(wins / total * 100, 1),
            "loss_percent": round(losses / total * 100, 1)
        }

    except Exception as e:
        logger.error(f"Ошибка get_user_game_percentages: {e}")
        return {
            "total": 0, "wins": 0, "losses": 0, "win_percent": 0.0, "loss_percent": 0.0
        }
    finally:
        cursor.close()
        conn.close()

def build_progress_bar(percent: float, filled: str, empty: str = "⬜️", length: int = 4) -> str:
    percent = max(0.0, min(100.0, float(percent)))
    filled_count = round(percent / 100 * length)
    filled_count = max(0, min(length, filled_count))
    return filled * filled_count + empty * (length - filled_count)

def cleanup_old_game_history() -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM game_history WHERE created_at < NOW() - INTERVAL '72 hours'")
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка очистки истории игр: {e}")
        try: conn.rollback()
        except Exception: pass
    finally:
        cursor.close()
        conn.close()

# ==========================================
# 💎 ИСПРАВЛЕННЫЙ МОДУЛЬ ДОНАТОВ В DB.PY
# ==========================================

def ensure_donations_table():
    """Снимает старые ограничения и подготавливает структуру таблицы donations"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donations (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                stars_eq INT DEFAULT 0,
                nmp_amount INT DEFAULT 0,
                stars_amount INT DEFAULT 0,
                crypto_usd DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Добавляем колонки, если их нет
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS stars_eq INT DEFAULT 0;
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS stars_equivalent INT DEFAULT 0;
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS nmp_amount INT DEFAULT 0;
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS stars_amount INT DEFAULT 0;
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS crypto_usd DOUBLE PRECISION DEFAULT 0.0;
            ALTER TABLE donations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

            -- СНИМАЕМ NOT NULL СО СТАРОЙ КОЛОНКИ, ЧТОБЫ БАЗА НЕ ПАДАЛА
            ALTER TABLE donations ALTER COLUMN stars_equivalent DROP NOT NULL;

            -- Настройки доната
            DROP TABLE IF EXISTS donation_settings CASCADE;
            CREATE TABLE donation_settings (
                id INT PRIMARY KEY DEFAULT 1,
                discount INT DEFAULT 0,
                bonus INT DEFAULT 0,
                custom_text TEXT DEFAULT ''
            );

            INSERT INTO donation_settings (id, discount, bonus, custom_text)
            VALUES (1, 0, 0, '')
            ON CONFLICT (id) DO NOTHING;
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка проверки таблиц доната: {e}")
    finally:
        cursor.close()
        conn.close()


def add_donation_record(user_id: int, stars_eq: int = 0, nmp: int = 0, stars_amt: int = 0, crypto_usd: float = 0.0):
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO donations (user_id, stars_eq, stars_equivalent, nmp_amount, stars_amount, crypto_usd, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, stars_eq, stars_eq, nmp, stars_amt, crypto_usd))
        conn.commit()
        logger.info(f"✅ Успешно записан донат: user_id={user_id}, stars={stars_eq}, nmp={nmp}")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Ошибка add_donation_record: {e}")
    finally:
        cursor.close()
        conn.close()


def get_donations_history(user_id: int, limit: int = 5) -> list:
    """Возвращает историю донатов конкретного пользователя (исправлено для экрана истории)"""
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(stars_amount, stars_eq, stars_equivalent, 0) as stars,
                   COALESCE(nmp_amount, 0) as nmp,
                   created_at
            FROM donations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (int(user_id), int(limit)))
        return cursor.fetchall() or []
    except Exception as e:
        logger.error(f"Ошибка get_donations_history: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_donation_settings() -> dict:
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT discount, bonus, custom_text FROM donation_settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return {"discount": row[0], "bonus": row[1], "custom_text": row[2]}
        return {"discount": 0, "bonus": 0, "custom_text": ""}
    except Exception as e:
        logger.error(f"Ошибка get_donation_settings: {e}")
        return {"discount": 0, "bonus": 0, "custom_text": ""}
    finally:
        cursor.close()
        conn.close()


def update_donation_settings(discount: int = 0, bonus: int = 0, text: str = ""):
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE donation_settings 
            SET discount = %s, bonus = %s, custom_text = %s 
            WHERE id = 1
        """, (discount, bonus, text))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка update_donation_settings: {e}")
    finally:
        cursor.close()
        conn.close()


def get_top_donators(period: str = "month", limit: int = 20):
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    
    interval_sql = ""
    if period == "week":
        interval_sql = "WHERE created_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
        interval_sql = "WHERE created_at >= NOW() - INTERVAL '30 days'"

    try:
        cursor.execute(f"""
            SELECT user_id, SUM(COALESCE(stars_eq, stars_equivalent, stars_amount, 0)) as total_stars
            FROM donations
            {interval_sql}
            GROUP BY user_id
            ORDER BY total_stars DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall() or []
        
        result = []
        for r in rows:
            u_id = int(r[0])
            stars_val = int(r[1] or 0)
            
            u_data = get_user(u_id) or {}
            f_name = u_data.get("first_name", "")
            u_name = u_data.get("username", "")
            
            result.append((u_id, stars_val, f_name, u_name))
            
        return result
    except Exception as e:
        logger.error(f"Ошибка get_top_donators: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_user_donation_stats(user_id: int, period: str = "month"):
    ensure_donations_table()
    conn = get_conn()
    cursor = conn.cursor()
    
    interval_sql = ""
    if period == "week":
        interval_sql = "AND created_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
        interval_sql = "AND created_at >= NOW() - INTERVAL '30 days'"

    try:
        cursor.execute(f"""
            SELECT COALESCE(SUM(COALESCE(stars_eq, stars_equivalent, stars_amount, 0)), 0) 
            FROM donations 
            WHERE user_id = %s {interval_sql}
        """, (user_id,))
        row = cursor.fetchone()
        user_stars = int(row[0] or 0) if row else 0

        if user_stars <= 0:
            return None, 0

        cursor.execute(f"""
            SELECT COUNT(*) + 1 
            FROM (
                SELECT user_id, SUM(COALESCE(stars_eq, stars_equivalent, stars_amount, 0)) as total 
                FROM donations 
                WHERE 1=1 {interval_sql}
                GROUP BY user_id 
                HAVING SUM(COALESCE(stars_eq, stars_equivalent, stars_amount, 0)) > %s
            ) sub
        """, (user_stars,))
        rank_row = cursor.fetchone()
        rank = rank_row[0] if rank_row else 1

        return rank, user_stars
    except Exception as e:
        logger.error(f"Ошибка get_user_donation_stats: {e}")
        return None, 0
    finally:
        cursor.close()
        conn.close()

# ==============================================================================
# 🛒 ИСПРАВЛЕННЫЙ БЛОК: NMP МАРКЕТ (/trade) В POSTGRESQL
# ==============================================================================

def init_trade_tables():
    """Создает таблицы для NMP Маркета в PostgreSQL при старте"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traders (
                user_id BIGINT PRIMARY KEY,
                is_trader INT DEFAULT 0,
                free_lot_used INT DEFAULT 0,
                total_deals INT DEFAULT 0,
                rating_sum INT DEFAULT 0,
                rating_count INT DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_listings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                price_per_nmp VARCHAR(100),
                amount_nmp DOUBLE PRECISION,
                contact_info TEXT,
                payment_methods TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_complaints (
                id SERIAL PRIMARY KEY,
                reporter_id BIGINT,
                trader_id BIGINT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации таблиц трейда: {e}")
    finally:
        cursor.close()
        conn.close()

try:
    init_trade_tables()
except Exception as e:
    logger.error(f"[NMP Market] Ошибка инициализации: {e}")

def get_trader(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, is_trader, free_lot_used, total_deals, rating_sum, rating_count FROM traders WHERE user_id = %s", (user_id,))
        r = cursor.fetchone()
        if not r: return None
        return {"user_id": r[0], "is_trader": r[1], "free_lot_used": r[2], "total_deals": r[3], "rating_sum": r[4], "rating_count": r[5]}
    finally:
        cursor.close()
        conn.close()

def set_trader_status(user_id: int, is_trader: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO traders (user_id, is_trader) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET is_trader = EXCLUDED.is_trader
        """, (user_id, is_trader))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_trader_listing(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id, price_per_nmp, amount_nmp, contact_info, payment_methods FROM trade_listings WHERE user_id = %s", (user_id,))
        r = cursor.fetchone()
        if not r: return None
        return {"id": r[0], "user_id": r[1], "price_per_nmp": r[2], "amount_nmp": r[3], "contact_info": r[4], "payment_methods": r[5]}
    finally:
        cursor.close()
        conn.close()

def save_trader_listing(user_id: int, price: str, amount: float, contact: str, payment: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM trade_listings WHERE user_id = %s", (user_id,))
        cursor.execute("""
            INSERT INTO trade_listings (user_id, price_per_nmp, amount_nmp, contact_info, payment_methods)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, price, amount, contact, payment))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def delete_trader_listing(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM trade_listings WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def mark_free_lot_used(user_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE traders SET free_lot_used = 1 WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_all_active_sellers():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        query = """
            SELECT l.id, l.user_id, l.price_per_nmp, l.amount_nmp, l.contact_info, l.payment_methods,
                   t.rating_sum, t.rating_count, t.total_deals,
                   u.first_name, u.username,
                   CASE WHEN t.rating_count > 0 THEN (CAST(t.rating_sum AS FLOAT) / t.rating_count) ELSE 0 END as avg_rating
            FROM trade_listings l
            JOIN traders t ON l.user_id = t.user_id
            LEFT JOIN users u ON l.user_id = u.user_id
            WHERE t.is_trader = 1 AND l.amount_nmp > 0
            ORDER BY avg_rating DESC, t.total_deals DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0], "user_id": r[1], "price_per_nmp": r[2], "amount_nmp": r[3],
                "contact_info": r[4], "payment_methods": r[5], "rating_sum": r[6],
                "rating_count": r[7], "total_deals": r[8], "first_name": r[9],
                "username": r[10], "avg_rating": r[11]
            })
        return result
    finally:
        cursor.close()
        conn.close()

def add_trade_rating(trader_id: int, rating: int):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE traders 
            SET rating_sum = rating_sum + %s, rating_count = rating_count + 1, total_deals = total_deals + 1
            WHERE user_id = %s
        """, (rating, trader_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def add_complaint(reporter_id: int, trader_id: int, reason: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO trade_complaints (reporter_id, trader_id, reason) VALUES (%s, %s, %s)", (reporter_id, trader_id, reason))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def add_one_time_drain(game_name: str, min_bet: float) -> bool:
    """Создает одноразовое правило принудительного слива первого попавшегося игрока"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO one_time_drains (game_name, min_bet, is_active)
            VALUES (%s, %s, TRUE)
        """, (game_name.lower().strip(), float(min_bet)))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка add_one_time_drain: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        try: conn.close()
        except: pass


def check_and_consume_drain(game_name: str, bet: float) -> bool:
    """
    Проверяет, есть ли активный одноразовый срез.
    Если есть — СРАЗУ СЖИГАЕТ ЕГО (деактивирует) и возвращает True!
    Дальнейшие игроки играют уже нормально.
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        # Находим активный срез
        cursor.execute("""
            SELECT id FROM one_time_drains
            WHERE is_active = TRUE
              AND (game_name = 'all' OR LOWER(game_name) = LOWER(%s))
              AND %s >= min_bet
            ORDER BY id ASC
            LIMIT 1
        """, (game_name, float(bet)))
        
        row = cursor.fetchone()
        if not row:
            return False

        drain_id = row[0]
        # Сразу сжигаем (деактивируем) этот срез, чтобы он сработал ровно 1 раз!
        cursor.execute("UPDATE one_time_drains SET is_active = FALSE WHERE id = %s", (drain_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка check_and_consume_drain: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        try: conn.close()
        except: pass


def save_basketball_round(
    round_id: str,
    user_id: int,
    bet: float,
    choice: str,
    dice_value: int,
    server_seed: str,
    server_hash: str
):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO basketball_rounds
            (round_id, user_id, bet, choice, dice_value, server_seed, server_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            round_id, user_id, bet, choice, dice_value,
            server_seed, server_hash
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_basketball_round(round_id: str):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT round_id, user_id, bet, choice, dice_value,
                   server_seed, server_hash, created_at
            FROM basketball_rounds
            WHERE round_id = %s
        """, (round_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "round_id": row[0],
            "user_id": row[1],
            "bet": float(row[2]),
            "choice": row[3],
            "dice_value": int(row[4]),
            "server_seed": row[5],
            "server_hash": row[6],
            "created_at": row[7],
        }
    finally:
        cursor.close()
        conn.close()
