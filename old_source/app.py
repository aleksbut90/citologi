import requests
import json
import os
import re
import psycopg2
from psycopg2 import sql, pool
from typing import List, Dict, Optional, Union
from datetime import datetime, date, timedelta
from docx import Document
import subprocess
import logging
from dotenv import load_dotenv
from pathlib import Path
import psycopg2.extras
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import secrets
import hashlib
import time
import base64
import tempfile
import shutil
from collections import defaultdict
from threading import Lock
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


from logging.handlers import RotatingFileHandler

# Настройка структурированного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__, static_folder='web', static_url_path='')

# Логирование запросов для мониторинга (после создания app)
@app.before_request
def log_request_info():
    """Логирует информацию о входящих запросах и отслеживает метрики"""
    if request.path.startswith('/api/'):
        client_id = request.remote_addr or 'unknown'
        if request.headers.get('X-Forwarded-For'):
            client_id = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        logger.info(f"Request: {request.method} {request.path} from {client_id}")
        
        # Отслеживание метрик
        request.start_time = time.time()
        with _metrics_lock:
            _request_metrics['total_requests'] += 1
            current_time = time.time()
            _request_metrics['requests_per_minute'].append(current_time)
            # Удаляем записи старше минуты
            _request_metrics['requests_per_minute'] = [
                t for t in _request_metrics['requests_per_minute'] 
                if current_time - t < 60
            ]

@app.after_request
def log_response_info(response):
    """Логирует информацию об ответах и отслеживает время выполнения"""
    if request.path.startswith('/api/'):
        logger.info(f"Response: {response.status_code} for {request.method} {request.path}")
        
        # Отслеживание времени выполнения
        if hasattr(request, 'start_time'):
            response_time = time.time() - request.start_time
            with _metrics_lock:
                _request_metrics['response_times'].append(response_time)
                # Храним только последние 1000 записей
                if len(_request_metrics['response_times']) > 1000:
                    _request_metrics['response_times'] = _request_metrics['response_times'][-1000:]
                
                # Отслеживание ошибок
                if response.status_code >= 400:
                    _request_metrics['errors'] += 1
    
    return response

# CORS настройки - ограничиваем конкретными доменами для безопасности
# Можно переопределить через переменную окружения ALLOWED_ORIGINS
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
if '*' in allowed_origins:
    # Для разработки разрешаем все источники
    CORS(app, resources={r"/api/*": {"origins": "*"}})
else:
    # Для продакшена ограничиваем конкретными доменами
    CORS(app, resources={r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }})

MKB_CACHE: List[Dict] = []
BETHESDA_DATA: List[Dict] = []

# Кэши для справочников (для улучшения производительности)
PHYSICIAN_CACHE: Optional[List[Dict]] = None
SERVICES_CACHE: Optional[List[Dict]] = None
SAMPLE_TYPES_CACHE: Optional[List[Dict]] = None
SERVICE_TYPES_CACHE: Optional[List[Dict]] = None
STUDY_CHARACTERS_CACHE: Optional[List[Dict]] = None
DEPARTMENTS_CACHE: Optional[List[Dict]] = None
SUBDEPARTMENTS_CACHE: Dict[int, List[Dict]] = {}  # Кэш по department_id
LOCALIZATION_CACHE: Optional[List[Dict]] = None
CODE_CYTOLOGY_CACHE: Optional[List[Dict]] = None
RAION_CACHE: Optional[List[Dict]] = None

# Время последнего обновления кэшей (для инвалидации при необходимости)
_cache_timestamps: Dict[str, datetime] = {}
CACHE_TTL_SECONDS = 3600  # 1 час

# Rate limiting (простая реализация без дополнительных зависимостей)
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock = Lock()
RATE_LIMIT_WINDOW = 60  # Окно в секундах
RATE_LIMIT_MAX_REQUESTS = 100  # Максимум запросов в окне

# Метрики для мониторинга
_request_metrics = {
    'total_requests': 0,
    'requests_per_minute': [],
    'response_times': [],
    'errors': 0,
    'start_time': datetime.now()
}
_metrics_lock = Lock()

PBKDF2_ITERATIONS = 200_000

def is_cache_valid(cache_name: str) -> bool:
    """Проверяет, действителен ли кэш (не истек ли TTL)"""
    if cache_name not in _cache_timestamps:
        return False
    elapsed = (datetime.now() - _cache_timestamps[cache_name]).total_seconds()
    return elapsed < CACHE_TTL_SECONDS

def invalidate_cache(cache_name: str = None):
    """Инвалидирует кэш (все кэши, если cache_name не указан)"""
    global PHYSICIAN_CACHE, SERVICES_CACHE, SAMPLE_TYPES_CACHE, SERVICE_TYPES_CACHE
    global STUDY_CHARACTERS_CACHE, DEPARTMENTS_CACHE, SUBDEPARTMENTS_CACHE
    global LOCALIZATION_CACHE, CODE_CYTOLOGY_CACHE, RAION_CACHE
    
    if cache_name is None:
        # Инвалидируем все кэши
        PHYSICIAN_CACHE = None
        SERVICES_CACHE = None
        SAMPLE_TYPES_CACHE = None
        SERVICE_TYPES_CACHE = None
        STUDY_CHARACTERS_CACHE = None
        DEPARTMENTS_CACHE = None
        SUBDEPARTMENTS_CACHE.clear()
        LOCALIZATION_CACHE = None
        CODE_CYTOLOGY_CACHE = None
        RAION_CACHE = None
        _cache_timestamps.clear()
        logger.info("Все кэши справочников инвалидированы")
    else:
        # Инвалидируем конкретный кэш
        if cache_name == 'physician':
            PHYSICIAN_CACHE = None
        elif cache_name == 'services':
            SERVICES_CACHE = None
        elif cache_name == 'sample_types':
            SAMPLE_TYPES_CACHE = None
        elif cache_name == 'service_types':
            SERVICE_TYPES_CACHE = None
        elif cache_name == 'study_characters':
            STUDY_CHARACTERS_CACHE = None
        elif cache_name == 'departments':
            DEPARTMENTS_CACHE = None
        elif cache_name == 'subdepartments':
            SUBDEPARTMENTS_CACHE.clear()
        elif cache_name == 'localization':
            LOCALIZATION_CACHE = None
        elif cache_name == 'code_cytology':
            CODE_CYTOLOGY_CACHE = None
        elif cache_name == 'raion':
            RAION_CACHE = None
        
        if cache_name in _cache_timestamps:
            del _cache_timestamps[cache_name]
        logger.info(f"Кэш '{cache_name}' инвалидирован")


def log_user_login(username: str) -> None:
    """Фиксирует успешный вход пользователя."""
    logger.info(f"{username} - это вход")


def log_function_error(function_name: str, error: Union[str, Exception]) -> None:
    """Фиксирует ошибку в функции в требуемом формате."""
    logger.error(f"{function_name} - это ошибка: {error}")


def log_startup_problem(component: str, error: Union[str, Exception]) -> None:
    """Фиксирует проблему при запуске компонента."""
    logger.error(f"{component} - проблема с запуском: {error}")


def log_startup_success(component: str) -> None:
    """Фиксирует успешную проверку компонента."""
    logger.info(f"{component} - проверка завершена успешно")


def check_database_connection() -> None:
    """Проверяет доступность базы данных."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


def check_ecp_credentials() -> None:
    """Проверяет наличие учетных данных для работы с ЕЦП."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT login, password FROM ecp45mis LIMIT 1")
        row = cursor.fetchone()
        if not row or not row[0] or not row[1]:
            raise ValueError("Не найдены учетные данные ЕЦП")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


def check_static_assets() -> None:
    """Проверяет наличие ключевых статических страниц."""
    required_files = [
        Path("web/authorization.html"),
        Path("web/admin.html"),
        Path("web/home.html")
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Отсутствуют страницы: {', '.join(missing)}")


def run_startup_checks() -> None:
    """Выполняет последовательные проверки при запуске приложения."""
    checks = [
        ("Подключение к базе данных", check_database_connection),
        ("Учетные данные ЕЦП", check_ecp_credentials),
        ("Статические страницы", check_static_assets),
    ]

    for component, check in checks:
        try:
            check()
            log_startup_success(component)
        except Exception as exc:
            log_startup_problem(component, exc)

def generate_password_salt() -> str:
    return base64.b64encode(secrets.token_bytes(16)).decode('utf-8')

def hash_password_with_salt(password: str, salt_b64: str) -> str:
    salt = base64.b64decode(salt_b64.encode('utf-8'))
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return base64.b64encode(dk).decode('utf-8')

def verify_password(password: str, salt_b64: Optional[str], hash_b64: Optional[str]) -> bool:
    if not salt_b64 or not hash_b64:
        return False
    try:
        calc = hash_password_with_salt(password, salt_b64)
        return hashlib.sha256(calc.encode()).digest() == hashlib.sha256(hash_b64.encode()).digest()
    except Exception:
        return False

DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

# Настройки пула соединений (можно переопределить через переменные окружения)
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '5'))  # Минимум соединений
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '200'))  # Максимум соединений (увеличено для поддержки 1000 пользователей)

# Конфигурационные константы (можно переопределить через переменные окружения)
MEDICAL_ORGANIZATION_ID = os.getenv('MEDICAL_ORGANIZATION_ID', '1.2.643.5.1.13.13.12.2.45.4286')
REGION_ID = os.getenv('REGION_ID', '45')
REGION_NAME = os.getenv('REGION_NAME', 'Курган')

# ID подразделений (можно переопределить через переменные окружения)
SUBDEPARTMENT_IDS = {
    'endoscopic': os.getenv('SUBDEPARTMENT_ENDOSCOPIC', '1-13'),
    'radiology': os.getenv('SUBDEPARTMENT_RADIOLOGY', '1-12'),
    'day_chemotherapy': os.getenv('SUBDEPARTMENT_DAY_CHEMOTHERAPY', '1-11'),
    'surgical': os.getenv('SUBDEPARTMENT_SURGICAL', '1-10'),
    'abdominal': os.getenv('SUBDEPARTMENT_ABDOMINAL', '1-9'),
    'chemotherapy': os.getenv('SUBDEPARTMENT_CHEMOTHERAPY', '1-8'),
    'thoracic': os.getenv('SUBDEPARTMENT_THORACIC', '1-7'),
    'gynecology': os.getenv('SUBDEPARTMENT_GYNECOLOGY', '1-6'),
    'breast_skin': os.getenv('SUBDEPARTMENT_BREAST_SKIN', '1-5'),
    'tumors': os.getenv('SUBDEPARTMENT_TUMORS', '1-4')
}

connection_pool = None
_pool_stats = {
    'total_connections': 0,
    'active_connections': 0,
    'max_connections': DB_POOL_MAX
}

def init_db_pool():
   
    global connection_pool, _pool_stats
    if connection_pool is not None:
        return connection_pool

    missing = [key for key, value in DATABASE_CONFIG.items() if not value]
    if missing:
        log_startup_problem("Параметры подключения к базе данных", f"Не заданы переменные: {', '.join(missing)}")
        return None

    try:
        connection_pool = pool.SimpleConnectionPool(DB_POOL_MIN, DB_POOL_MAX, **DATABASE_CONFIG)
        _pool_stats['max_connections'] = DB_POOL_MAX
        logger.info(f"Пул соединений с базой данных инициализирован: минимум={DB_POOL_MIN}, максимум={DB_POOL_MAX}")
    except Exception as e:
        log_function_error("init_db_pool", e)
        connection_pool = None
    return connection_pool

def get_db_connection():
   
    global _pool_stats
    try:
        if connection_pool is None:
            init_db_pool()
        if connection_pool is None:
            raise RuntimeError("Пул соединений с базой данных не инициализирован")
        try:
            # SimpleConnectionPool.getconn() не поддерживает timeout
            # Если пул исчерпан, метод выбросит PoolError
            conn = connection_pool.getconn()
            _pool_stats['active_connections'] = _pool_stats.get('active_connections', 0) + 1
            _pool_stats['total_connections'] = _pool_stats.get('total_connections', 0) + 1
        except pool.PoolError as e:
            log_function_error("get_db_connection", f"Пул соединений исчерпан: {e}")
            logger.warning(f"Статистика пула: активных={_pool_stats.get('active_connections', 0)}, максимум={_pool_stats.get('max_connections', 0)}")
            raise RuntimeError("Сервис временно перегружен. Попробуйте позже.") from e
        logger.debug("Подключение к базе данных получено из пула")
        return conn
    except Exception as e:
        log_function_error("get_db_connection", e)
        raise

def return_db_connection(conn):
    """Возвращает соединение в пул с проверкой его валидности"""
    global _pool_stats
    if not conn:
        return
    
    try:
        # Проверяем, что соединение все еще открыто и валидно
        # Используем try-except, так как доступ к conn.closed может вызвать исключение
        try:
            is_closed = conn.closed != 0
        except (AttributeError, Exception):
            # Если не можем проверить статус, считаем соединение невалидным
            is_closed = True
        
        if not is_closed:  # Соединение открыто
            # Проверяем, что пул существует
            if connection_pool is not None:
                try:
                    connection_pool.putconn(conn)
                    _pool_stats['active_connections'] = max(0, _pool_stats.get('active_connections', 0) - 1)
                    logger.debug("Соединение возвращено в пул")
                except pool.PoolError as e:
                    # Ошибка пула (например, "trying to put unkeyed connection")
                    log_function_error("return_db_connection", f"Ошибка пула при возврате соединения: {e}")
                    # Пытаемся закрыть соединение
                    try:
                        conn.close()
                    except:
                        pass
                    # Обновляем счетчик
                    _pool_stats['active_connections'] = max(0, _pool_stats.get('active_connections', 0) - 1)
            else:
                logger.warning("Попытка вернуть соединение, но пул не инициализирован")
                try:
                    conn.close()
                except:
                    pass
                _pool_stats['active_connections'] = max(0, _pool_stats.get('active_connections', 0) - 1)
        else:
            logger.warning("Попытка вернуть уже закрытое соединение")
            # Соединение уже закрыто, просто обновляем счетчик
            _pool_stats['active_connections'] = max(0, _pool_stats.get('active_connections', 0) - 1)
    except Exception as e:
        log_function_error("return_db_connection", f"Ошибка при возврате соединения: {e}")
        # Пытаемся закрыть соединение, если оно еще открыто
        try:
            if hasattr(conn, 'closed') and conn.closed == 0:
                conn.close()
        except:
            pass
        # Обновляем счетчик
        _pool_stats['active_connections'] = max(0, _pool_stats.get('active_connections', 0) - 1)

def handle_db_error(e, function_name="unknown"):
    """Обработка ошибок БД с автоматическим переподключением"""
    global connection_pool
    
    if isinstance(e, psycopg2.OperationalError):
        # Ошибка соединения - попробовать переподключиться
        log_function_error(function_name, f"Ошибка соединения с БД: {e}")
        try:
            connection_pool = None
            init_db_pool()
            logger.info("Попытка переподключения к БД выполнена")
        except Exception as reconnect_error:
            log_function_error(function_name, f"Ошибка при переподключении: {reconnect_error}")
        return jsonify({"status": "error", "message": "Ошибка соединения с базой данных. Попробуйте позже."}), 503
    elif isinstance(e, psycopg2.IntegrityError):
        # Нарушение целостности данных (дубликаты, внешние ключи и т.д.)
        log_function_error(function_name, f"Нарушение целостности данных: {e}")
        error_msg = str(e).lower()
        # Уникальность: unique, duplicate, рус. уникальн, дубликат, повторя
        if any(x in error_msg for x in ('unique', 'duplicate', 'уникальн', 'дубликат', 'повторя')):
            return jsonify({"status": "error", "message": "Запись с такими данными уже существует"}), 400
        # Внешний ключ: foreign key, рус. внешн, связан, ключ (в контексте FK)
        if any(x in error_msg for x in ('foreign key', 'внешн', 'связан', 'ключ')):
            return jsonify({"status": "error", "message": "Связанная запись не найдена"}), 400
        return jsonify({"status": "error", "message": "Нарушение целостности данных"}), 400
    elif isinstance(e, psycopg2.DataError):
        # Ошибка данных (неверный формат, переполнение и т.д.)
        log_function_error(function_name, f"Ошибка данных: {e}")
        return jsonify({"status": "error", "message": "Неверный формат данных"}), 400
    else:
        # Другие ошибки БД — проверяем русские сообщения (целостность/внешний ключ)
        error_msg = str(e).lower()
        if any(x in error_msg for x in ('foreign key', 'внешн', 'связан', 'уникальн', 'дубликат', 'целостност')):
            log_function_error(function_name, f"Нарушение целостности/ФК: {e}")
            return jsonify({"status": "error", "message": "Связанная запись не найдена или нарушение целостности данных"}), 400
        log_function_error(function_name, f"Ошибка БД: {e}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера"}), 500

def create_session_table():
    """Создает таблицу для хранения сессий пользователей"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                session_hash VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address VARCHAR(255),
                user_agent VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        conn.commit()
        logger.info("Таблица user_sessions создана или уже существует")
    except Exception as e:
        log_function_error("create_session_table", e)
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def generate_session_id():
    """Генерирует уникальный идентификатор сессии"""
    return secrets.token_urlsafe(32)

def create_user_session(user_id, session_hash, expires_in_hours=48):
    """Создает новую сессию пользователя с защитой от race condition"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Устанавливаем timeout для транзакции (5 секунд)
        cursor.execute("SET statement_timeout = 5000")
        
        # Используем блокировку строк для предотвращения race condition
        # Сначала блокируем все активные сессии пользователя
        cursor.execute("""
            SELECT id FROM user_sessions 
            WHERE user_id = %s AND is_active = TRUE
            FOR UPDATE
        """, (user_id,))
        
        # Инвалидируем старые сессии пользователя (теперь они заблокированы)
        cursor.execute("""
            UPDATE user_sessions 
            SET is_active = FALSE 
            WHERE user_id = %s AND is_active = TRUE
        """, (user_id,))
        
        # Создаем новую сессию
        expires_at = datetime.now() + timedelta(hours=expires_in_hours)
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        
        # Используем INSERT ... ON CONFLICT для защиты от дубликатов session_hash
        try:
            cursor.execute("""
                INSERT INTO user_sessions (user_id, session_hash, expires_at, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, session_hash, expires_at, ip_address, user_agent))
        except psycopg2.IntegrityError:
            # Если session_hash уже существует (крайне маловероятно), генерируем новый
            session_hash = generate_session_id()
            cursor.execute("""
                INSERT INTO user_sessions (user_id, session_hash, expires_at, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, session_hash, expires_at, ip_address, user_agent))
        
        conn.commit()
        logger.info(f"Создана новая сессия для пользователя {user_id}")
        return True
    except Exception as e:
        log_function_error("create_user_session", e)
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def validate_session(session_hash):
    """Проверяет валидность сессии"""
    if not session_hash:
        return None
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, expires_at 
            FROM user_sessions 
            WHERE session_hash = %s AND is_active = TRUE AND expires_at > CURRENT_TIMESTAMP
        """, (session_hash,))
        
        result = cursor.fetchone()
        if result:
            user_id, expires_at = result
            logger.info(f"Валидная сессия найдена для пользователя {user_id}")
            return user_id
        else:
            logger.info(f"Невалидная или истекшая сессия: {session_hash[:16]}...")
            return None
    except Exception as e:
        log_function_error("validate_session", e)
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def invalidate_session(session_hash):
    """Инвалидирует сессию пользователя"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE user_sessions 
            SET is_active = FALSE 
            WHERE session_hash = %s
        """, (session_hash,))
        
        conn.commit()
        logger.info(f"Сессия инвалидирована: {session_hash[:16]}...")
        return True
    except Exception as e:
        log_function_error("invalidate_session", e)
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def cleanup_expired_sessions():
    """Очищает истекшие сессии"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM user_sessions 
            WHERE expires_at < CURRENT_TIMESTAMP
        """)
        
        deleted_count = cursor.rowcount
        conn.commit()
        logger.info(f"Удалено {deleted_count} истекших сессий")
        return deleted_count
    except Exception as e:
        log_function_error("cleanup_expired_sessions", e)
        if conn:
            conn.rollback()
        return 0
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def require_auth(f):
    """Декоратор для проверки авторизации"""
    def decorated_function(*args, **kwargs):
        session_hash = request.cookies.get('session_hash')
        if not session_hash:
            return jsonify({"status": "error", "message": "Требуется авторизация"}), 401
        
        user_id = validate_session(session_hash)
        if not user_id:
            return jsonify({"status": "error", "message": "Недействительная сессия"}), 401
        
        # Добавляем user_id в request для использования в функции
        request.user_id = user_id
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

def validate_date(date_str: str) -> bool:
    """Валидация формата даты"""
    if not date_str:
        return False
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False

def sanitize_filename(filename: str) -> str:
    """Удаляет недопустимые символы из имени файла"""
    # Удаляем недопустимые символы для Windows/Linux
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '_', filename)
    return filename

def validate_string(value, max_length=255, field_name="", allow_empty=False):
    """Валидация строкового значения"""
    if value is None:
        if allow_empty:
            return None
        raise ValueError(f"{field_name} не может быть пустым")
    
    if not isinstance(value, str):
        raise ValueError(f"{field_name} должен быть строкой")
    
    value = value.strip()
    
    if not value and not allow_empty:
        raise ValueError(f"{field_name} не может быть пустым")
    
    if len(value) > max_length:
        raise ValueError(f"{field_name} слишком длинный (максимум {max_length} символов)")
    
    return value

def validate_snils(snils):
    """Валидация формата СНИЛС"""
    if not snils:
        return None
    
    if not isinstance(snils, str):
        raise ValueError("СНИЛС должен быть строкой")
    
    # Удаляем пробелы и дефисы
    snils_clean = snils.replace('-', '').replace(' ', '')
    
    # Проверка формата СНИЛС (11 цифр)
    if not re.match(r'^\d{11}$', snils_clean):
        raise ValueError("Неверный формат СНИЛС (должно быть 11 цифр)")
    
    return snils_clean

def mask_sensitive_data(value, visible_chars=3):
    """Маскирует чувствительные данные для логирования"""
    if not value or len(str(value)) <= visible_chars * 2:
        return "***"
    str_value = str(value)
    return f"{str_value[:visible_chars]}***{str_value[-visible_chars:]}"

def check_rate_limit(identifier, max_requests=RATE_LIMIT_MAX_REQUESTS, window=RATE_LIMIT_WINDOW):
    """Проверяет rate limit для идентификатора (IP адрес или user_id)"""
    global _rate_limit_store
    current_time = time.time()
    
    with _rate_limit_lock:
        # Очищаем старые записи
        _rate_limit_store[identifier] = [
            timestamp for timestamp in _rate_limit_store[identifier]
            if current_time - timestamp < window
        ]
        
        # Проверяем лимит
        if len(_rate_limit_store[identifier]) >= max_requests:
            return False
        
        # Добавляем текущий запрос
        _rate_limit_store[identifier].append(current_time)
        return True

def get_client_identifier():
    """Получает идентификатор клиента для rate limiting"""
    # Используем IP адрес или X-Forwarded-For если есть прокси
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or 'unknown'
    # Удаляем множественные подчеркивания
    filename = re.sub(r'_+', '_', filename)
    # Ограничиваем длину имени файла
    if len(filename) > 200:
        filename = filename[:200]
    return filename.strip('_')

def check_program_exists(program: str) -> bool:
    """Проверяет наличие программы в системе"""
    try:
        if os.name == "nt":  # Windows
            # Проверяем через where (Windows)
            result = subprocess.run(
                ["where", program],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        else:  # Linux/MacOS
            result = subprocess.run(
                ["which", program],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
    except Exception:
        return False

@app.route('/api/generate_and_print_referral', methods=['POST'])
def generate_and_print_referral():
    """
    Генерация и печать направления на исследование
    
    Returns:
        Dict с результатом операции
    """
    output_path = None
    temp_dir = None
    try:
        patient_data = request.get_json()
        template_path = Path("hablon.docx")
        if not template_path.exists():
            raise FileNotFoundError(f"Шаблон {template_path} не найден")
        
        # Создаем временную директорию для файлов
        temp_dir = Path(tempfile.mkdtemp(prefix="referral_print_"))
        
        # Санитизируем имя файла
        safe_name = sanitize_filename(f"{patient_data.get('full_name', 'patient')}_{patient_data.get('study_date', 'date')}")
        output_path = temp_dir / f"referral_{safe_name}.docx"
        
        doc = Document(template_path)
        
        placeholders = {
            "{doctor_id}": patient_data.get("doctor_id", ""),
            "{full_name}": patient_data.get("full_name", ""),
            "{birthdate}": patient_data.get("birth_date", ""),
            "{insurance_policy_number}": patient_data.get("insurance", ""),
            "{snils}": patient_data.get("snils", ""),
            "{address}": patient_data.get("address", ""),
            "{clinical_diagnosis_text}": patient_data.get("clinical_diagnosis_text", ""),
            "{clinical_diagnosis_id}": patient_data.get("clinical_diagnosis_id", ""),
            "{study_date}": patient_data.get("study_date", ""),
            "{service_id}": patient_data.get("service_id", ""),
            "{transferred_to_doctor}": patient_data.get("transferred_to_doctor", "")
        }
        
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                text = run.text
                for key, value in placeholders.items():
                    if key in text:
                        run.text = text.replace(key, str(value))
        
        doc.save(output_path)
        logger.info(f"Документ сохранен: {output_path}")
        
        # Печать документа
        if os.name == "nt":  # Windows
            # Проверяем наличие Word
            word_paths = [
                r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
                r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
            ]
            
            word_exe = None
            for path in word_paths:
                if os.path.exists(path):
                    word_exe = path
                    break
            
            if not word_exe:
                # Пытаемся найти через where
                try:
                    result = subprocess.run(
                        ["where", "winword"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        word_exe = result.stdout.strip().split('\n')[0]
                except Exception:
                    pass
            
            if word_exe:
                # Пытаемся использовать win32api для печати (если установлен)
                use_win32 = False
                try:
                    import win32api
                    use_win32 = True
                except ImportError:
                    pass
                
                if use_win32:
                    try:
                        # Используем Windows API для печати
                        win32api.ShellExecute(
                            0,
                            "print",
                            str(output_path),
                            None,
                            ".",
                            0
                        )
                        logger.info(f"Документ отправлен на печать через Windows API: {output_path}")
                        # Даем время на печать
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"Ошибка при печати через win32api: {e}, пробуем альтернативный метод")
                        use_win32 = False
                
                if not use_win32:
                    # Используем прямой вызов Word
                    try:
                        process = subprocess.Popen(
                            [word_exe, str(output_path), "/mFilePrintDefault", "/mFileExit"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        # Ждем завершения с таймаутом
                        try:
                            process.wait(timeout=60)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            raise Exception("Таймаут при печати документа")
                        if process.returncode != 0:
                            raise Exception(f"Ошибка печати: код возврата {process.returncode}")
                        logger.info(f"Документ отправлен на печать через Word: {output_path}")
                    except Exception as e:
                        raise Exception(f"Ошибка при печати через Word: {str(e)}")
            else:
                # Fallback: используем os.startfile (может не работать для печати)
                try:
                    os.startfile(str(output_path), "print")
                    logger.info(f"Документ отправлен на печать через os.startfile: {output_path}")
                    # Даем время на печать
                    time.sleep(2)
                except Exception as e:
                    raise Exception(f"Word не найден и не удалось использовать альтернативный метод: {str(e)}")
                    
        elif os.name == "posix":  # Linux/MacOS
            # Проверяем наличие lp (стандартная утилита печати в Linux)
            if check_program_exists("lp"):
                try:
                    process = subprocess.run(
                        ["lp", str(output_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if process.returncode != 0:
                        raise Exception(f"Ошибка печати: {process.stderr}")
                    logger.info(f"Документ отправлен на печать через lp: {output_path}")
                except subprocess.TimeoutExpired:
                    raise Exception("Таймаут при печати документа")
            elif check_program_exists("libreoffice"):
                # Используем LibreOffice для печати
                try:
                    # Конвертируем в PDF и печатаем
                    pdf_path = output_path.with_suffix('.pdf')
                    process = subprocess.run(
                        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir), str(output_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if process.returncode == 0 and pdf_path.exists():
                        # Печатаем PDF
                        print_process = subprocess.run(
                            ["lp", str(pdf_path)],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if print_process.returncode != 0:
                            raise Exception(f"Ошибка печати PDF: {print_process.stderr}")
                        logger.info(f"Документ конвертирован в PDF и отправлен на печать: {pdf_path}")
                    else:
                        raise Exception(f"Ошибка конвертации в PDF: {process.stderr}")
                except subprocess.TimeoutExpired:
                    raise Exception("Таймаут при конвертации/печати документа")
            else:
                raise Exception("Не найдены программы для печати (lp или libreoffice)")
        
        # Удаляем временные файлы после успешной печати
        try:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Временная директория удалена: {temp_dir}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временную директорию {temp_dir}: {e}")
        
        return jsonify({"status": "success", "message": "Документ успешно сгенерирован и отправлен на печать"})
    except Exception as e:
        log_function_error("generate_and_print_referral", e)
        # Пытаемся удалить временные файлы даже при ошибке
        try:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})

@app.route('/api/save_patient_to_db', methods=['POST'])
def save_patient_to_db():
    conn = None
    cursor = None
    try:
        # Получаем данные из JSON
        data = request.get_json()
        
        # === Извлечение всех полей ===
        last_name = data.get('last_name')
        first_name = data.get('first_name')
        middle_name = data.get('middle_name')
        birth_date = data.get('birth_date')
        snils = data.get('snils')
        address = data.get('address')
        district_id = data.get('district_id')
        insurance = data.get('insurance')
        is_employed = data.get('is_employed', False)
        dismissal_date = data.get('dismissal_date')
        ambulatory_card_number = data.get('ambulatory_card_number')
        direction_number = data.get('direction_number')
        orderer = data.get('orderer')
        receipt_date = data.get('receipt_date')
        slides_count_mat = data.get('slides_count_mat')
        department_id = data.get('department_id')
        subdepartment_id = data.get('subdepartment_id')
        referring_doctor = data.get('referring_doctor_id')
        research_type = data.get('research_type')
        clinical_diagnosis = data.get('clinical_diagnosis')
        localization = data.get('localization')
        material_type = data.get('material_type')
        ciphers_id = data.get('ciphers_id')
        gist_matik = data.get('gist_matik')
        histologically_confirmed = data.get('histologically_confirmed', False)
        conclusion_matched = data.get('conclusion_matched', False)
        doctor = data.get('doctor_id')
        lab_technician = data.get('lab_technician_id')
        zno_dno = data.get('zno_dno')
        service = data.get('service')
        urgency = data.get('urgency')
        study_type = data.get('study_type')
        is_fluid = data.get('is_fluid', False)
        slides_count = data.get('slides_count')
        transferred_to_doctor = data.get('transferred_to_doctor')
        bethesda_term_id = data.get('bethesda_term_id')
        comment = data.get('comment')
        date_of_study = data.get('date_of_study')
        conclusion_text = data.get('conclusion_text')
        is_review = data.get('is_review', False)
        create_copy = data.get('create_copy', False)
        current_study_id = data.get('current_study_id')
        
        # Пустые строки для внешних ключей и опциональных полей — в NULL
        def _none_if_empty(v):
            return None if v == '' or v == [] else v
        
        doctor = _none_if_empty(doctor)
        lab_technician = _none_if_empty(lab_technician)
        orderer = _none_if_empty(orderer)
        referring_doctor = _none_if_empty(referring_doctor)
        # department_id может быть int или string (например '1', '3')
        if department_id and str(department_id).isdigit():
            department_id = int(department_id)
        else:
            department_id = _none_if_empty(department_id)
        # subdepartment_id — строка типа '1-11', '1-13'
        subdepartment_id = _none_if_empty(subdepartment_id)
        
        # === Валидация входных данных ===
        try:
            if last_name:
                last_name = validate_string(last_name, max_length=100, field_name="Фамилия", allow_empty=False)
            if first_name:
                first_name = validate_string(first_name, max_length=100, field_name="Имя", allow_empty=False)
            if middle_name:
                middle_name = validate_string(middle_name, max_length=100, field_name="Отчество", allow_empty=True)
            if snils:
                snils = validate_snils(snils)
            if address:
                address = validate_string(address, max_length=500, field_name="Адрес", allow_empty=True)
            if ambulatory_card_number:
                ambulatory_card_number = validate_string(ambulatory_card_number, max_length=50, field_name="Номер амбулаторной карты", allow_empty=True)
            if direction_number:
                direction_number = validate_string(direction_number, max_length=100, field_name="Номер направления", allow_empty=True)
            if insurance:
                insurance = validate_string(insurance, max_length=50, field_name="Страховой полис", allow_empty=True)
            if zno_dno:
                zno_dno = validate_string(zno_dno, max_length=50, field_name="ЗНО/ДНО", allow_empty=True)
            if comment:
                comment = validate_string(comment, max_length=1000, field_name="Комментарий", allow_empty=True)
            if conclusion_text:
                conclusion_text = validate_string(conclusion_text, max_length=5000, field_name="Текст заключения", allow_empty=True)
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 400
        
        # gist_matik → int
        if gist_matik is not None and gist_matik != '':
            try:
                gist_matik = int(gist_matik)
            except (ValueError, TypeError):
                gist_matik = None
        else:
            gist_matik = None
        
        # Валидация дат
        if birth_date and not validate_date(birth_date):
            return jsonify({"status": "error", "message": "Неверный формат даты рождения"}), 400
        if date_of_study and not validate_date(date_of_study):
            return jsonify({"status": "error", "message": "Неверный формат даты исследования"}), 400
        
        if not date_of_study and not (is_review and create_copy):
            date_of_study = date.today().strftime("%Y-%m-%d")
        
        full_name = f"{last_name} {first_name} {middle_name}".strip()
        snils_masked = mask_sensitive_data(snils, visible_chars=3) if snils else None
        logger.info(f"Сохранение пациента: {full_name}, дата рождения: {birth_date}, СНИЛС: {snils_masked}")
        
        # Получаем user_id из сессии для проверки блокировки
        session_hash = request.cookies.get('session_hash')
        current_user_id = None
        if session_hash:
            current_user_id = validate_session(session_hash)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SET statement_timeout = 30000")
        
        # === 1. ПАЦИЕНТ (поиск/создание по СНИЛС) ===
        patient_id = None
        if snils:
            cursor.execute("SELECT id FROM patients WHERE snils = %s FOR UPDATE", (snils,))
            result = cursor.fetchone()
            if result:
                patient_id = result['id']
            
            if patient_id:
                cursor.execute("""
                    UPDATE patients SET
                        full_name = %s, birthdate = %s, address = %s, district_id = %s,
                        insurance_policy_number = %s, is_employed = %s, dismissal_date = %s,
                        ambulatory_card_number = %s
                    WHERE id = %s RETURNING id
                """, (full_name, birth_date, address, district_id, insurance, is_employed,
                      dismissal_date, ambulatory_card_number, patient_id))
                patient_id = cursor.fetchone()['id']
                logger.info(f"Обновлён пациент с ID: {patient_id}")
            else:
                try:
                    cursor.execute("""
                        INSERT INTO patients (
                            full_name, birthdate, snils, address, district_id, insurance_policy_number,
                            is_employed, dismissal_date, ambulatory_card_number
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (snils) DO UPDATE SET
                            full_name = EXCLUDED.full_name,
                            birthdate = EXCLUDED.birthdate,
                            address = EXCLUDED.address,
                            district_id = EXCLUDED.district_id,
                            insurance_policy_number = EXCLUDED.insurance_policy_number,
                            is_employed = EXCLUDED.is_employed,
                            dismissal_date = EXCLUDED.dismissal_date,
                            ambulatory_card_number = EXCLUDED.ambulatory_card_number
                        RETURNING id
                    """, (full_name, birth_date, snils, address, district_id, insurance,
                          is_employed, dismissal_date, ambulatory_card_number))
                    patient_id = cursor.fetchone()['id']
                    logger.info(f"Создан пациент с ID: {patient_id}")
                except psycopg2.ProgrammingError:
                    conn.rollback()
                    cursor.execute("SELECT id FROM patients WHERE snils = %s", (snils,))
                    result = cursor.fetchone()
                    if result:
                        patient_id = result['id']
                        cursor.execute("""
                            UPDATE patients SET
                                full_name = %s, birthdate = %s, address = %s, district_id = %s,
                                insurance_policy_number = %s, is_employed = %s, dismissal_date = %s,
                                ambulatory_card_number = %s
                            WHERE id = %s RETURNING id
                        """, (full_name, birth_date, address, district_id, insurance, is_employed,
                              dismissal_date, ambulatory_card_number, patient_id))
                        patient_id = cursor.fetchone()['id']
                    else:
                        cursor.execute("""
                            INSERT INTO patients (
                                full_name, birthdate, snils, address, district_id, insurance_policy_number,
                                is_employed, dismissal_date, ambulatory_card_number
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (full_name, birth_date, snils, address, district_id, insurance,
                              is_employed, dismissal_date, ambulatory_card_number))
                        patient_id = cursor.fetchone()['id']
        
        # === 2. Бетесда термин ===
        try:
            if conclusion_text is not None and str(conclusion_text).strip():
                text_val = str(conclusion_text).strip()
                current_name = None
                if bethesda_term_id:
                    cursor.execute("SELECT full_name FROM betesda WHERE unique_id = %s", (bethesda_term_id,))
                    row = cursor.fetchone()
                    if row:
                        current_name = row[0] or ''
                
                if not bethesda_term_id or (current_name is not None and current_name.strip() != text_val):
                    cursor.execute("SELECT unique_id FROM betesda WHERE full_name = %s", (text_val,))
                    existing = cursor.fetchone()
                    if existing:
                        bethesda_term_id = existing[0]
                    else:
                        cursor.execute("INSERT INTO betesda (full_name) VALUES (%s) RETURNING unique_id", (text_val,))
                        bethesda_term_id = cursor.fetchone()[0]
        except Exception as e:
            log_function_error("match_or_create_bethesda_term", e)
        
        # === 3. КОПИЯ (пересмотр) ===
        if is_review and create_copy:
            if not current_study_id:
                raise ValueError("Невозможно создать копию — не указано оригинальное исследование")
            
            cursor.execute("""
                SELECT s.*, m.*
                FROM studies s
                JOIN materials m ON m.id = s.material_id
                WHERE s.id = %s
            """, (current_study_id,))
            original_data = cursor.fetchone()
            if not original_data:
                raise ValueError("Оригинальное исследование не найдено")
            
            cursor.execute("""
                INSERT INTO materials (
                    patient_id, direction_number, medical_organization_id, receipt_date,
                    slides_count, department_id, subdepartment_id, referring_doctor_id,
                    research_type_id, clinical_diagnosis_id, localization_id,
                    material_type_id, ciphers_id, gisolog_comment,
                    histologically_confirmed, conclusion_matched, is_reviewed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id
            """, (patient_id, original_data['direction_number'], original_data['medical_organization_id'],
                  original_data['receipt_date'], original_data['slides_count'],
                  original_data['department_id'], original_data.get('subdepartment_id'),
                  original_data['referring_doctor_id'], original_data['research_type_id'],
                  original_data['clinical_diagnosis_id'], original_data['localization_id'],
                  original_data['material_type_id'], original_data['ciphers_id'],
                  gist_matik, original_data['histologically_confirmed'],
                  original_data['conclusion_matched']))
            new_material_id = cursor.fetchone()['id']
            
            cursor.execute("""
                INSERT INTO studies (
                    patient_id, study_date, doctor_id, lab_technician_id, zno_dno,
                    service_id, urgency_id, study_type_id, is_fluid, slides_count,
                    transferred_to_doctor, bethesda_term_id, conclusion_text, comment, is_reviewed, material_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                RETURNING id
            """, (patient_id, date_of_study, doctor, lab_technician, zno_dno,
                  service, urgency, study_type, is_fluid, slides_count,
                  transferred_to_doctor, bethesda_term_id, conclusion_text,
                  comment, new_material_id))
            new_study_id = cursor.fetchone()['id']
            
            barcode = generate_barcode(new_study_id, date_of_study)
            cursor.execute("UPDATE studies SET barcode = %s WHERE id = %s", (barcode, new_study_id))
            cursor.execute("UPDATE materials SET studies_id = %s WHERE id = %s", (new_study_id, new_material_id))
            
            study_id = new_study_id
            material_id = new_material_id
        
        # === 4. РЕДАКТИРОВАНИЕ или СОЗДАНИЕ ===
        else:
            if current_study_id:
                cursor.execute("SELECT id, version, material_id FROM studies WHERE id = %s", (current_study_id,))
                existing_study = cursor.fetchone()
                
                if existing_study:
                    logger.info(f"Обновление исследования ID: {current_study_id}")
                    
                    current_version = existing_study['version'] or 0
                    expected_version = data.get('version', current_version)
                    
                    cursor.execute("""
                        UPDATE studies SET
                            patient_id = %s, study_date = %s, doctor_id = %s,
                            lab_technician_id = %s, zno_dno = %s, service_id = %s,
                            urgency_id = %s, study_type_id = %s, is_fluid = %s,
                            slides_count = %s, transferred_to_doctor = %s,
                            bethesda_term_id = %s, conclusion_text = %s, comment = %s,
                            is_reviewed = %s, version = version + 1
                        WHERE id = %s AND version = %s
                        RETURNING id, material_id
                    """, (patient_id, date_of_study, doctor, lab_technician, zno_dno,
                          service, urgency, study_type, is_fluid, slides_count,
                          transferred_to_doctor, bethesda_term_id, conclusion_text,
                          comment, is_review, current_study_id, expected_version))
                    
                    result = cursor.fetchone()
                    if not result:
                        return jsonify({
                            "status": "error",
                            "message": "Данные были изменены другим пользователем. Обновите страницу.",
                            "conflict": True
                        }), 409
                    
                    study_id = result['id']
                    material_id = result['material_id']
                    
                    cursor.execute("""
                        UPDATE materials SET
                            patient_id = %s, direction_number = %s, medical_organization_id = %s,
                            receipt_date = %s, slides_count = %s, department_id = %s,
                            subdepartment_id = %s,
                            referring_doctor_id = %s, research_type_id = %s,
                            clinical_diagnosis_id = %s, localization_id = %s,
                            material_type_id = %s, ciphers_id = %s, gisolog_comment = %s,
                            histologically_confirmed = %s, conclusion_matched = %s,
                            is_reviewed = %s
                        WHERE id = %s
                    """, (patient_id, direction_number, orderer, receipt_date,
                          slides_count_mat, department_id, subdepartment_id,
                          referring_doctor, research_type, clinical_diagnosis,
                          localization, material_type, ciphers_id, gist_matik,
                          histologically_confirmed, conclusion_matched, is_review,
                          material_id))
                    
                    logger.info(f"Исследование {current_study_id} успешно обновлено")
                else:
                    logger.info(f"Исследование ID {current_study_id} не найдено, создаём новое")
                    current_study_id = None
            
            if not current_study_id:
                cursor.execute("""
                    INSERT INTO materials (
                        patient_id, direction_number, medical_organization_id, receipt_date,
                        slides_count, department_id, subdepartment_id,
                        referring_doctor_id, research_type_id, clinical_diagnosis_id,
                        localization_id, material_type_id, ciphers_id, gisolog_comment,
                        histologically_confirmed, conclusion_matched, is_reviewed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (patient_id, direction_number, orderer, receipt_date,
                      slides_count_mat, department_id, subdepartment_id,
                      referring_doctor, research_type, clinical_diagnosis,
                      localization, material_type, ciphers_id, gist_matik,
                      histologically_confirmed, conclusion_matched, is_review))
                
                new_material_id = cursor.fetchone()['id']
                
                cursor.execute("""
                    INSERT INTO studies (
                        patient_id, study_date, doctor_id, lab_technician_id, zno_dno,
                        service_id, urgency_id, study_type_id, is_fluid, slides_count,
                        transferred_to_doctor, bethesda_term_id, conclusion_text, comment,
                        is_reviewed, material_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (patient_id, date_of_study, doctor, lab_technician, zno_dno,
                      service, urgency, study_type, is_fluid, slides_count,
                      transferred_to_doctor, bethesda_term_id, conclusion_text,
                      comment, is_review, new_material_id))
                
                new_study_id = cursor.fetchone()['id']
                
                barcode = generate_barcode(new_study_id, date_of_study)
                cursor.execute("UPDATE studies SET barcode = %s WHERE id = %s", (barcode, new_study_id))
                cursor.execute("UPDATE materials SET studies_id = %s WHERE id = %s", (new_study_id, new_material_id))
                
                study_id = new_study_id
                material_id = new_material_id
                logger.info(f"Создано новое исследование ID: {study_id}")
        
        conn.commit()
        
        if current_user_id and current_study_id:
            unlock_study(current_study_id, current_user_id)
        
        return jsonify({
            "status": "success",
            "message": "Данные успешно сохранены",
            "patient_id": patient_id,
            "study_id": study_id,
            "material_id": material_id
        })
        
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return handle_db_error(e, "save_patient_to_db")
    except ValueError as ve:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("save_patient_to_db", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)
            
@app.route('/api/check_patient_in_db', methods=['GET'])
def check_patient_in_db():
    try:
        surname = request.args.get('surname')
        firstname = request.args.get('firstname')
        patronymic = request.args.get('patronymic')
        birth_date = request.args.get('birth_date')
        study_id = request.args.get('study_id')
        conn = get_db_connection()
        cursor = conn.cursor()

        if surname and firstname and patronymic and birth_date:
            full_name = f"{surname} {firstname} {patronymic}".strip()
            logger.info(f"Поиск пациента: {full_name}, birth_date: {birth_date}")
            cursor.execute("""
                SELECT p.id AS patient_id
                FROM patients p
                WHERE p.full_name = %s AND p.birthdate = %s
            """, (full_name, birth_date))
            result = cursor.fetchone()
            if not result:
                logger.info("Пациент не найден")
                return {"status": "success", "message": "Пациент не найден", "patient_id": None}
            patient_id = result[0]
            logger.info(f"Найден пациент с id: {patient_id}")
            return {"status": "success", "message": "Пациент найден", "patient_id": patient_id}
        else:
            return {"status": "error", "message": "Недостаточно параметров для поиска пациента"}

    except Exception as e:
        log_function_error("check_patient_in_db", e)
        return {"status": "error", "message": f"Ошибка поиска: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_patient_studies', methods=['GET'])
def get_patient_studies():
    try:
        patient_id = request.args.get('patient_id')
        if not patient_id:
            logger.info("patient_id не указан")
            return {"status": "error", "message": "patient_id обязателен"}
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info(f"Запрос исследований для patient_id: {patient_id}")
        cursor.execute("""
            SELECT id, study_date, doctor_id, lab_technician_id, is_fluid, barcode, material_id, is_reviewed
            FROM studies 
            WHERE patient_id = %s
            ORDER BY study_date DESC NULLS LAST
        """, (patient_id,))
        studies = cursor.fetchall()
        
        if not studies:
            logger.info(f"Исследования не найдены для patient_id: {patient_id}")
            return {"status": "success", "message": "Исследования не найдены", "data": []}

        columns = [desc[0] for desc in cursor.description]
        studies_data = [dict(zip(columns, study)) for study in studies]
        
        for study in studies_data:
            if study['study_date']:
                try:
                    date_obj = datetime.strptime(str(study['study_date']), "%Y-%m-%d")
                    study['study_date'] = date_obj.strftime("%d-%m-%Y")
                except Exception:
                    study['study_date'] = str(study['study_date'])
                
        logger.info(f"Найдено исследований: {len(studies_data)}")
        return {
            "status": "success",
            "message": f"Найдено {len(studies_data)} исследований",
            "data": studies_data
        }
    except Exception as e:
        log_function_error("get_patient_studies", e)
        return {"status": "error", "message": f"Ошибка: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.route('/api/get_physician_data', methods=['GET'])
def get_physician_data():
    global PHYSICIAN_CACHE
    conn = None
    cursor = None
    try:
        # Проверяем кэш
        if PHYSICIAN_CACHE is not None and is_cache_valid('physician'):
            logger.debug("Данные врачей загружены из кэша")
            return {"status": "success", "data": PHYSICIAN_CACHE}
        
        # Загружаем из БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Загружаем все записи из physician, независимо от роли
        cursor.execute("""
            SELECT id, doctor_laboratory AS full_name
            FROM physician 
            ORDER BY doctor_laboratory
        """)
        
        results = cursor.fetchall()
        data = [{"id": row[0], "full_name": row[1]} for row in results]
        
        # Сохраняем в кэш
        PHYSICIAN_CACHE = data
        _cache_timestamps['physician'] = datetime.now()
        
        logger.info(f"Загружено {len(data)} записей из physician (кэшировано)")
        return {"status": "success", "data": data}
    except Exception as e:
        log_function_error("get_physician_data", e)
        return {"status": "error", "message": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)



            
@app.route('/api/get_study_data', methods=['GET'])
def get_study_data():
    try:
        study_id = request.args.get('study_id')
        if not study_id:
            logger.info("study_id не указан")
            return {"status": "error", "message": "study_id обязателен"}
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Запрос данных для study_id: {study_id}")
        # Проверяем существование столбцов для оптимистической блокировки
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'studies' AND column_name IN ('version', 'locked_by_user_id', 'locked_at')
        """)
        locking_columns = {row[0] for row in cursor.fetchall()}
        has_version = 'version' in locking_columns
        has_locked_by = 'locked_by_user_id' in locking_columns
        has_locked_at = 'locked_at' in locking_columns
        
        # Формируем SELECT с учетом наличия столбцов
        version_select = "s.version AS study_version" if has_version else "0 AS study_version"
        locked_by_select = "s.locked_by_user_id" if has_locked_by else "NULL AS locked_by_user_id"
        locked_at_select = "s.locked_at" if has_locked_at else "NULL AS locked_at"
        
        cursor.execute(f"""
            SELECT 
                p.*, 
                m.slides_count AS material_slides_count,
                s.slides_count AS study_slides_count,
                m.id AS material_id, 
                m.direction_number,
                m.medical_organization_id, 
                m.receipt_date, 
                m.department_id, 
                m.subdepartment_id,  -- Добавляем subdepartment_id
                m.referring_doctor_id,
                m.research_type_id, 
                m.clinical_diagnosis_id, 
                m.localization_id, 
                m.material_type_id,
                m.ciphers_id,
                m.histologically_confirmed, 
                m.conclusion_matched, 
                m.is_reviewed AS material_reviewed,
                m.gisolog_comment,
                s.study_date, 
                s.doctor_id, 
                s.lab_technician_id, 
                s.zno_dno, 
                s.service_id,
                s.urgency_id, 
                s.study_type_id, 
                s.is_fluid, 
                s.transferred_to_doctor,
                s.bethesda_term_id, 
                s.conclusion_text,
                s.comment, 
                s.barcode,
                s.is_reviewed AS study_reviewed,
                {version_select},
                {locked_by_select},
                {locked_at_select},
                mkb.code AS mkb_code, 
                mkb.diagnosis_list AS mkb_diagnosis,
                org.name_short AS medical_organization_text, 
                loc.location AS localization_text,
                otd.department AS department_text,
                subdept.department AS subdepartment_text,  -- Добавляем текстовое значение подотделения
                g.gist_name AS gistolog_comment_text
            FROM studies s
            LEFT JOIN patients p ON p.id = s.patient_id
            LEFT JOIN materials m ON m.id = s.material_id
            LEFT JOIN mkb ON CAST(NULLIF(TRIM(m.clinical_diagnosis_id), '') AS INTEGER) = mkb.id
            LEFT JOIN organ org ON m.medical_organization_id = org.id
            LEFT JOIN loc ON m.localization_id = loc.id
            LEFT JOIN otdel otd ON m.department_id = otd.id
            LEFT JOIN otdel subdept ON m.subdepartment_id = subdept.id  -- Присоединяем таблицу otdel для subdepartment_id
            LEFT JOIN gistolog g ON CAST(NULLIF(TRIM(m.gisolog_comment), '') AS INTEGER) = g.id
            WHERE s.id = %s
        """, (study_id,))
        result = cursor.fetchone()
        if not result:
            logger.info(f"Данные не найдены для study_id: {study_id}")
            return {"status": "success", "message": "Данные не найдены", "data": None}
        columns = [desc[0] for desc in cursor.description]
        result_dict = dict(zip(columns, result))

        # Данные пациента
        patient_data = {k: result_dict[k] for k in 
                       ['id', 'full_name', 'birthdate', 'snils', 'address', 'district_id', 
                        'insurance_policy_number', 'is_employed', 'dismissal_date', 'ambulatory_card_number'] 
                        if k in result_dict}

        # Данные материала
        material_data = {k: result_dict[k] for k in 
                        ['direction_number', 'medical_organization_id', 'receipt_date', 'material_slides_count',
                         'department_id', 'subdepartment_id', 'referring_doctor_id', 'research_type_id', 
                         'clinical_diagnosis_id', 'localization_id', 'material_type_id', 'ciphers_id',
                         'histologically_confirmed', 'conclusion_matched', 'material_reviewed', 'gisolog_comment'] 
                        if k in result_dict}
        material_data['slides_count'] = result_dict.get('material_slides_count')
        material_data['clinical_diagnosis_text'] = (f"{result_dict['mkb_code']} - {result_dict['mkb_diagnosis']}" 
                                                 if result_dict.get('mkb_code') else None)
        material_data['medical_organization_text'] = result_dict.get('medical_organization_text')
        material_data['localization_text'] = result_dict.get('localization_text')
        material_data['department_text'] = result_dict.get('department_text')
        material_data['subdepartment_text'] = result_dict.get('subdepartment_text')  # Добавляем текст подотделения
        # Возвращаем как ID, так и текст для заключения гистолога
        material_data['gisolog_comment_text'] = result_dict.get('gistolog_comment_text')

        # Данные исследования
        study_data = {k: result_dict[k] for k in 
                     ['study_date', 'doctor_id', 'lab_technician_id', 'zno_dno', 'service_id',
                      'urgency_id', 'study_type_id', 'is_fluid', 'study_slides_count', 'transferred_to_doctor',
                      'bethesda_term_id', 'conclusion_text', 'comment', 'barcode', 'study_reviewed', 
                      'study_version', 'locked_by_user_id', 'locked_at'] if k in result_dict}
        study_data['slides_count'] = result_dict.get('study_slides_count')
        study_data['version'] = result_dict.get('study_version', 0)
        
        # Получаем информацию о пользователе, который редактирует (если есть)
        locked_by_user_id = result_dict.get('locked_by_user_id')
        if locked_by_user_id:
            cursor.execute("SELECT fio_name FROM \"user\" WHERE id = %s", (locked_by_user_id,))
            locked_user = cursor.fetchone()
            if locked_user:
                study_data['locked_by_fio'] = locked_user[0]
            study_data['locked_at'] = str(result_dict.get('locked_at')) if result_dict.get('locked_at') else None

        # Преобразование дат в строковый формат
        for data in [patient_data, material_data, study_data]:
            for key in ['birthdate', 'receipt_date', 'study_date', 'dismissal_date']:
                if key in data and data[key]:
                    data[key] = str(data[key])

        # Убедимся, что is_fluid всегда имеет значение (True/False)
        if 'is_fluid' in study_data and study_data['is_fluid'] is None:
            study_data['is_fluid'] = False

        # Проверяем is_reviewed в обоих таблицах
        is_reviewed = False
        if 'material_reviewed' in material_data and material_data['material_reviewed']:
            is_reviewed = True
        if 'study_reviewed' in study_data and study_data['study_reviewed']:
            is_reviewed = True

        logger.info(f"Найдены данные для study_id {study_id}")
        return {
            "status": "success",
            "message": "Данные найдены",
            "data": {
                "patient": patient_data if patient_data.get('id') else None,
                "material": material_data if any(v is not None for v in material_data.values()) else None,
                "study": study_data if any(study_data.values()) else None,
                "is_reviewed": is_reviewed
            }
        }
    except Exception as e:
        log_function_error("get_study_data", e)
        return {"status": "error", "message": f"Ошибка: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)




@app.route('/api/check_study_lock', methods=['GET'])
def check_study_lock_endpoint():
    """Проверяет, заблокировано ли исследование другим пользователем"""
    conn = None
    cursor = None
    try:
        study_id = request.args.get('study_id')
        if not study_id:
            return jsonify({"status": "error", "message": "study_id обязателен"}), 400
        
        session_hash = request.cookies.get('session_hash')
        current_user_id = None
        if session_hash:
            current_user_id = validate_session(session_hash)
        
        lock_info = check_study_lock(study_id, current_user_id)
        
        if lock_info and lock_info.get("locked"):
            return jsonify({
                "status": "locked",
                "message": f"Исследование редактируется пользователем: {lock_info.get('locked_by_fio', 'Неизвестный пользователь')}",
                "locked_by_fio": lock_info.get('locked_by_fio'),
                "locked_by_user_id": lock_info.get('locked_by_user_id'),
                "locked_at": lock_info.get('locked_at')
            }), 200
        else:
            return jsonify({
                "status": "unlocked",
                "message": "Исследование не заблокировано"
            }), 200
    except Exception as e:
        log_function_error("check_study_lock_endpoint", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/lock_study', methods=['POST'])
def lock_study_endpoint():
    """Устанавливает блокировку исследования для текущего пользователя"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        study_id = data.get('study_id')
        if not study_id:
            return jsonify({"status": "error", "message": "study_id обязателен"}), 400
        
        session_hash = request.cookies.get('session_hash')
        if not session_hash:
            return jsonify({"status": "error", "message": "Требуется авторизация"}), 401
        
        current_user_id = validate_session(session_hash)
        if not current_user_id:
            return jsonify({"status": "error", "message": "Недействительная сессия"}), 401
        
        lock_result = lock_study(study_id, current_user_id)
        
        if lock_result and lock_result.get("locked"):
            return jsonify({
                "status": "error",
                "message": f"Исследование редактируется пользователем: {lock_result.get('locked_by_fio', 'Неизвестный пользователь')}",
                "locked_by_fio": lock_result.get('locked_by_fio'),
                "locked_by_user_id": lock_result.get('locked_by_user_id'),
                "locked_at": lock_result.get('locked_at')
            }), 409
        else:
            return jsonify({
                "status": "success",
                "message": "Блокировка установлена"
            }), 200
    except Exception as e:
        log_function_error("lock_study_endpoint", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/unlock_study', methods=['POST'])
def unlock_study_endpoint():
    """Снимает блокировку исследования"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        study_id = data.get('study_id')
        if not study_id:
            return jsonify({"status": "error", "message": "study_id обязателен"}), 400
        
        session_hash = request.cookies.get('session_hash')
        if not session_hash:
            return jsonify({"status": "error", "message": "Требуется авторизация"}), 401
        
        current_user_id = validate_session(session_hash)
        if not current_user_id:
            return jsonify({"status": "error", "message": "Недействительная сессия"}), 401
        
        success = unlock_study(study_id, current_user_id)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Блокировка снята"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Не удалось снять блокировку"
            }), 400
    except Exception as e:
        log_function_error("unlock_study_endpoint", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_patient_data', methods=['GET'])
def get_patient_data():
    try:
        patient_id = request.args.get('patient_id')
        if not patient_id:
            logger.info("patient_id не указан")
            return {"status": "error", "message": "patient_id обязателен"}
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info(f"Запрос данных пациента для patient_id: {patient_id}")
        cursor.execute("""
            SELECT id, full_name, birthdate, snils, address, district_id, 
                   insurance_policy_number, is_employed, dismissal_date, ambulatory_card_number
            FROM patients
            WHERE id = %s
        """, (patient_id,))
        result = cursor.fetchone()
        
        if not result:
            logger.info(f"Пациент не найден для patient_id: {patient_id}")
            return {"status": "success", "message": "Пациент не найден", "data": None}

        columns = [desc[0] for desc in cursor.description]
        patient_data = dict(zip(columns, result))
        
        # Преобразование даты в строковый формат
        if patient_data['birthdate']:
            patient_data['birthdate'] = str(patient_data['birthdate'])
        if patient_data['dismissal_date']:
            patient_data['dismissal_date'] = str(patient_data['dismissal_date'])

        logger.info(f"Найдены данные пациента для patient_id {patient_id}:", patient_data)
        return {
            "status": "success",
            "message": "Данные пациента найдены",
            "data": patient_data
        }
    except Exception as e:
        log_function_error("get_patient_data", e)
        return {"status": "error", "message": f"Ошибка: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)




def preload_mkb_data():
    global MKB_CACHE
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, code, diagnosis_list FROM mkb')
        rows = cursor.fetchall()
        
        MKB_CACHE = [{"id": row[0], "text": f"{row[1]} - {row[2]}"} for row in rows]
        logger.info(f"Загружено {len(MKB_CACHE)} записей МКБ")
    except Exception as e:
        log_function_error("preload_mkb_data", e)
        MKB_CACHE = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/search_mkb_data', methods=['GET'])
def search_mkb_data():
    term = request.args.get('term', '')
    limit = int(request.args.get('limit', 50))
    
    if not term:
        return jsonify(MKB_CACHE[:limit])
    
    query = term.lower()
    filtered_results = [item for item in MKB_CACHE if query in item["text"].lower()][:limit]
    return jsonify(filtered_results)



@app.route('/api/get_bethesda_data', methods=['GET'])
def get_bethesda_data():
    return jsonify(BETHESDA_DATA)

@app.route('/api/login', methods=['POST'])
def login():
    conn = None
    cursor = None
    try:
        # Rate limiting для login endpoint (максимум 5 попыток в минуту)
        client_id = get_client_identifier()
        if not check_rate_limit(f"login:{client_id}", max_requests=5, window=60):
            logger.warning(f"Rate limit exceeded for login from {client_id}")
            return jsonify({"status": "error", "message": "Слишком много попыток входа. Попробуйте позже."}), 429
        
        # Получаем данные из JSON
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"status": "error", "message": "Логин и пароль обязательны"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Устанавливаем timeout для транзакции (10 секунд)
        cursor.execute("SET statement_timeout = 10000")
        
        # Используем SELECT FOR UPDATE для блокировки строки и предотвращения race condition
        cursor.execute("""
            SELECT id, fio_name, status, password_hash, password_salt, password, failed_attempts, lock_until
            FROM "user"
            WHERE login = %s
            LIMIT 1
            FOR UPDATE
        """, (username,))
        row = cursor.fetchone()
        if row:
            user_id, fio_name, user_status, pwd_hash, pwd_salt, legacy_plain, failed_attempts, lock_until = row
            # Enforce lockout
            now = datetime.utcnow()
            if lock_until and isinstance(lock_until, datetime) and lock_until > now:
                conn.rollback()
                return jsonify({"status": "failure", "message": "Аккаунт заблокирован. Попробуйте позже."})
            ok = False
            if pwd_hash and pwd_salt:
                ok = verify_password(password, pwd_salt, pwd_hash)
            elif legacy_plain:
                if legacy_plain == password:
                    salt = generate_password_salt()
                    new_hash = hash_password_with_salt(password, salt)
                    cursor.execute("UPDATE \"user\" SET password_hash=%s, password_salt=%s, password=NULL WHERE id=%s", (new_hash, salt, str(user_id)))
                    conn.commit()
                    ok = True
            if ok:
                # reset counters and clear plaintext password if any
                cursor.execute("UPDATE \"user\" SET failed_attempts=0, lock_until=NULL, password=NULL WHERE id=%s", (str(user_id),))
                conn.commit()
                session_hash = generate_session_id()
                if not create_user_session(user_id, session_hash):
                    return jsonify({"status": "error", "message": "Ошибка создания сессии"}), 500
                log_user_login(username)
                response = jsonify({
                    "status": "success",
                    "message": "Успешно",
                    "fio": fio_name,
                    "user_status": user_status if user_status else 'user'
                })
                response.set_cookie('session_hash', session_hash, max_age=48*60*60, httponly=True, secure=False, samesite='Lax')
                return response
            else:
                # Используем атомарное обновление для предотвращения race condition
                # Увеличиваем failed_attempts прямо в БД, используя текущее значение
                now = datetime.utcnow()
                if (failed_attempts or 0) + 1 >= 10:
                    lock_ts = now + timedelta(minutes=30)
                    cursor.execute("""
                        UPDATE "user" 
                        SET failed_attempts = COALESCE(failed_attempts, 0) + 1, 
                            lock_until = %s 
                        WHERE id = %s
                    """, (lock_ts, str(user_id)))
                else:
                    cursor.execute("""
                        UPDATE "user" 
                        SET failed_attempts = COALESCE(failed_attempts, 0) + 1 
                        WHERE id = %s
                    """, (str(user_id),))
                conn.commit()
                log_function_error("login", f"Попытка пользователя {username}: неверный логин или пароль")
                return jsonify({"status": "failure", "message": "Неверный логин или пароль"})
        if conn:
            conn.rollback()
        log_function_error("login", f"Попытка пользователя {username}: пользователь не найден")
        return jsonify({"status": "failure", "message": "Неверный логин или пароль"})
            
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("login", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/logout', methods=['POST'])
def logout():
    """Выход из системы"""
    try:
        session_hash = request.cookies.get('session_hash')
        if session_hash:
            invalidate_session(session_hash)
        
        response = jsonify({"status": "success", "message": "Выход выполнен успешно"})
        response.delete_cookie('session_hash')
        return response
    except Exception as e:
        log_function_error("logout", e)
        return jsonify({"status": "error", "message": "Ошибка выхода из системы"}), 500

@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    """Проверка авторизации пользователя"""
    conn = None
    cursor = None
    try:
        session_hash = request.cookies.get('session_hash')
        if not session_hash:
            return jsonify({"status": "error", "message": "Требуется авторизация"}), 401
        
        user_id = validate_session(session_hash)
        if not user_id:
            return jsonify({"status": "error", "message": "Недействительная сессия"}), 401
        
        # Получаем информацию о пользователе
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT "fio_name", "status", login
            FROM "user" 
            WHERE id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        if result:
            fio_name, user_status, login = result
            return jsonify({
                "status": "success",
                "user": {
                    "id": user_id,
                    "fio": fio_name,
                    "status": user_status,
                    "login": login
                }
            })
        else:
            return jsonify({"status": "error", "message": "Пользователь не найден"}), 404
            
    except Exception as e:
        log_function_error("check_auth", e)
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint для мониторинга"""
    conn = None
    cursor = None
    try:
        # Проверка БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        
        # Проверка пула
        pool_ok = connection_pool is not None
        
        return jsonify({
            "status": "healthy" if pool_ok else "degraded",
            "database": "connected",
            "pool": "ok" if pool_ok else "not_initialized",
            "timestamp": datetime.now().isoformat()
        }), 200 if pool_ok else 503
    except Exception as e:
        log_function_error("health_check", e)
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/pool_stats', methods=['GET'])
def pool_stats():
    """Возвращает статистику пула соединений БД (для мониторинга)"""
    try:
        global connection_pool, _pool_stats
        stats = {
            "pool_initialized": connection_pool is not None,
            "max_connections": _pool_stats.get('max_connections', 0),
            "active_connections": _pool_stats.get('active_connections', 0),
            "total_connections_used": _pool_stats.get('total_connections', 0),
            "available_connections": max(0, _pool_stats.get('max_connections', 0) - _pool_stats.get('active_connections', 0)),
            "utilization_percent": round((_pool_stats.get('active_connections', 0) / max(1, _pool_stats.get('max_connections', 1))) * 100, 2)
        }
        return jsonify({"status": "success", "data": stats})
    except Exception as e:
        log_function_error("pool_stats", e)
        return jsonify({"status": "error", "message": str(e)}), 500

def get_active_users_count():
    """Получает количество активных пользователей из БД"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем активные сессии (не истекшие и активные)
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as active_count,
                   COUNT(*) as total_sessions
            FROM user_sessions 
            WHERE is_active = TRUE 
            AND expires_at > CURRENT_TIMESTAMP
        """)
        
        result = cursor.fetchone()
        if result:
            active_count, total_sessions = result
            return {
                'active_users': active_count,
                'total_sessions': total_sessions
            }
        return {'active_users': 0, 'total_sessions': 0}
    except Exception as e:
        log_function_error("get_active_users_count", e)
        return {'active_users': 0, 'total_sessions': 0, 'error': str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def get_active_users_details():
    """Получает детальную информацию об активных пользователях"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем активные сессии с информацией о пользователях
        cursor.execute("""
            SELECT DISTINCT ON (us.user_id)
                us.user_id,
                u.fio_name,
                u.login,
                u.status,
                us.ip_address,
                us.created_at,
                us.expires_at
            FROM user_sessions us
            JOIN "user" u ON us.user_id = u.id
            WHERE us.is_active = TRUE 
            AND us.expires_at > CURRENT_TIMESTAMP
            ORDER BY us.user_id, us.created_at DESC
        """)
        
        users = []
        for row in cursor.fetchall():
            user_id, fio_name, login, status, ip_address, created_at, expires_at = row
            users.append({
                'user_id': user_id,
                'fio': fio_name,
                'login': login,
                'status': status,
                'ip_address': ip_address,
                'login_time': created_at.isoformat() if created_at else None,
                'expires_at': expires_at.isoformat() if expires_at else None
            })
        
        return users
    except Exception as e:
        log_function_error("get_active_users_details", e)
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Возвращает полную статистику системы: активные пользователи, нагрузка, метрики"""
    try:
        # Получаем активных пользователей
        active_users_data = get_active_users_count()
        active_users_list = get_active_users_details()
        
        # Получаем метрики запросов
        with _metrics_lock:
            total_requests = _request_metrics['total_requests']
            requests_per_minute = len(_request_metrics['requests_per_minute'])
            errors = _request_metrics['errors']
            response_times = _request_metrics['response_times']
            
            # Вычисляем среднее время ответа
            avg_response_time = 0
            max_response_time = 0
            min_response_time = 0
            if response_times:
                avg_response_time = round(sum(response_times) / len(response_times) * 1000, 2)  # в миллисекундах
                max_response_time = round(max(response_times) * 1000, 2)
                min_response_time = round(min(response_times) * 1000, 2)
            
            uptime_seconds = (datetime.now() - _request_metrics['start_time']).total_seconds()
            uptime_hours = round(uptime_seconds / 3600, 2)
        
        # Получаем системные метрики (если psutil доступен)
        system_metrics = {}
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process()
                cpu_percent = process.cpu_percent(interval=0.1)
                memory_info = process.memory_info()
                memory_mb = round(memory_info.rss / 1024 / 1024, 2)
                
                # Системные метрики
                system_cpu = psutil.cpu_percent(interval=0.1)
                system_memory = psutil.virtual_memory()
                
                system_metrics = {
                    'process_cpu_percent': round(cpu_percent, 2),
                    'process_memory_mb': memory_mb,
                    'system_cpu_percent': round(system_cpu, 2),
                    'system_memory_percent': round(system_memory.percent, 2),
                    'system_memory_total_gb': round(system_memory.total / 1024 / 1024 / 1024, 2),
                    'system_memory_available_gb': round(system_memory.available / 1024 / 1024 / 1024, 2)
                }
            except Exception as e:
                logger.warning(f"Ошибка получения системных метрик: {e}")
                system_metrics = {'error': str(e)}
        else:
            system_metrics = {'available': False, 'message': 'psutil не установлен'}
        
        # Получаем статистику пула БД
        db_pool_stats = {}
        try:
            global connection_pool, _pool_stats
            db_pool_stats = {
                "pool_initialized": connection_pool is not None,
                "max_connections": _pool_stats.get('max_connections', 0),
                "active_connections": _pool_stats.get('active_connections', 0),
                "available_connections": max(0, _pool_stats.get('max_connections', 0) - _pool_stats.get('active_connections', 0)),
                "utilization_percent": round((_pool_stats.get('active_connections', 0) / max(1, _pool_stats.get('max_connections', 1))) * 100, 2)
            }
        except Exception as e:
            db_pool_stats = {'error': str(e)}
        
        # Формируем итоговый ответ
        stats = {
            'timestamp': datetime.now().isoformat(),
            'uptime_hours': uptime_hours,
            'users': {
                'active_count': active_users_data.get('active_users', 0),
                'total_sessions': active_users_data.get('total_sessions', 0),
                'active_users_list': active_users_list
            },
            'requests': {
                'total': total_requests,
                'per_minute': requests_per_minute,
                'errors': errors,
                'error_rate_percent': round((errors / max(1, total_requests)) * 100, 2),
                'response_time_ms': {
                    'avg': avg_response_time,
                    'max': max_response_time,
                    'min': min_response_time
                }
            },
            'system': system_metrics,
            'database_pool': db_pool_stats
        }
        
        return jsonify({"status": "success", "data": stats})
    except Exception as e:
        log_function_error("get_stats", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/invalidate_cache', methods=['POST'])
def invalidate_cache_endpoint():
    """Инвалидирует кэши справочников (для администраторов)"""
    try:
        cache_name = request.json.get('cache_name') if request.is_json else None
        invalidate_cache(cache_name)
        return jsonify({
            "status": "success", 
            "message": f"Кэш {'всех справочников' if cache_name is None else f'({cache_name})'} инвалидирован"
        })
    except Exception as e:
        log_function_error("invalidate_cache_endpoint", e)
        return jsonify({"status": "error", "message": str(e)}), 500

# @app.route('/api/load_organ_data', methods=['GET'])
# def load_organ_data():
#     conn = None
#     cursor = None
#     try:
#         conn = get_db_connection()
#         cursor = conn.cursor()
#         cursor.execute("SELECT id, name_short FROM organ WHERE region_name = 'Курганская область' ORDER BY name_short")
#         results = cursor.fetchall()
#         # Предполагаем, что organ.id — строка OID, но нужно число для materials
#         # Если есть числовое поле, замените id на него (например, numeric_id)
#         data = [{"id": row[0], "text": row[1]} for row in results]
#         logger.info(f"Загружено {len(data)} организаций из таблицы organ")
#         return jsonify(data)
#     except Exception as e:
#         logger.error(f"Ошибка загрузки организаций: {str(e)}")
#         return jsonify([])
#     finally:
#         if cursor:
#             cursor.close()
#         if conn:
#             return_db_connection(conn)

@app.route('/api/load_organ_data', methods=['GET'])
def load_organ_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Используем строковое значение для region_id
        cursor.execute("SELECT id, name_short FROM organ WHERE region_id = '45' ORDER BY name_short LIMIT 1000")
        results = cursor.fetchall()
        data = [{"id": row[0], "text": row[1]} for row in results]
        logger.info(f"Загружено {len(data)} организаций из таблицы organ")
        return jsonify(data)
    except Exception as e:
        log_function_error("load_organ_data", e)
        return jsonify([])
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_all_studies', methods=['GET'])
def get_all_studies():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT s.id, s.study_date, s.doctor_id, s.lab_technician_id, s.is_fluid, s.barcode, s.material_id
            FROM studies s
            WHERE 1=1
        """
        params = []

        # Фильтр по дате
        if request.args.get('date_filter') == 'today':
            query += " AND s.study_date = CURRENT_DATE"
        elif request.args.get('date_filter') == 'month':
            query += " AND s.study_date >= date_trunc('month', CURRENT_DATE)"
        elif request.args.get('date_filter') == 'custom' and request.args.get('date_from') and request.args.get('date_to'):
            query += " AND s.study_date BETWEEN %s AND %s"
            params.extend([request.args.get('date_from'), request.args.get('date_to')])

        # Фильтр по врачу
        if request.args.get('doctor'):
            query += " AND s.doctor_id = %s"
            params.append(request.args.get('doctor'))

        # Фильтр по услуге
        if request.args.get('service'):
            query += " AND s.service_id = %s"
            params.append(request.args.get('service'))

        # Пагинация
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))  # По умолчанию 50 записей на страницу
        offset = (page - 1) * per_page
        
        # Сначала получаем общее количество для пагинации
        count_query = "SELECT COUNT(*) FROM (" + query + ") AS count_query"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Добавляем LIMIT и OFFSET
        query += " ORDER BY s.study_date DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        studies = [
            {
                'id': row[0],
                'study_date': row[1],
                'doctor_id': row[2],
                'lab_technician_id': row[3],
                'is_fluid': row[4],
                'barcode': row[5],
                'material_id': row[6]
            } for row in results
        ]
        # Format study_date to DD-MM-YYYY
        for study in studies:
            if study['study_date']:
                try:
                    date_obj = datetime.strptime(str(study['study_date']), "%Y-%m-%d")
                    study['study_date'] = date_obj.strftime("%d-%m-%Y")
                except Exception:
                    study['study_date'] = str(study['study_date'])
        
        total_pages = (total_count + per_page - 1) // per_page  # Округление вверх
        
        logger.info(f"Найдено исследований: {len(studies)} из {total_count} (страница {page}/{total_pages})")
        return jsonify({
            "status": "success", 
            "data": studies,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        })
    except Exception as e:
        log_function_error("get_studies", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.route('/api/delete_study', methods=['DELETE'])
def delete_study():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        study_id = data.get('study_id')
        material_id = data.get('material_id')
        
        if not study_id:
            return jsonify({"status": "error", "message": "study_id обязателен"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем material_id из таблицы studies для проверки
        cursor.execute("SELECT material_id FROM studies WHERE id = %s", (study_id,))
        study_row = cursor.fetchone()
        if study_row:
            db_material_id = study_row[0]
            
            # Удаляем материал, если он связан с этим исследованием
            if db_material_id:
                # Проверяем, что в таблице materials поле studies_id соответствует удаляемому study_id
                cursor.execute("SELECT id FROM materials WHERE id = %s AND studies_id = %s", (db_material_id, study_id))
                material_row = cursor.fetchone()
                if material_row:
                    cursor.execute("DELETE FROM materials WHERE id = %s AND studies_id = %s", (db_material_id, study_id))
                    logger.info(f"Удален материал с ID: {db_material_id} (связан с study_id: {study_id})")
                else:
                    logger.warning(f"Материал с ID {db_material_id} не связан с study_id {study_id}, пропускаем удаление материала")
        
        # Затем удаляем исследование
        cursor.execute("DELETE FROM studies WHERE id = %s", (study_id,))
        logger.info(f"Удалено исследование с ID: {study_id}")
        
        conn.commit()
        return jsonify({"status": "success", "message": "Исследование удалено"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("delete_study", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.route('/api/get_services_data', methods=['GET'])
def get_services_data():
    global SERVICES_CACHE
    conn = None
    cursor = None
    try:
        # Проверяем кэш
        if SERVICES_CACHE is not None and is_cache_valid('services'):
            logger.debug("Данные услуг загружены из кэша")
            return jsonify({"status": "success", "data": SERVICES_CACHE})
        
        # Загружаем из БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Запрос к таблице service для получения id и name_service
        cursor.execute("""
            SELECT id, name_service
            FROM service
            ORDER BY name_service
            LIMIT 500
        """)
        
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        # Сохраняем в кэш
        SERVICES_CACHE = data
        _cache_timestamps['services'] = datetime.now()
        
        logger.info(f"Загружено {len(data)} услуг из таблицы service (кэшировано)")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_services_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)




@app.route('/api/get_bethesda_terms', methods=['GET'])
def get_bethesda_terms():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Изменяем SQL-запрос для выбора abbreviation и full_name
        cursor.execute("SELECT unique_id, abbreviation, full_name FROM betesda ORDER BY full_name LIMIT 500")
        results = cursor.fetchall()
        
        # Формируем список словарей с нужным форматом
        data = [
            {
                "id": row[0],
                "name": f"{row[1]} - {row[2]}" if row[1] else row[2]  # Если abbreviation есть, добавляем его; иначе только full_name
            }
            for row in results
        ]
        
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)
@app.route('/api/get_study_characters', methods=['GET'])
def get_study_characters():
    global STUDY_CHARACTERS_CACHE
    conn = None
    cursor = None
    try:
        # Проверяем кэш
        if STUDY_CHARACTERS_CACHE is not None and is_cache_valid('study_characters'):
            logger.debug("Характеры исследований загружены из кэша")
            return jsonify({"status": "success", "data": STUDY_CHARACTERS_CACHE})
        
        # Загружаем из БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, character FROM study_character ORDER BY character LIMIT 100")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        # Сохраняем в кэш
        STUDY_CHARACTERS_CACHE = data
        _cache_timestamps['study_characters'] = datetime.now()
        
        logger.debug(f"Характеры исследований загружены из БД и кэшированы ({len(data)} записей)")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_sample_types', methods=['GET'])
def get_sample_types():
    global SAMPLE_TYPES_CACHE
    conn = None
    cursor = None
    try:
        # Проверяем кэш
        if SAMPLE_TYPES_CACHE is not None and is_cache_valid('sample_types'):
            logger.debug("Типы образцов загружены из кэша")
            return jsonify({"status": "success", "data": SAMPLE_TYPES_CACHE})
        
        # Загружаем из БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT code, name FROM sample_types ORDER BY name LIMIT 100")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        # Сохраняем в кэш
        SAMPLE_TYPES_CACHE = data
        _cache_timestamps['sample_types'] = datetime.now()
        
        logger.debug(f"Типы образцов загружены из БД и кэшированы ({len(data)} записей)")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_service_types', methods=['GET'])
def get_service_types():
    global SERVICE_TYPES_CACHE
    conn = None
    cursor = None
    try:
        # Проверяем кэш
        if SERVICE_TYPES_CACHE is not None and is_cache_valid('service_types'):
            logger.debug("Типы услуг загружены из кэша")
            return jsonify({"status": "success", "data": SERVICE_TYPES_CACHE})
        
        # Загружаем из БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM service_types ORDER BY name LIMIT 200")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        # Сохраняем в кэш
        SERVICE_TYPES_CACHE = data
        _cache_timestamps['service_types'] = datetime.now()
        
        logger.debug(f"Типы услуг загружены из БД и кэшированы ({len(data)} записей)")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)































@app.route('/api/search_study_by_case_number', methods=['GET'])
def search_study_by_case_number():
    try:
        case_number = request.args.get('case_number')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info(f"Поиск исследования по номеру случая: {case_number}")
        
        # Предполагаем, что case_number соответствует study.id
        cursor.execute("""
            SELECT id, patient_id 
            FROM studies 
            WHERE id = %s
        """, (case_number,))
        
        result = cursor.fetchone()
        
        if not result:
            logger.info(f"Исследование с номером {case_number} не найдено")
            return jsonify({"status": "success", "message": "Исследование не найдено", "data": None})
            
        study_id, patient_id = result
        logger.info(f"Найдено исследование: id={study_id}, patient_id={patient_id}")
        
        return jsonify({
            "status": "success",
            "message": "Исследование найдено",
            "data": {
                "study_id": study_id,
                "patient_id": patient_id
            }
        })
        
    except Exception as e:
        log_function_error("search_study_by_case_number", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)




@app.route('/api/search_study_by_date', methods=['GET'])
def search_study_by_date():
    try:
        study_date = request.args.get('study_date')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info(f"Поиск исследования по дате: {study_date}")
        
        cursor.execute("""
            SELECT id, patient_id 
            FROM studies 
            WHERE study_date = %s
            LIMIT 1
        """, (study_date,))
        
        result = cursor.fetchone()
        
        if not result:
            logger.info(f"Исследование с датой {study_date} не найдено")
            return jsonify({"status": "success", "message": "Исследование не найдено", "data": None})
            
        study_id, patient_id = result
        logger.info(f"Найдено исследование: id={study_id}, patient_id={patient_id}")
        
        return jsonify({
            "status": "success",
            "message": "Исследование найдено",
            "data": {
                "study_id": study_id,
                "patient_id": patient_id
            }
        })
        
    except Exception as e:
        log_function_error("search_study_by_date", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)









@app.route('/api/search_study_by_direction_number', methods=['GET'])
def search_study_by_direction_number():
    try:
        direction_number = request.args.get('direction_number')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info(f"Поиск материала по номеру направления: '{direction_number}'")
        
        # Ищем patient_id в materials по direction_number
        cursor.execute("""
            SELECT patient_id
            FROM materials
            WHERE direction_number = %s
            LIMIT 1
        """, (str(direction_number),))
        
        result = cursor.fetchone()
        
        if not result:
            logger.info(f"Материал с номером направления '{direction_number}' не найден")
            cursor.execute("SELECT direction_number FROM materials LIMIT 5")
            existing_numbers = cursor.fetchall()
            logger.info("Первые 5 номеров направлений в базе:", existing_numbers)
            return jsonify({"status": "success", "message": "Материал не найден", "data": None})
            
        patient_id = result[0]
        
        # Ищем первое исследование пациента в studies (например, по дате)
        cursor.execute("""
            SELECT id
            FROM studies
            WHERE patient_id = %s
            ORDER BY study_date DESC
            LIMIT 1
        """, (patient_id,))
        
        study_result = cursor.fetchone()
        study_id = study_result[0] if study_result else None
        
        logger.info(f"Найден материал: patient_id={patient_id}, study_id={study_id}")
        
        return jsonify({
            "status": "success",
            "message": "Материал найден",
            "data": {
                "patient_id": patient_id,
                "study_id": study_id  # Первое исследование пациента или None, если исследований нет
            }
        })
        
    except Exception as e:
        log_function_error("search_material", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)



@app.route('/api/search_patient', methods=['GET'])
def search_patient():
    try:
        surname = request.args.get('surname')
        firstname = request.args.get('firstname')
        secondname = request.args.get('secondname')
        birthdate = request.args.get('birthdate')
        login_url = 'https://45ecp.is-mis.ru/api/user/Login'
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT login, password 
            FROM ecp45mis 
            LIMIT 1
        """)
        credentials = cursor.fetchone()
        
        api_success = False
        mapped_persons = []
        # Пытаемся использовать внешний API, если есть учетные данные
        if credentials and credentials[0] and credentials[1]:
            # Обрезаем пробелы и проверяем, что значения не пустые
            api_login = str(credentials[0]).strip() if credentials[0] else None
            api_password = str(credentials[1]).strip() if credentials[1] else None
            
            if not api_login or not api_password:
                log_function_error("search_patient", "Логин или пароль пусты в таблице ecp45mis")
            else:
                api_login_params = {
                    'Login': api_login,
                    'Password': api_password
                }
                
                logger.info(f"Поиск пациента: {surname} {firstname} {secondname}, birthdate: {birthdate}")
                logger.info(f"Используется логин из БД: {api_login}, длина пароля: {len(api_password)}")
                
                # Попытка авторизации в API
                try:
                    login_response = requests.get(login_url, params=api_login_params, timeout=(5, 30))
                    logger.info(f"Статус API авторизации: {login_response.status_code}")
                    logger.info(f"Ответ API авторизации: {login_response.text}")

                    if login_response.status_code == 200:
                        try:
                            login_data = login_response.json()
                        except ValueError as e:
                            log_function_error("search_patient", f"Ошибка разбора JSON авторизации: {e}")
                            login_data = {'error_code': 1}

                        if login_data.get('error_code') == 0:
                            # Получаем sess_id из data.sess_id (новая структура) или из верхнего уровня (для обратной совместимости)
                            data = login_data.get('data', {})
                            sess_id = data.get('sess_id') or login_data.get('sess_id')
                            if sess_id:
                                person_url = 'https://45ecp.is-mis.ru/api/Person'
                                search_params = {
                                    'PersonSurName_SurName': surname,
                                    'PersonFirName_FirName': firstname,
                                    'PersonSecName_SecName': secondname,
                                    'sess_id': sess_id
                                }
                                
                                try:
                                    person_response = requests.get(person_url, params=search_params, timeout=(5, 30))
                                    logger.info(f"Статус API поиска: {person_response.status_code}")
                                    logger.info(f"Ответ API поиска: {person_response.text}")

                                    if person_response.status_code == 200:
                                        try:
                                            person_data = person_response.json()
                                        except ValueError as e:
                                            log_function_error("search_patient", f"Ошибка разбора JSON поиска: {e}")
                                            person_data = {'error_code': 1}

                                        if person_data.get('error_code') == 0 and person_data.get('data'):
                                            persons = person_data.get('data', [])
                                            if birthdate:
                                                persons = [p for p in persons if p.get('PersonBirthDay_BirthDay') == birthdate]
                                            
                                            if persons:
                                                mapped_persons = [{
                                                    'surname': p.get('PersonSurName_SurName'),
                                                    'firstname': p.get('PersonFirName_FirName'),
                                                    'patronymic': p.get('PersonSecName_SecName'),
                                                    'birth_date': p.get('PersonBirthDay_BirthDay'),
                                                    'PersonSnils_Snils': p.get('PersonSnils_Snils'),
                                                    'UAddress_Address': p.get('UAddress_Address')
                                                } for p in persons]
                                                
                                                # Дедупликация по ФИО и дате рождения (без учёта регистра)
                                                seen = set()
                                                unique_persons = []
                                                for p in mapped_persons:
                                                    # Приводим к нижнему регистру и убираем пробелы для сравнения
                                                    surname_lower = (p['surname'] or '').strip().lower()
                                                    firstname_lower = (p['firstname'] or '').strip().lower()
                                                    patronymic_lower = (p['patronymic'] or '').strip().lower()
                                                    birth_date_val = (p['birth_date'] or '').strip()
                                                    key = (surname_lower, firstname_lower, patronymic_lower, birth_date_val)
                                                    if key not in seen:
                                                        seen.add(key)
                                                        unique_persons.append(p)
                                                mapped_persons = unique_persons
                                                
                                                logger.info(f"Найдено пациентов через API: {len(mapped_persons)}")
                                                api_success = True
                                except requests.exceptions.Timeout:
                                    log_function_error("search_patient", "Таймаут при поиске в API, переходим к поиску в БД")
                                except requests.exceptions.RequestException as e:
                                    log_function_error("search_patient", f"Ошибка подключения при поиске в API: {e}, переходим к поиску в БД")
                        else:
                            log_function_error("search_patient", "Ошибка авторизации API, переходим к поиску в БД")
                    else:
                        log_function_error("search_patient", f"Ошибка HTTP при авторизации API ({login_response.status_code}), переходим к поиску в БД")
                except requests.exceptions.Timeout:
                    log_function_error("search_patient", "Таймаут при авторизации в API, переходим к поиску в БД")
                except requests.exceptions.RequestException as e:
                    log_function_error("search_patient", f"Ошибка подключения к API: {e}, переходим к поиску в БД")
        else:
            log_function_error("search_patient", "Не найдены учетные данные в таблице ecp45mis, используем поиск в БД")
        
        # Если API успешно вернул результаты, возвращаем их
        if api_success and mapped_persons:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                return_db_connection(conn)
                conn = None  # Помечаем как возвращенное, чтобы не возвращать снова в finally
            return jsonify({"status": "success", "message": f"Найдено {len(mapped_persons)} пациентов", "data": mapped_persons})

        # Поиск в базе данных (если API не сработал или не настроен)
        logger.info("Поиск в локальной базе данных...")
        try:
            search_pattern = f"{surname[:1]}% {firstname[:1]}%"
            if secondname and secondname.strip():
                search_pattern += f" {secondname[:1]}%"

            query = """
                SELECT MIN(id) as id, full_name, birthdate, MIN(snils) as snils, MIN(address) as address
                FROM patients
                WHERE full_name ILIKE %s
            """
            params = [search_pattern]

            if birthdate:
                query += " AND birthdate = %s"
                params.append(birthdate)
            
            query += " GROUP BY full_name, birthdate"

            logger.info(f"Выполняемый запрос: {query} с параметрами {params}")  
            cursor.execute(query, params)
            results = cursor.fetchall()

            if not results:
                logger.info("Пациенты не найдены в базе данных")
                return jsonify({"status": "success", "message": "Пациенты не найдены", "data": []})

            mapped_persons = []
            for row in results:
                patient_id, full_name, birthdate, snils, address = row
                name_parts = full_name.split()
                mapped_persons.append({
                    'surname': name_parts[0] if len(name_parts) > 0 else '',
                    'firstname': name_parts[1] if len(name_parts) > 1 else '',
                    'patronymic': name_parts[2] if len(name_parts) > 2 else '',
                    'birth_date': str(birthdate) if birthdate else '',
                    'PersonSnils_Snils': snils or '',
                    'UAddress_Address': address or ''
                })

            # Дедупликация по ФИО и дате рождения (без учёта регистра)
            seen = set()
            unique_persons = []
            for p in mapped_persons:
                surname_lower = (p['surname'] or '').strip().lower()
                firstname_lower = (p['firstname'] or '').strip().lower()
                patronymic_lower = (p['patronymic'] or '').strip().lower()
                birth_date_val = (p['birth_date'] or '').strip()
                key = (surname_lower, firstname_lower, patronymic_lower, birth_date_val)
                if key not in seen:
                    seen.add(key)
                    unique_persons.append(p)
            mapped_persons = unique_persons

            logger.info(f"Найдено пациентов в базе данных: {len(mapped_persons)}")
            return jsonify({"status": "success", "message": f"Найдено {len(mapped_persons)} пациентов", "data": mapped_persons})

        except Exception as e:
            log_function_error("search_patient_database", e)
            return jsonify({"status": "error", "message": f"Ошибка поиска в базе: {str(e)}"})

    except Exception as e:
        log_function_error("search_patient", e)
        return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/generate_report', methods=['POST'])
def generate_report():
    conn = None
    cursor = None
    try:
        study_type = request.form.get('study_type')
        date_from = request.form.get('date_from')
        date_to = request.form.get('date_to')
        
        # 🔍 Логирование входных параметров
        logger.info(f"🔍 GENERATE_REPORT: study_type={study_type}, date_from={date_from}, date_to={date_to}")
        
        # Валидация входных данных
        if not study_type:
            return jsonify({'status': 'error', 'message': 'Тип отчета не указан'}), 400
        if not date_from or not date_to:
            return jsonify({'status': 'error', 'message': 'Даты начала и окончания периода обязательны'}), 400
        
        # Валидация формата дат
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Неверный формат даты. Используйте YYYY-MM-DD'}), 400
        
        # Проверка, что date_from <= date_to
        if date_from > date_to:
            return jsonify({'status': 'error', 'message': 'Дата начала периода не может быть позже даты окончания'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # =========================================================================
        # ОТЧЕТ: Локализация
        # =========================================================================
        if study_type == 'localization':
            query = sql.SQL("""
                SELECT
                    t3.location as localization,
                    count(*) as count,
                    sum(t1.slides_count) as slides_count,
                    count(t1.urgency_id) FILTER (WHERE t1.urgency_id = 1) AS urgency,
                    count(t2.medical_organization_id) FILTER (WHERE t2.medical_organization_id = %s) AS medical_organization,
                    count(t2.medical_organization_id) FILTER (WHERE t2.medical_organization_id <> %s) AS nemedical_organization,
                    count(t2.histologically_confirmed) FILTER (WHERE t2.histologically_confirmed = TRUE) AS histologically,
                    count(t2.conclusion_matched) FILTER (WHERE t2.conclusion_matched = TRUE) AS conclusion,
                    count(t1.comment) FILTER (WHERE t1.comment = '1') AS comment_dobro,
                    count(t1.comment) FILTER (WHERE t1.comment = '2') AS comment_pog,
                    count(t1.comment) FILTER (WHERE t1.comment = '3') AS comment_zloc,
                    count(t1.comment) FILTER (WHERE t1.comment = '4') AS comment_podozr,
                    count(t1.comment) FILTER (WHERE t1.comment = '5') AS comment_displ,
                    count(t1.comment) FILTER (WHERE t1.comment = '6') AS comment_giper,
                    count(t1.comment) FILTER (WHERE t1.comment = '7') AS comment_proch,
                    count(t1.comment) FILTER (WHERE t1.comment = '8') AS comment_bez_osob,
                    count(t1.comment) FILTER (WHERE t1.comment = '9') AS comment_material
                FROM
                    (SELECT * FROM studies WHERE study_date::DATE BETWEEN %s AND %s) AS t1
                LEFT JOIN
                    (SELECT id, localization_id, medical_organization_id, histologically_confirmed, conclusion_matched FROM materials) AS t2
                    ON t1.material_id = t2.id
                LEFT JOIN
                    (SELECT * FROM loc) AS t3
                    ON t2.localization_id = t3.id
                GROUP BY t3.location
                ORDER BY t3.location
            """)
            
            params = [MEDICAL_ORGANIZATION_ID, MEDICAL_ORGANIZATION_ID, date_from, date_to]
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            data = []
            for row in results:
                data.append({
                    'localization': row[0],
                    'count': row[1],
                    'slides_count': row[2],
                    'urgency': row[3],
                    'medical_organization': row[4],
                    'nemedical_organization': row[5],
                    'histologically': row[6],
                    'conclusion': row[7],
                    'comment_dobro': row[8],
                    'comment_pog': row[9],
                    'comment_zloc': row[10],
                    'comment_podozr': row[11],
                    'comment_displ': row[12],
                    'comment_giper': row[13],
                    'comment_proch': row[14],
                    'comment_bez_osob': row[15],
                    'comment_material': row[16]
                })
            
            logger.info(f"🔍 LOCALIZATION: найдено строк={len(data)}")
            return jsonify({'status': 'success', 'data': data})
        
        # =========================================================================
        # ОТЧЕТ: Цитология (с исправлением list index out of range)
        # =========================================================================
        elif study_type == 'cytology':
            query = sql.SQL("""
                SELECT
                    t3.name_service,
                    count(t2.department_id) FILTER (WHERE t2.department_id = '1' AND t2.medical_organization_id = %s) AS polyclinic,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS endoscopic,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS radiology,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS dayChemotherapy,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS surgical,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS abdominal,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS chemotherapy,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS thoracic,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS gynecology,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS breastSkin,
                    count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) AS tumors,
                    (
                        count(t2.department_id) FILTER (WHERE t2.department_id = '1' AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s) +
                        count(t2.department_id) FILTER (WHERE t2.department_id = %s AND t2.medical_organization_id = %s)
                    ) AS koodTotal,
                    count(t2.department_id) FILTER (WHERE t2.department_id = '1' AND t2.medical_organization_id <> %s) AS otherPolyclinic,
                    count(t2.department_id) FILTER (WHERE t2.department_id = '3' AND t2.medical_organization_id <> %s) AS otherStationary,
                    count(t2.department_id) FILTER (WHERE t2.department_id = '1') AS polyclinicTotal
                FROM
                    (SELECT * FROM studies WHERE study_date::DATE BETWEEN %s AND %s) AS t1
                LEFT JOIN
                    (SELECT id, medical_organization_id, department_id FROM materials) AS t2
                    ON t1.material_id = t2.id
                LEFT JOIN
                    (SELECT id, name_service FROM service) AS t3
                    ON t1.service_id = t3.id
                GROUP BY t3.id, t3.name_service
                ORDER BY t3.name_service
            """)
            
            params = [
                MEDICAL_ORGANIZATION_ID,                     # polyclinic ('1')

                SUBDEPARTMENT_IDS['endoscopic'], MEDICAL_ORGANIZATION_ID,        # '1-13'
                SUBDEPARTMENT_IDS['radiology'], MEDICAL_ORGANIZATION_ID,         # '1-12'
                SUBDEPARTMENT_IDS['day_chemotherapy'], MEDICAL_ORGANIZATION_ID,  # '1-11'
                SUBDEPARTMENT_IDS['surgical'], MEDICAL_ORGANIZATION_ID,          # '1-10'
                SUBDEPARTMENT_IDS['abdominal'], MEDICAL_ORGANIZATION_ID,         # '1-9'
                SUBDEPARTMENT_IDS['chemotherapy'], MEDICAL_ORGANIZATION_ID,      # '1-8'
                SUBDEPARTMENT_IDS['thoracic'], MEDICAL_ORGANIZATION_ID,          # '1-7'
                SUBDEPARTMENT_IDS['gynecology'], MEDICAL_ORGANIZATION_ID,        # '1-6'
                SUBDEPARTMENT_IDS['breast_skin'], MEDICAL_ORGANIZATION_ID,       # '1-5'
                SUBDEPARTMENT_IDS['tumors'], MEDICAL_ORGANIZATION_ID,            # '1-4'

                # koodTotal (повтор тех же 11 фильтров)
                MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['endoscopic'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['radiology'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['day_chemotherapy'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['surgical'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['abdominal'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['chemotherapy'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['thoracic'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['gynecology'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['breast_skin'], MEDICAL_ORGANIZATION_ID,
                SUBDEPARTMENT_IDS['tumors'], MEDICAL_ORGANIZATION_ID,

                # otherPolyclinic, otherStationary
                MEDICAL_ORGANIZATION_ID,
                MEDICAL_ORGANIZATION_ID,

                # date_from, date_to
                date_from,
                date_to
            ]

            sql_text = query.as_string(cursor)
            full_sql = cursor.mogrify(sql_text, params).decode('utf-8')
            logger.info("FINAL SQL:\n" + full_sql)
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall()
            
            logger.info(f" CYTOLOGY: найдено строк={len(results)}, колонок={len(columns)}")
            
            data = []
            for row in results:
                data.append({
                    'service': row[0],
                    'kood': {
                        'polyclinic': row[1],
                        'endoscopic': row[2],
                        'radiology': row[3],
                        'dayChemotherapy': row[4],
                        'surgical': row[5],
                        'abdominal': row[6],
                        'chemotherapy': row[7],
                        'thoracic': row[8],
                        'gynecology': row[9],
                        'breastSkin': row[10],
                        'tumors': row[11],
                        'total': row[12]
                    },
                    'otherLpu': {
                        'polyclinic': row[13],
                        'stationary': row[14]
                    },
                    'polyclinicTotal': row[15]
                })
            
            return jsonify({'status': 'success', 'data': data})
        
        # =========================================================================
        # ОТЧЕТ: Журнал расхождений (гистология)
        # =========================================================================
        elif study_type == 'histology_journal':
            query = sql.SQL("""
                SELECT
                    p.id AS patient_id,
                    COALESCE(p.ambulatory_card_number, '') AS ambulatory_card_number,
                    cc.code_si AS number,
                    COALESCE(cc.name_code_si, '') AS cytology_conclusion_name,
                    COALESCE(loc.location, '') AS localization,
                    COALESCE(g.gist_name, '') AS histology_name
                FROM
                    (SELECT * FROM studies WHERE study_date::DATE BETWEEN %s AND %s) AS s
                LEFT JOIN materials m ON s.material_id = m.id
                LEFT JOIN patients p ON p.id = s.patient_id
                LEFT JOIN code_cytology cc ON TRIM(m.ciphers_id) = cc.code_si
                LEFT JOIN loc ON m.localization_id = loc.id
                LEFT JOIN gistolog g ON CAST(NULLIF(TRIM(m.gisolog_comment), '') AS INTEGER) = g.id
                WHERE
                    m.histologically_confirmed = TRUE
                    AND m.conclusion_matched = FALSE
                ORDER BY p.id, cc.code_si
            """)
            
            cursor.execute(query, (date_from, date_to))
            results = cursor.fetchall()
            
            data = []
            for row in results:
                data.append({
                    'patient_id': row[0],
                    'ambulatory_card_number': row[1],
                    'number': row[2],
                    'cytology_conclusion_name': row[3],
                    'localization': row[4],
                    'histology_name': row[5]
                })
            
            logger.info(f"🔍 HISTOLOGY_JOURNAL: найдено строк={len(data)}")
            return jsonify({'status': 'success', 'data': data})
        
        # =========================================================================
        # ОТЧЕТЫ: Профосмотры (общий, жидкостная, традиционная) - ЕДИНАЯ ФУНКЦИЯ
        # =========================================================================
                # =========================================================================
        # ОТЧЕТЫ: Профосмотры (общий, жидкостная, традиционная)
        # =========================================================================
        elif study_type in ['profosmotr', 'profosmotr_liquid', 'profosmotr_traditional']:
            prof_filter = request.form.get('profosmotr_prof')
            
            logger.info(f"PROFOSMOTR: study_type={study_type}, date_from={date_from}, date_to={date_to}")
            
            # Фильтр по датам (ОБЯЗАТЕЛЬНО ::DATE для VARCHAR поля)
            base_where = sql.SQL("(p.data_reg::DATE BETWEEN %s AND %s)")
            
            # Фильтр по типу исследования
            if study_type == 'profosmotr_liquid':
                base_where += sql.SQL(" AND LOWER(TRIM(p.liquid_prof)) = 'true'")
            elif study_type == 'profosmotr_traditional':
                base_where += sql.SQL(" AND LOWER(TRIM(p.traditional_prof)) = 'true'")
            
            # Опциональный фильтр по подтипу
            if prof_filter:
                base_where += sql.SQL(" AND p.profosmotr_prof = %s")
            
            # Условия для регионов
            kurgan_condition = sql.SQL("o.region_id::text = %s AND o.region_name = %s")
            region_condition = sql.SQL("o.region_id::text = %s")
            
            # Формируем запрос с FILTER для ВСЕХ агрегатов
            query = sql.SQL("""
                -- Основные данные по организациям
                SELECT
                    COALESCE(o.name_short, l.name) AS "Лечебные учреждения",
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}) AS "Стекол",
                    SUM(CAST(p.pathologies_prof AS INTEGER)) FILTER (WHERE {type_filter}) AS "Патологий_врачами",
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}) AS "Патологий_лаборантами",
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.liquid_prof)) = 'true') AS "Жидкостная",
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.traditional_prof)) = 'true') AS "Традиционная",
                    SUM(COALESCE(CAST(p.nilm_tabl_doctot AS INTEGER),0) + COALESCE(CAST(p.nilm_tabl_lab AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "NILM",
                    SUM(COALESCE(CAST(p.ascus_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "ASCUS",
                    SUM(COALESCE(CAST(p.asc_h_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "ASC-H",
                    SUM(COALESCE(CAST(p.cin_i_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "CIN I",
                    SUM(COALESCE(CAST(p.cin_ii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "CIN II",
                    SUM(COALESCE(CAST(p.cin_iii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "CIN III",
                    SUM(COALESCE(CAST(p.suspicion_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Подозр. на рак",
                    SUM(COALESCE(CAST(p.cr_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Cr(ccs)",
                    SUM(COALESCE(CAST(p.sgc_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Ат. кл. хл. эп. ан (AGC)",
                    SUM(COALESCE(CAST(p.cuspicion_tumor_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Подозр. на опух.",
                    SUM(COALESCE(CAST(p.adenocarcinoma_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Аденокарцинома",
                    SUM(COALESCE(CAST(p.others_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "Прочие",
                    SUM(COALESCE(CAST(p.hpv AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "воспаление+HPV",
                    SUM(COALESCE(CAST(p.lsil_hpv AS INTEGER),0)) FILTER (WHERE {type_filter}) AS "LSIL+HPV"
                FROM
                    profosmotr p
                LEFT JOIN organ o ON p.lpu_prof = o.id::text
                LEFT JOIN lpu l ON p.lpu_prof = l.id::text
                WHERE {base_where}
                GROUP BY COALESCE(o.name_short, l.name)
                
                UNION ALL
                
                -- Итого по Кургану
                SELECT
                    'Итого по Кургану' AS "Лечебные учреждения",
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(CAST(p.pathologies_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.liquid_prof)) = 'true'),
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.traditional_prof)) = 'true'),
                    SUM(COALESCE(CAST(p.nilm_tabl_doctot AS INTEGER),0) + COALESCE(CAST(p.nilm_tabl_lab AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.ascus_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.asc_h_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_i_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_ii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_iii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.suspicion_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cr_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.sgc_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cuspicion_tumor_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.adenocarcinoma_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.others_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.hpv AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.lsil_hpv AS INTEGER),0)) FILTER (WHERE {type_filter})
                FROM
                    profosmotr p
                LEFT JOIN organ o ON p.lpu_prof = o.id::text
                LEFT JOIN lpu l ON p.lpu_prof = l.id::text
                WHERE {kurgan_condition} AND {base_where}
                
                UNION ALL
                
                -- Итого по Курганской области
                SELECT
                    'Итого по Курганской области' AS "Лечебные учреждения",
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(CAST(p.pathologies_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(CAST(p.steclo_prof AS INTEGER)) FILTER (WHERE {type_filter}),
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.liquid_prof)) = 'true'),
                    SUM(1) FILTER (WHERE {type_filter} AND LOWER(TRIM(p.traditional_prof)) = 'true'),
                    SUM(COALESCE(CAST(p.nilm_tabl_doctot AS INTEGER),0) + COALESCE(CAST(p.nilm_tabl_lab AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.ascus_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.asc_h_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_i_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_ii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cin_iii_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.suspicion_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cr_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.sgc_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.cuspicion_tumor_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.adenocarcinoma_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.others_tabl_doctot AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.hpv AS INTEGER),0)) FILTER (WHERE {type_filter}),
                    SUM(COALESCE(CAST(p.lsil_hpv AS INTEGER),0)) FILTER (WHERE {type_filter})
                FROM
                    profosmotr p
                LEFT JOIN organ o ON p.lpu_prof = o.id::text
                LEFT JOIN lpu l ON p.lpu_prof = l.id::text
                WHERE {region_condition} AND {base_where}
                
                ORDER BY "Лечебные учреждения"
            """).format(
                base_where=base_where,
                kurgan_condition=kurgan_condition,
                region_condition=region_condition,
                type_filter=sql.SQL("TRUE")  # FILTER уже применён в WHERE, здесь просто TRUE
            )
            
            # Формирование параметров
            if prof_filter:
                params = [
                    date_from, date_to, prof_filter,
                    REGION_ID, REGION_NAME, date_from, date_to, prof_filter,
                    REGION_ID, date_from, date_to, prof_filter
                ]
            else:
                params = [
                    date_from, date_to,
                    REGION_ID, REGION_NAME, date_from, date_to,
                    REGION_ID, date_from, date_to
                ]
            
            logger.info(f"PROFOSMOTR: params count={len(params)}")
            
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall()
            
            logger.info(f"PROFOSMOTR: найдено строк={len(results)}")
            
            # Отладка: если пусто, проверяем без фильтра
            if len(results) == 0:
                test_query = sql.SQL("""
                    SELECT COUNT(*) FROM profosmotr p
                    WHERE p.data_reg::DATE BETWEEN %s AND %s
                """)
                if study_type == 'profosmotr_liquid':
                    test_query += sql.SQL(" AND LOWER(TRIM(p.liquid_prof)) = 'true'")
                elif study_type == 'profosmotr_traditional':
                    test_query += sql.SQL(" AND LOWER(TRIM(p.traditional_prof)) = 'true'")
                
                cursor.execute(test_query, [date_from, date_to])
                test_count = cursor.fetchone()[0]
                logger.warning(f"PROFOSMOTR: пустой результат! Всего записей в БД за период: {test_count}")
            
            data = [dict(zip(columns, row)) for row in results]
            return jsonify({'status': 'success', 'data': data})
        # =========================================================================
        # НЕИЗВЕСТНЫЙ ТИП ОТЧЕТА
        # =========================================================================
        else:
            return jsonify({'status': 'error', 'message': 'Неизвестный тип отчета'}), 400
    
    except Exception as e:
        log_function_error("generate_report", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_localization_data', methods=['GET'])
def get_localization_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, location FROM loc ORDER BY location")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_code_cytology_data', methods=['GET'])
def get_code_cytology_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT code_si, name_code_si FROM code_cytology ORDER BY code_si")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": f"{row[0]} - {row[1]}"} for row in results]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_department_data', methods=['GET'])
def get_department_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Используем DISTINCT ON для получения уникальных отделений и фильтруем только целочисленные ID
        cursor.execute("""
            SELECT DISTINCT ON (department) id, department 
            FROM otdel 
            WHERE department IS NOT NULL 
            ORDER BY department, id
        """)
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        logger.info(f"Загружено {len(data)} уникальных отделений")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_department_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_subdepartment_data', methods=['GET'])
def get_subdepartment_data():
    try:
        department_id = request.args.get('department_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if department_id:
            # Если указано отделение, получаем только подотделения для него
            cursor.execute("""
                SELECT id, department
                FROM otdel
                WHERE department IS NOT NULL
                  AND id ~ '^[0-9]+-[0-9]+$'
                  AND SPLIT_PART(id, '-', 1) = %s
                ORDER BY CAST(SPLIT_PART(id, '-', 1) AS INTEGER)
            """, (str(department_id),))
        else:
            cursor.execute("""
                SELECT id, department
                FROM otdel
                WHERE department IS NOT NULL
                  AND id ~ '^[0-9]+-[0-9]+$'
                  AND SPLIT_PART(id, '-', 1) = SPLIT_PART(id, '-', 2)
                ORDER BY CAST(SPLIT_PART(id, '-', 1) AS INTEGER)
            """)
            
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1].strip()} for row in results]
        logger.info(f"Загружено {len(data)} подотделений")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_subdepartment_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/search_referring_doctors', methods=['GET'])
def search_referring_doctors():
    try:
        query = request.args.get('query', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if query:
            cursor.execute("""
                SELECT id, doctor_napravitel 
                FROM docnaprav 
                WHERE doctor_napravitel ILIKE %s 
                ORDER BY doctor_napravitel
                LIMIT 10
            """, (f"%{query}%",))
        else:
            cursor.execute("""
                SELECT id, doctor_napravitel 
                FROM docnaprav 
                ORDER BY doctor_napravitel
                LIMIT 10
            """)
        
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("search_referring_doctors", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/add_referring_doctor', methods=['POST'])
def add_referring_doctor():
    try:
        data = request.get_json()
        full_name = data.get('name')
        
        if not full_name:
            return jsonify({"status": "error", "message": "Имя врача обязательно"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли уже такой врач
        cursor.execute("SELECT id FROM docnaprav WHERE doctor_napravitel = %s", (full_name,))
        existing = cursor.fetchone()
        
        if existing:
            return jsonify({"status": "success", "id": existing[0], "name": full_name, "message": "Врач уже существует"})
        
        # Добавляем нового врача
        cursor.execute("""
            INSERT INTO docnaprav (doctor_napravitel) 
            VALUES (%s) 
            RETURNING id
        """, (full_name,))
        new_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({"status": "success", "id": new_id, "name": full_name, "message": "Врач успешно добавлен"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("add_referring_doctor", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_referring_doctors', methods=['GET'])
def get_referring_doctors():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем данные из таблицы docnaprav
        cursor.execute("""
            SELECT DISTINCT id, doctor_napravitel as name
            FROM docnaprav 
            WHERE doctor_napravitel IS NOT NULL 
            ORDER BY doctor_napravitel
        """)
        
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_referring_doctors", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_lpu_data', methods=['GET'])
def get_lpu_data():
    """Получить список ЦРБ из таблицы lpu с полями name и region"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, region
            FROM lpu
            ORDER BY region, name
        """)
        rows = cursor.fetchall()
        data = []
        for row in rows:
            data.append({
                'id': row[0],
                'name': row[1] or '',
                'region': row[2] or ''
            })
        return jsonify(data)
    except Exception as e:
        log_function_error("get_lpu_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_raion_data', methods=['GET'])
def get_raion_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.name_raion, r.type 
            FROM raion r 
            ORDER BY r.name_raion
        """)
        results = cursor.fetchall()
        data = [{"id": row[0], "name": f"{row[1]} ({row[2]})"} for row in results]
        logger.info(f"Загружено {len(data)} районов")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_district_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)


@app.route('/api/save_profosmotr_lpu', methods=['POST'])
def save_profosmotr_lpu():
    conn = None
    cursor = None
    try:
        # Получаем параметры из формы
        lpu_id = request.form.get('lpu_id')
        lpu_source = request.form.get('lpu_source')  # 'lpu' или 'organ'
        date_value = request.form.get('date')
        doctor_prof = request.form.get('doctor_prof')
        laborant_prof = request.form.get('laborant_prof')
        profosmotr_prof = request.form.get('profosmotr_prof')
        steclo_prof = request.form.get('steclo_prof')
        pathologies_prof = request.form.get('pathologies_prof')
        liquid_prof = request.form.get('liquid_prof')
        traditional_prof = request.form.get('traditional_prof')
        nilm_tabl_doctot = request.form.get('nilm_tabl_doctot')
        ascus_tabl_doctot = request.form.get('ascus_tabl_doctot')
        asc_h_tabl_doctot = request.form.get('asc_h_tabl_doctot')
        cin_i_tabl_doctot = request.form.get('cin_i_tabl_doctot')
        cin_ii_tabl_doctot = request.form.get('cin_ii_tabl_doctot')
        cin_iii_tabl_doctot = request.form.get('cin_iii_tabl_doctot')
        suspicion_tabl_doctot = request.form.get('suspicion_tabl_doctot')
        cr_tabl_doctot = request.form.get('cr_tabl_doctot')
        sgc_tabl_doctot = request.form.get('sgc_tabl_doctot')
        cuspicion_tumor_tabl_doctot = request.form.get('cuspicion_tumor_tabl_doctot')
        adenocarcinoma_tabl_doctot = request.form.get('adenocarcinoma_tabl_doctot')
        others_tabl_doctot = request.form.get('others_tabl_doctot')
        nilm_tabl_lab = request.form.get('nilm_tabl_lab')
        hpv = request.form.get('hpv')
        lsil_hpv = request.form.get('lsil_hpv')
        profosmotr_id = request.form.get('profosmotr_id')
        
        # Обрабатываем null значения
        def clean_value(value):
            if value is None or value == '' or value == 'null' or value == 'undefined' or value == 'None':
                return None
            return value
        
        # Очищаем все значения
        lpu_id = clean_value(lpu_id)
        lpu_source = clean_value(lpu_source)
        date_value = clean_value(date_value)
        doctor_prof = clean_value(doctor_prof)
        laborant_prof = clean_value(laborant_prof)
        profosmotr_prof = clean_value(profosmotr_prof)
        steclo_prof = clean_value(steclo_prof)
        pathologies_prof = clean_value(pathologies_prof)
        liquid_prof = clean_value(liquid_prof)
        traditional_prof = clean_value(traditional_prof)
        nilm_tabl_doctot = clean_value(nilm_tabl_doctot)
        ascus_tabl_doctot = clean_value(ascus_tabl_doctot)
        asc_h_tabl_doctot = clean_value(asc_h_tabl_doctot)
        cin_i_tabl_doctot = clean_value(cin_i_tabl_doctot)
        cin_ii_tabl_doctot = clean_value(cin_ii_tabl_doctot)
        cin_iii_tabl_doctot = clean_value(cin_iii_tabl_doctot)
        suspicion_tabl_doctot = clean_value(suspicion_tabl_doctot)
        cr_tabl_doctot = clean_value(cr_tabl_doctot)
        sgc_tabl_doctot = clean_value(sgc_tabl_doctot)
        cuspicion_tumor_tabl_doctot = clean_value(cuspicion_tumor_tabl_doctot)
        adenocarcinoma_tabl_doctot = clean_value(adenocarcinoma_tabl_doctot)
        others_tabl_doctot = clean_value(others_tabl_doctot)
        nilm_tabl_lab = clean_value(nilm_tabl_lab)
        hpv = clean_value(hpv)
        lsil_hpv = clean_value(lsil_hpv)
        profosmotr_id = clean_value(profosmotr_id)
        
        # Отладочная информация
        logger.info(f"profosmotr_id: {profosmotr_id}, type: {type(profosmotr_id)}")
        logger.info(f"lpu_id: {lpu_id}, type: {type(lpu_id)}, source: {lpu_source}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Определяем значение для lpu_prof
        # Если источник - таблица lpu, то используем lpu_id напрямую
        # Если источник - таблица organ, то нужно найти соответствующий ID в таблице lpu
        lpu_prof_value = lpu_id
        if lpu_source == 'organ' and lpu_id:
            # Если выбран из таблицы organ, пытаемся найти соответствующий ID в таблице lpu
            # Предполагаем, что может быть связь через какое-то поле или просто используем lpu_id как есть
            # Если нужно найти соответствие, можно добавить JOIN запрос
            # Пока оставляем как есть, если нужно будет найти соответствие - добавим запрос
            pass
        elif lpu_source == 'lpu' and lpu_id:
            # Если выбран из таблицы lpu, используем ID напрямую
            lpu_prof_value = lpu_id
        
        # Создаем словарь с параметрами для удобства
        params = {
            'lpu_prof': lpu_prof_value,
            'data_reg': date_value,
            'doctor_prof': doctor_prof,
            'laborant_prof': laborant_prof,
            'profosmotr_prof': profosmotr_prof,
            'steclo_prof': steclo_prof,
            'pathologies_prof': pathologies_prof,
            'liquid_prof': liquid_prof,
            'traditional_prof': traditional_prof,
            'nilm_tabl_doctot': nilm_tabl_doctot,
            'ascus_tabl_doctot': ascus_tabl_doctot,
            'asc_h_tabl_doctot': asc_h_tabl_doctot,
            'cin_i_tabl_doctot': cin_i_tabl_doctot,
            'cin_ii_tabl_doctot': cin_ii_tabl_doctot,
            'cin_iii_tabl_doctot': cin_iii_tabl_doctot,
            'suspicion_tabl_doctot': suspicion_tabl_doctot,
            'cr_tabl_doctot': cr_tabl_doctot,
            'sgc_tabl_doctot': sgc_tabl_doctot,
            'cuspicion_tumor_tabl_doctot': cuspicion_tumor_tabl_doctot,
            'adenocarcinoma_tabl_doctot': adenocarcinoma_tabl_doctot,
            'others_tabl_doctot': others_tabl_doctot,
            'nilm_tabl_lab': nilm_tabl_lab,
            'hpv': hpv,
            'lsil_hpv': lsil_hpv
        }
        
        if profosmotr_id:
            # UPDATE - добавляем update_reg
            params['update_reg'] = date.today().isoformat()
            # Безопасное построение запроса с использованием psycopg2.sql
            update_fields = [k for k in params.keys() if k != 'profosmotr_id']
            set_parts = sql.SQL(', ').join(
                sql.Identifier(k) + sql.SQL(' = %s') for k in update_fields
            )
            query = sql.SQL("UPDATE profosmotr SET {} WHERE id = %s").format(set_parts)
            values = [params[k] for k in update_fields]
            values.append(profosmotr_id)
            logger.debug(f"UPDATE query: {query.as_string(conn)}")
            logger.debug(f"UPDATE values count: {len(values)}")
            cursor.execute(query, values)
            conn.commit()
            return jsonify({"status": "success"})
        else:
            # INSERT - добавляем update_reg для новых записей
            params['update_reg'] = date.today().isoformat()
            # Безопасное построение запроса с использованием psycopg2.sql
            columns = list(params.keys())
            identifiers = sql.SQL(', ').join(sql.Identifier(k) for k in columns)
            placeholders = sql.SQL(', ').join([sql.Placeholder()] * len(columns))
            query = sql.SQL("INSERT INTO profosmotr ({}) VALUES ({})").format(identifiers, placeholders)
            values = list(params.values())
            logger.debug(f"INSERT query: {query.as_string(conn)}")
            logger.debug(f"INSERT values count: {len(values)}")
            cursor.execute(query, values)
            conn.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("save_profosmotr", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_physicians', methods=['GET'])
def get_physicians():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, doctor_laboratory FROM physician ORDER BY doctor_laboratory")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        cursor.close()
        return_db_connection(conn)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_physicians", e)
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_physician_name_by_id', methods=['GET'])
def get_physician_name_by_id():
    """Получить имя врача по его ID из таблицы physician"""
    try:
        physician_id = request.args.get('physician_id')
        if not physician_id:
            return jsonify({"status": "error", "message": "ID врача не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT doctor_laboratory FROM physician WHERE id = %s", (physician_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Врач с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_physician_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_physician_names_batch', methods=['POST'])
def get_physician_names_batch():
    """Получить имена врачей по списку ID (batch запрос для оптимизации)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        physician_ids = data.get('physician_ids', [])
        
        if not physician_ids or not isinstance(physician_ids, list):
            return jsonify({"status": "error", "message": "Список ID врачей не указан или неверный формат"})
        
        # Убираем дубликаты и пустые значения
        physician_ids = [str(id) for id in set(physician_ids) if id and str(id).strip() and str(id) != 'null']
        
        if not physician_ids:
            return jsonify({"status": "success", "data": {}})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Загружаем все имена одним запросом
        placeholders = ','.join(['%s'] * len(physician_ids))
        cursor.execute(f"""
            SELECT id, doctor_laboratory 
            FROM physician 
            WHERE id IN ({placeholders})
        """, physician_ids)
        
        results = cursor.fetchall()
        # Создаем словарь id -> name
        names_map = {str(row[0]): row[1] for row in results}
        
        logger.debug(f"Загружено {len(names_map)} имен врачей для {len(physician_ids)} ID")
        return jsonify({"status": "success", "data": names_map})
    except Exception as e:
        log_function_error("get_physician_names_batch", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_physician_initials_by_id', methods=['GET'])
def get_physician_initials_by_id():
    """Получить фамилию с инициалами врача по его ID из таблицы physician"""
    try:
        physician_id = request.args.get('physician_id')
        if not physician_id:
            return jsonify({"status": "error", "message": "ID врача не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT doctor_laboratory FROM physician WHERE id = %s", (physician_id,))
        result = cursor.fetchone()
        
        if result:
            full_name = result[0]
            # Разбиваем полное имя на части
            name_parts = full_name.strip().split()
            
            if len(name_parts) >= 3:
                # Фамилия И.О.
                surname = name_parts[0]
                first_initial = name_parts[1][0] + "." if len(name_parts[1]) > 0 else ""
                middle_initial = name_parts[2][0] + "." if len(name_parts[2]) > 0 else ""
                initials = f"{surname} {first_initial}{middle_initial}"
            elif len(name_parts) == 2:
                # Фамилия И.
                surname = name_parts[0]
                first_initial = name_parts[1][0] + "." if len(name_parts[1]) > 0 else ""
                initials = f"{surname} {first_initial}"
            else:
                # Только фамилия или одно слово
                initials = full_name
            
            return jsonify({"status": "success", "initials": initials})
        else:
            return jsonify({"status": "error", "message": "Врач с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_physician_initials_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_lab_technicians', methods=['GET'])
def get_lab_technicians():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, doctor_laboratory FROM physician WHERE post = 'лаборант' ORDER BY doctor_laboratory")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        cursor.close()
        return_db_connection(conn)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_lab_technicians", e)
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_doctors', methods=['GET'])
def get_doctors():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, doctor_laboratory FROM physician WHERE post = 'врач' ORDER BY doctor_laboratory")
        results = cursor.fetchall()
        data = [{"id": row[0], "full_name": row[1]} for row in results]
        cursor.close()
        return_db_connection(conn)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_doctors", e)
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_profosmotr_data', methods=['GET'])
def get_profosmotr_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, data_reg, update_reg 
            FROM profosmotr 
            ORDER BY id DESC
        """)
        # Сортировка по ID DESC обеспечивает отображение самых новых записей первыми
        # (ID обычно автоинкрементный и отражает порядок создания)
        results = cursor.fetchall()
        logger.info(f"Загружено {len(results)} записей профосмотра")
        data = []
        for row in results:
            id_val = row[0]
            date_val = row[1]
            update_reg_val = row[2]
            date_str = ""
            if date_val:
                # Если это строка, пробуем преобразовать
                if isinstance(date_val, str):
                    try:
                        # Обрезаем время, если оно есть
                        date_obj = datetime.strptime(date_val[:10], "%Y-%m-%d")
                        date_str = date_obj.strftime("%d-%m-%Y")
                    except Exception:
                        date_str = date_val  # fallback: просто строка
                else:
                    # Если это объект даты
                    date_str = date_val.strftime("%d-%m-%Y")
            data.append({"id": id_val, "date": date_str})
            logger.info(f"ID: {id_val}, Date: {date_str}, Update_reg: {update_reg_val}")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_profosmotr_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/delete_profosmotr', methods=['POST'])
def delete_profosmotr():
    """Удаление записи из таблицы profosmotr по id"""
    conn = None
    cursor = None
    try:
        profosmotr_id = request.form.get('profosmotr_id')
        if not profosmotr_id:
            return jsonify({"status": "error", "message": "Не указан profosmotr_id"})
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profosmotr WHERE id = %s", (profosmotr_id,))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Удалён профосмотр id={profosmotr_id}")
            return jsonify({"status": "success", "message": "Запись удалена"})
        return jsonify({"status": "error", "message": "Запись не найдена"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("delete_profosmotr", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_profosmotr_row_data', methods=['GET'])
def get_profosmotr_row_data():
    conn = None
    cursor = None
    try:
        row_id = request.args.get('row_id')
        if not row_id:
            return jsonify({"status": "error", "message": "Не указан row_id"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование таблицы lpu перед использованием
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'lpu'
            )
        """)
        lpu_table_exists = cursor.fetchone()[0]
        
        if lpu_table_exists:
            cursor.execute("""
                SELECT p.*, 
                       o.name_short as lpu_name_organ,
                       l.name as lpu_name_lpu,
                       l.region as lpu_region
                FROM profosmotr p
                LEFT JOIN organ o ON p.lpu_prof = o.id::text
                LEFT JOIN lpu l ON p.lpu_prof = l.id::text
                WHERE p.id = %s
                LIMIT 1
            """, (row_id,))
        else:
            # Если таблица lpu не существует, используем только organ
            cursor.execute("""
                SELECT p.*, 
                       o.name_short as lpu_name_organ,
                       NULL as lpu_name_lpu,
                       NULL as lpu_region
                FROM profosmotr p
                LEFT JOIN organ o ON p.lpu_prof = o.id::text
                WHERE p.id = %s
                LIMIT 1
            """, (row_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Данные не найдены"})
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        
        # Определяем, из какой таблицы пришло значение lpu_prof
        lpu_source = None
        lpu_name = None
        if data.get('lpu_name_organ'):
            lpu_source = 'organ'
            lpu_name = data.get('lpu_name_organ')
        elif data.get('lpu_name_lpu'):
            lpu_source = 'lpu'
            lpu_name = data.get('lpu_name_lpu')
            if data.get('lpu_region'):
                lpu_name = f"{lpu_name} ({data.get('lpu_region')})"
        
        cytologist_map = [
            ('nilm_tabl_doctot', 'nilm_tabl_lab', 'NILM'),
            ('ascus_tabl_doctot', None, 'ASCUS'),
            ('asc_h_tabl_doctot', None, 'ASC-H'),
            ('cin_i_tabl_doctot', None, 'CIN I'),
            ('cin_ii_tabl_doctot', None, 'CIN II'),
            ('cin_iii_tabl_doctot', None, 'CIN III'),
            ('suspicion_tabl_doctot', None, 'Подозр. на рак'),
            ('cr_tabl_doctot', None, 'Cr(ccs)'),
            ('sgc_tabl_doctot', None, 'Ат. кл. хл. эп. ан (AGC)'),
            ('cuspicion_tumor_tabl_doctot', None, 'AGC(fn.)'),
            ('adenocarcinoma_tabl_doctot', None, 'AgCa'),
            ('others_tabl_doctot', None, 'Прочие'),
            ('hpv', None, 'воспаление+HPV'),
            ('lsil_hpv', None, 'LSIL+HPV'),
        ]
        right_table = []
        for doct, lab, cyt in cytologist_map:
            right_table.append({
                'cytologist': cyt,
                'doctorLab': data.get(doct, ''),
                'lab': data.get(lab, '') if lab else '',
                'conclusion': ''
            })
        return jsonify({
            "status": "success",
            "data": right_table,
            "raw": data,  # data содержит lpu_prof, doctor_prof, laborant_prof и т.д.
            "lpu_name": lpu_name or "",
            "lpu_source": lpu_source  # 'organ' или 'lpu'
        })
    except Exception as e:
        log_function_error("get_profosmotr_row_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/check_admin_auth', methods=['GET'])
def check_admin_auth():
    """Check if the current user is an admin"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the current user is an admin
        cursor.execute("""
            SELECT is_admin 
            FROM "user" 
            WHERE login = %s
        """, ('Ozerov',))  # Replace with actual current user login
        
        result = cursor.fetchone()
        return jsonify({"is_admin": result[0] if result else False})
    except Exception as e:
        log_function_error("check_admin_auth", e)
        return jsonify({"is_admin": False})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_all_users', methods=['GET'])
def get_all_users():
    """Get all users from the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, login, fio_name, password_hash, password, status, failed_attempts, lock_until 
            FROM "user" 
            ORDER BY login
        """)
        
        results = cursor.fetchall()
        users = [
            {
                "id": row[0],
                "login": row[1],
                "fio_name": row[2],
                "password": row[3],  # hash (для обратной совместимости)
                "password_hash": row[3],
                "password_plain": row[4],
                "status": row[5] if row[5] else 'user',
                "failed_attempts": row[6] or 0,
                "lock_until": str(row[7]) if row[7] else None
            }
            for row in results
        ]
        
        return jsonify({"status": "success", "data": users})
    except Exception as e:
        log_function_error("get_all_users", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_user', methods=['GET'])
def get_user():
    """Get a specific user by ID"""
    try:
        user_id = request.args.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Преобразуем user_id в строку, так как в базе данных id хранится как varchar
        cursor.execute("""
            SELECT id, login, fio_name, password_hash, password, status, failed_attempts, lock_until 
            FROM "user" 
            WHERE id = %s
        """, (str(user_id),))
        
        result = cursor.fetchone()
        if result:
            user = {
                "id": result[0],
                "login": result[1],
                "fio_name": result[2],
                "password": result[3],  # hash (для обратной совместимости)
                "password_hash": result[3],
                "password_plain": result[4],
                "status": result[5] if result[5] else 'user',
                "failed_attempts": result[6] or 0,
                "lock_until": str(result[7]) if result[7] else None
            }
            return jsonify({"status": "success", "data": user})
        else:
            return jsonify({"status": "error", "message": "Пользователь не найден"})
    except Exception as e:
        log_function_error("get_user", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

def validate_login(login):
    """Валидация логина"""
    if not login:
        raise ValueError("Логин обязателен")
    login = validate_string(login, max_length=50, field_name="Логин", allow_empty=False)
    if not re.match(r'^[a-zA-Z0-9_]{3,50}$', login):
        raise ValueError("Логин должен содержать 3-50 символов (буквы, цифры, _)")
    return login

def validate_password(password, min_length=8):
    """Валидация пароля"""
    if not password:
        raise ValueError("Пароль обязателен")
    if len(password) < min_length:
        raise ValueError(f"Пароль должен содержать минимум {min_length} символов")
    if len(password) > 100:
        raise ValueError("Пароль слишком длинный (максимум 100 символов)")
    return password

@app.route('/api/create_user', methods=['POST'])
def create_user():
    """Create a new user"""
    conn = None
    cursor = None
    try:
        login = request.form.get('login')
        password = request.form.get('password')
        fio_name = request.form.get('fio_name')
        status = request.form.get('status', 'user')  # По умолчанию 'user'
        
        # Валидация входных данных
        try:
            login = validate_login(login)
            if password:
                password = validate_password(password, min_length=4)  # Минимум 4 для обратной совместимости
            if fio_name:
                fio_name = validate_string(fio_name, max_length=200, field_name="ФИО", allow_empty=False)
            if status not in ['user', 'admin']:
                raise ValueError("Статус должен быть 'user' или 'admin'")
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user with this login already exists
        cursor.execute("""
            SELECT id FROM "user" WHERE login = %s
        """, (login,))
        
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Пользователь с таким логином уже существует"}), 400
        
        # Get the next available ID
        cursor.execute("""
            SELECT COALESCE(MAX(CAST(id AS INTEGER)), 0) + 1 
            FROM "user"
        """)
        next_id = cursor.fetchone()[0]
        
        salt = generate_password_salt()
        pwd_hash = hash_password_with_salt(password, salt)

        cursor.execute("""
            INSERT INTO "user" (id, login, password_hash, password_salt, password, fio_name, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (str(next_id), login, pwd_hash, salt, password, fio_name, status))
        
        new_user_id = cursor.fetchone()[0]
        conn.commit()
        
        # Логируем без пароля
        logger.info(f"Создан пользователь: login={login}, fio={fio_name}, status={status}")
        return jsonify({"status": "success", "message": "Пользователь успешно создан", "user_id": new_user_id})
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return handle_db_error(e, "create_user")
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("create_user", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/update_user', methods=['POST'])
def update_user():
    """Update an existing user"""
    conn = None
    cursor = None
    try:
        user_id = request.form.get('user_id')
        login = request.form.get('login')
        password = request.form.get('password')
        fio_name = request.form.get('fio_name')
        status = request.form.get('status', 'user')  # По умолчанию 'user'
        
        if not user_id:
            return jsonify({"status": "error", "message": "ID пользователя обязателен"}), 400
        
        # Валидация входных данных
        try:
            if login:
                login = validate_login(login)
            if password:
                password = validate_password(password, min_length=4)
            if fio_name:
                fio_name = validate_string(fio_name, max_length=200, field_name="ФИО", allow_empty=False)
            if status not in ['user', 'admin']:
                raise ValueError("Статус должен быть 'user' или 'admin'")
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("""
            SELECT id FROM "user" WHERE id = %s
        """, (str(user_id),))
        
        if not cursor.fetchone():
            return jsonify({"status": "error", "message": "Пользователь не найден"}), 404
        
        # Check if login is already taken by another user
        cursor.execute("""
            SELECT id FROM "user" WHERE login = %s AND id != %s
        """, (login, str(user_id)))
        
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Пользователь с таким логином уже существует"})
        
        # Update user
        if password:  # Only update password if it's provided
            salt = generate_password_salt()
            pwd_hash = hash_password_with_salt(password, salt)
            cursor.execute("""
                UPDATE "user" 
                SET login = %s, password_hash = %s, password_salt = %s, password = %s, fio_name = %s, status = %s
                WHERE id = %s
            """, (login, pwd_hash, salt, password, fio_name, status, str(user_id)))
        else:
            cursor.execute("""
                UPDATE "user" 
                SET login = %s, fio_name = %s, status = %s
                WHERE id = %s
            """, (login, fio_name, status, str(user_id)))
        
        conn.commit()
        
        # Логируем без пароля
        logger.info(f"Обновлен пользователь: id={user_id}, login={login}, fio={fio_name}, status={status}")
        return jsonify({"status": "success", "message": "Пользователь успешно обновлен"})
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return handle_db_error(e, "update_user")
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("update_user", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/unlock_user', methods=['POST'])
def unlock_user():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "user_id обязателен"})
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE \"user\" SET failed_attempts=0, lock_until=NULL WHERE id=%s", (str(user_id),))
        conn.commit()
        return jsonify({"status": "success", "message": "Пользователь разблокирован"})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/delete_user', methods=['DELETE'])
def delete_user():
    """Delete a user"""
    try:
        user_id = request.args.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("""
            SELECT id FROM "user" WHERE id = %s
        """, (str(user_id),))
        
        if not cursor.fetchone():
            return jsonify({"status": "error", "message": "Пользователь не найден"})
        
        # Delete user
        cursor.execute("""
            DELETE FROM "user" WHERE id = %s
        """, (str(user_id),))
        
        conn.commit()
        return jsonify({"status": "success", "message": "Пользователь успешно удален"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("delete_user", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/search_users', methods=['GET'])
def search_users():
    """Search users by login or name"""
    try:
        query = request.args.get('query')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT id, login, fio_name, password_hash, password, status 
            FROM "user" 
            WHERE login ILIKE %s OR fio_name ILIKE %s
            ORDER BY login
        """, (search_pattern, search_pattern))
        
        results = cursor.fetchall()
        users = [
            {
                "id": row[0],
                "login": row[1],
                "fio_name": row[2],
                "password": row[3],
                "password_hash": row[3],
                "password_plain": row[4],
                "status": row[5] if row[5] else 'user'
            }
            for row in results
        ]
        
        return jsonify({"status": "success", "data": users})
    except Exception as e:
        log_function_error("search_users", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_api_credentials', methods=['GET'])
def get_api_credentials():
    """Get API credentials from ecp45mis table"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT login, password 
            FROM ecp45mis 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if result:
            return jsonify({
                "status": "success",
                "data": {
                    "login": result[0],
                    "password": result[1]
                }
            })
        else:
            return jsonify({"status": "error", "message": "Учетные данные не найдены"})
    except Exception as e:
        log_function_error("get_api_credentials", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/update_api_credentials', methods=['POST'])
def update_api_credentials():
    """Update API credentials in ecp45mis table"""
    try:
        login = request.form.get('login')
        password = request.form.get('password')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже запись
        cursor.execute("SELECT COUNT(*) FROM ecp45mis")
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Обновляем существующую запись
            cursor.execute("""
                UPDATE ecp45mis 
                SET login = %s, password = %s
            """, (login, password))
        else:
            # Создаем новую запись
            cursor.execute("""
                INSERT INTO ecp45mis (login, password)
                VALUES (%s, %s)
            """, (login, password))
        
        conn.commit()
        return jsonify({"status": "success", "message": "Учетные данные успешно обновлены"})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("update_api_credentials", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/create_bethesda_term', methods=['POST'])
def create_bethesda_term():
    try:
        term = request.form.get('term')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if term already exists
        cursor.execute("SELECT unique_id, full_name FROM betesda WHERE full_name = %s", (term,))
        existing = cursor.fetchone()
        if existing:
            return jsonify({
                "status": "success",
                "data": {
                    "id": existing[0],
                    "name": existing[1]
                }
            })
        
        # Insert new term
        cursor.execute("""
            INSERT INTO betesda (full_name)
            VALUES (%s)
            RETURNING unique_id, full_name
        """, (term,))
        
        new_term = cursor.fetchone()
        conn.commit()
        
        return jsonify({
            "status": "success",
            "data": {
                "id": new_term[0],
                "name": new_term[1]
            }
        })
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("create_bethesda_term", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_gistolog_data', methods=['GET'])
def get_gistolog_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query to get all gist_name values from gistolog table
        cursor.execute("""
            SELECT id, gist_name 
            FROM gistolog 
            ORDER BY gist_name
        """)
        
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        
        return jsonify({
            "status": "success",
            "data": data
        })
    except Exception as e:
        print(f"Error in get_gistolog_data: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/add_gistolog_term', methods=['POST'])
def add_gistolog_term():
    try:
        # Получаем данные из JSON или form data
        if request.is_json:
            data = request.get_json()
            term = data.get('name')
        else:
            term = request.form.get('term')
        
        if not term:
            return jsonify({"status": "error", "message": "Термин не указан"})
        
        logger.info(f"Adding gistolog term: {term}")
            
        conn = get_db_connection()
        cursor = conn.cursor()
        # Проверяем, есть ли уже такой термин
        cursor.execute("SELECT id FROM gistolog WHERE gist_name = %s", (term,))
        existing = cursor.fetchone()
        if existing:
            logger.info(f"Term already exists with id: {existing[0]}")
            return jsonify({"status": "success", "id": existing[0], "name": term})
        # Вставляем новый термин
        cursor.execute("INSERT INTO gistolog (gist_name) VALUES (%s) RETURNING id", (term,))
        new_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"New term added with id: {new_id}")
        return jsonify({"status": "success", "id": new_id, "name": term})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("add_gistolog_term", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_comment_data', methods=['GET'])
def get_comment_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, com_name FROM comment ORDER BY com_name")
        results = cursor.fetchall()
        data = [{"id": row[0], "name": row[1]} for row in results]
        logger.info(f"Загружено {len(data)} комментариев из таблицы comment")
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        log_function_error("get_comment_data", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)




@app.route('/api/get_service_name_by_id', methods=['GET'])
def get_service_name_by_id():
    """Получить название услуги по ID"""
    try:
        service_id = request.args.get('service_id')
        if not service_id:
            return jsonify({"status": "error", "message": "ID услуги не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name_service FROM service WHERE id = %s", (service_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Услуга с указанным ID не найдена"})
    except Exception as e:
        log_function_error("get_service_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_reference_names_batch', methods=['POST'])
def get_reference_names_batch():
    """Получить имена справочников по списку ID (batch запрос для оптимизации N+1)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        requests_map = data.get('requests', {})  # {type: [ids]}
        
        if not requests_map:
            return jsonify({"status": "error", "message": "Запросы не указаны"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        result = {}
        
        # Обрабатываем каждый тип справочника
        for ref_type, ids in requests_map.items():
            if not ids or not isinstance(ids, list):
                continue
            
            # Убираем дубликаты и пустые значения
            clean_ids = [str(id) for id in set(ids) if id and str(id).strip() and str(id) != 'null']
            if not clean_ids:
                result[ref_type] = {}
                continue
            
            placeholders = ','.join(['%s'] * len(clean_ids))
            names_map = {}
            
            try:
                if ref_type == 'service':
                    cursor.execute(f"SELECT id, name_service FROM service WHERE id IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): row[1] for row in cursor.fetchall()}
                elif ref_type == 'study_type':
                    cursor.execute(f"SELECT id, name FROM service_types WHERE id IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): row[1] for row in cursor.fetchall()}
                elif ref_type == 'research_type':
                    cursor.execute(f"SELECT id, character_name FROM character_study WHERE id IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): row[1] for row in cursor.fetchall()}
                elif ref_type == 'material_type':
                    cursor.execute(f"SELECT code, name FROM sample_types WHERE code IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): row[1] for row in cursor.fetchall()}
                elif ref_type == 'bethesda':
                    cursor.execute(f"SELECT unique_id, abbreviation, full_name FROM betesda WHERE unique_id IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): f"{row[1]} - {row[2]}" if row[1] else row[2] for row in cursor.fetchall()}
                elif ref_type == 'comment':
                    cursor.execute(f"SELECT id, name FROM comment WHERE id IN ({placeholders})", clean_ids)
                    names_map = {str(row[0]): row[1] for row in cursor.fetchall()}
                else:
                    logger.warning(f"Неизвестный тип справочника: {ref_type}")
                    names_map = {}
            except Exception as e:
                log_function_error(f"get_reference_names_batch:{ref_type}", e)
                names_map = {}
            
            result[ref_type] = names_map
        
        logger.debug(f"Загружено имен справочников: {sum(len(v) for v in result.values())} для {len(requests_map)} типов")
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        log_function_error("get_reference_names_batch", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_study_type_name_by_id', methods=['GET'])
def get_study_type_name_by_id():
    """Получить название типа исследования по ID"""
    try:
        study_type_id = request.args.get('study_type_id')
        if not study_type_id:
            return jsonify({"status": "error", "message": "ID типа исследования не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM service_types WHERE id = %s", (study_type_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Тип исследования с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_study_type_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_research_type_name_by_id', methods=['GET'])
def get_research_type_name_by_id():
    """Получить название характера исследования по ID"""
    try:
        research_type_id = request.args.get('research_type_id')
        if not research_type_id:
            return jsonify({"status": "error", "message": "ID характера исследования не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT character_name FROM character_study WHERE id = %s", (research_type_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Характер исследования с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_research_type_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_material_type_name_by_id', methods=['GET'])
def get_material_type_name_by_id():
    """Получить название характера материала по ID"""
    try:
        material_type_id = request.args.get('material_type_id')
        if not material_type_id:
            return jsonify({"status": "error", "message": "ID характера материала не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT sample_name FROM sample_types WHERE id = %s", (material_type_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Характер материала с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_material_type_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_bethesda_term_name_by_id', methods=['GET'])
def get_bethesda_term_name_by_id():
    """Получить название термина Бетесда по ID"""
    try:
        bethesda_id = request.args.get('bethesda_id')
        if not bethesda_id:
            return jsonify({"status": "error", "message": "ID термина Бетесда не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT abbreviation, full_name FROM betesda WHERE unique_id = %s", (bethesda_id,))
        result = cursor.fetchone()
        
        if result:
            abbreviation, full_name = result
            name = f"{abbreviation} - {full_name}" if abbreviation else full_name
            return jsonify({"status": "success", "name": name})
        else:
            return jsonify({"status": "error", "message": "Термин Бетесда с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_bethesda_term_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

@app.route('/api/get_comment_name_by_id', methods=['GET'])
def get_comment_name_by_id():
    """Получить название комментария по ID"""
    try:
        comment_id = request.args.get('comment_id')
        if not comment_id:
            return jsonify({"status": "error", "message": "ID комментария не указан"})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT com_name FROM comment WHERE id = %s", (comment_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({"status": "success", "name": result[0]})
        else:
            return jsonify({"status": "error", "message": "Комментарий с указанным ID не найден"})
    except Exception as e:
        log_function_error("get_comment_name_by_id", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)











# Route to serve the main HTML page
@app.route('/')
def index():
    return app.send_static_file('authorization.html')

# Route to serve static files (this is handled automatically by Flask with static_folder='web')
@app.route('/<path:filename>')
def serve_static(filename):
    return app.send_static_file(filename)

def generate_barcode(study_id, study_date):
    """Генерирует штрих-код для исследования в формате YYYYMMDD-ID"""
    try:
        if study_date:
            # Преобразуем дату в строку формата YYYYMMDD
            if isinstance(study_date, str):
                date_obj = datetime.strptime(study_date, "%Y-%m-%d")
            else:
                date_obj = study_date
            date_str = date_obj.strftime("%Y%m%d")
        else:
            # Если дата не указана, используем текущую дату
            date_str = datetime.now().strftime("%Y%m%d")
        
        return f"{date_str}-{study_id}"
    except Exception as e:
        log_function_error("generate_barcode", e)
        return f"{datetime.now().strftime('%Y%m%d')}-{study_id}"

def ensure_conclusion_text_column():
	"""Ensure studies.conclusion_text exists"""
	conn = None
	cursor = None
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		cursor.execute("ALTER TABLE studies ADD COLUMN IF NOT EXISTS conclusion_text TEXT")
		conn.commit()
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def ensure_optimistic_locking_columns():
	"""Добавляет поля для оптимистической блокировки в таблицы studies и materials"""
	conn = None
	cursor = None
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		# Добавляем поля version, locked_by_user_id, locked_at в studies
		cursor.execute("ALTER TABLE studies ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 0")
		cursor.execute("ALTER TABLE studies ADD COLUMN IF NOT EXISTS locked_by_user_id VARCHAR(255)")
		cursor.execute("ALTER TABLE studies ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP")
		
		# Добавляем поля version, locked_by_user_id, locked_at в materials
		cursor.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 0")
		cursor.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS locked_by_user_id VARCHAR(255)")
		cursor.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP")
		
		# Инициализируем version = 0 для существующих записей
		cursor.execute("UPDATE studies SET version = 0 WHERE version IS NULL")
		cursor.execute("UPDATE materials SET version = 0 WHERE version IS NULL")
		
		conn.commit()
		logger.info("Поля для оптимистической блокировки добавлены/проверены")
	except Exception as e:
		log_function_error("ensure_optimistic_locking_columns", e)
		if conn:
			conn.rollback()
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def check_study_lock(study_id, current_user_id):
	"""Проверяет, заблокировано ли исследование другим пользователем"""
	conn = None
	cursor = None
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		cursor.execute("""
			SELECT s.locked_by_user_id, s.locked_at, u.fio_name
			FROM studies s
			LEFT JOIN "user" u ON s.locked_by_user_id = u.id
			WHERE s.id = %s
		""", (study_id,))
		
		result = cursor.fetchone()
		if not result:
			return None  # Исследование не найдено
		
		locked_by, locked_at, locked_by_fio = result
		
		if not locked_by:
			return None  # Не заблокировано
		
		# Проверяем, не истекла ли блокировка (30 минут)
		if locked_at:
			lock_time = locked_at if isinstance(locked_at, datetime) else datetime.fromisoformat(str(locked_at))
			elapsed = (datetime.now() - lock_time).total_seconds()
			if elapsed > 1800:  # 30 минут
				# Блокировка истекла, снимаем её
				cursor.execute("""
					UPDATE studies 
					SET locked_by_user_id = NULL, locked_at = NULL 
					WHERE id = %s
				""", (study_id,))
				conn.commit()
				return None
		
		# Если заблокировано текущим пользователем - разрешаем
		if locked_by == str(current_user_id):
			return None
		
		# Заблокировано другим пользователем
		return {
			"locked": True,
			"locked_by_user_id": locked_by,
			"locked_by_fio": locked_by_fio or "Неизвестный пользователь",
			"locked_at": str(locked_at) if locked_at else None
		}
	except Exception as e:
		log_function_error("check_study_lock", e)
		return None
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def lock_study(study_id, user_id, lock_duration_minutes=30):
	"""Устанавливает блокировку исследования для пользователя"""
	conn = None
	cursor = None
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		# Проверяем, не заблокировано ли другим пользователем
		lock_info = check_study_lock(study_id, user_id)
		if lock_info and lock_info.get("locked"):
			return lock_info
		
		# Устанавливаем блокировку
		cursor.execute("""
			UPDATE studies 
			SET locked_by_user_id = %s, locked_at = CURRENT_TIMESTAMP
			WHERE id = %s
		""", (str(user_id), study_id))
		
		conn.commit()
		return None  # Успешно заблокировано
	except Exception as e:
		log_function_error("lock_study", e)
		if conn:
			conn.rollback()
		return {"locked": False, "error": str(e)}
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def unlock_study(study_id, user_id):
	"""Снимает блокировку исследования"""
	conn = None
	cursor = None
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		cursor.execute("""
			UPDATE studies 
			SET locked_by_user_id = NULL, locked_at = NULL
			WHERE id = %s AND locked_by_user_id = %s
		""", (study_id, str(user_id)))
		
		conn.commit()
		return True
	except Exception as e:
		log_function_error("unlock_study", e)
		if conn:
			conn.rollback()
		return False
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def ensure_db_indexes():
	"""Создает необходимые индексы БД для улучшения производительности"""
	conn = None
	cursor = None
	indexes_created = 0
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		# Список индексов для создания (IF NOT EXISTS для безопасности)
		indexes = [
			# Индексы для таблицы patients
			("CREATE INDEX IF NOT EXISTS idx_patients_snils ON patients(snils) WHERE snils IS NOT NULL", "patients.snils"),
			("CREATE INDEX IF NOT EXISTS idx_patients_ambulatory_card ON patients(ambulatory_card_number) WHERE ambulatory_card_number IS NOT NULL", "patients.ambulatory_card_number"),
			
			# Индексы для таблицы studies
			("CREATE INDEX IF NOT EXISTS idx_studies_patient_id ON studies(patient_id)", "studies.patient_id"),
			("CREATE INDEX IF NOT EXISTS idx_studies_study_date ON studies(study_date)", "studies.study_date"),
			("CREATE INDEX IF NOT EXISTS idx_studies_barcode ON studies(barcode) WHERE barcode IS NOT NULL", "studies.barcode"),
			("CREATE INDEX IF NOT EXISTS idx_studies_doctor_id ON studies(doctor_id) WHERE doctor_id IS NOT NULL", "studies.doctor_id"),
			("CREATE INDEX IF NOT EXISTS idx_studies_material_id ON studies(material_id) WHERE material_id IS NOT NULL", "studies.material_id"),
			
			# Индексы для таблицы materials
			("CREATE INDEX IF NOT EXISTS idx_materials_patient_id ON materials(patient_id)", "materials.patient_id"),
			("CREATE INDEX IF NOT EXISTS idx_materials_direction_number ON materials(direction_number) WHERE direction_number IS NOT NULL", "materials.direction_number"),
			
			# Индексы для таблицы user_sessions
			("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id) WHERE is_active = TRUE", "user_sessions.user_id"),
			("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at) WHERE is_active = TRUE", "user_sessions.expires_at"),
			
			# Индексы для таблицы user
			("CREATE INDEX IF NOT EXISTS idx_user_login ON \"user\"(login)", "user.login"),
			("CREATE INDEX IF NOT EXISTS idx_user_lock_until ON \"user\"(lock_until) WHERE lock_until IS NOT NULL", "user.lock_until"),
		]
		
		for index_sql, index_name in indexes:
			try:
				cursor.execute(index_sql)
				indexes_created += 1
				logger.debug(f"Индекс создан/проверен: {index_name}")
			except Exception as e:
				log_function_error(f"ensure_db_indexes:{index_name}", e)
				# Продолжаем создание других индексов даже при ошибке
		
		conn.commit()
		logger.info(f"Создано/проверено {indexes_created} индексов БД")
	except Exception as e:
		log_function_error("ensure_db_indexes", e)
		if conn:
			conn.rollback()
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

def preload_reference_data():
    """Предзагрузка справочных данных в контексте приложения"""
    loaders = [
        get_service_types,
        get_sample_types,
        get_bethesda_terms,
        get_study_characters,
        preload_mkb_data,
        get_physician_data,
        get_services_data,
    ]
    for loader in loaders:
        try:
            loader()
            logger.info(f"Успешная предзагрузка: {loader.__name__}")
        except Exception as exc:
            log_function_error(f"preload_reference_data:{loader.__name__}", exc)

def bootstrap_app():
    """Полный цикл инициализации приложения для продакшена"""
    pool = init_db_pool()
    if pool is None:
        raise RuntimeError("Не удалось инициализировать пул соединений с базой данных. Проверьте параметры подключения.")
    create_session_table()
    ensure_conclusion_text_column()
    ensure_optimistic_locking_columns()  # Добавление полей для оптимистической блокировки
    ensure_db_indexes()  # Создание индексов для улучшения производительности
    with app.app_context():
        preload_reference_data()
    run_startup_checks()

@app.route('/api/search_study_by_ambulatory_card', methods=['GET'])
def search_study_by_ambulatory_card():
	try:
		card_number = request.args.get('card_number')
		conn = get_db_connection()
		cursor = conn.cursor()
		logger.info(f"Поиск по амбулаторной карте: {card_number}")
		# Найти пациента по номеру амбулаторной карты
		cursor.execute("""
			SELECT id FROM patients
			WHERE ambulatory_card_number = %s
			LIMIT 1
		""", (card_number,))
		patient_row = cursor.fetchone()
		if not patient_row:
			return jsonify({"status": "success", "message": "Пациент не найден", "data": None})
		patient_id = patient_row[0]
		# Найти последнее исследование пациента
		cursor.execute("""
			SELECT id FROM studies
			WHERE patient_id = %s
			ORDER BY study_date DESC NULLS LAST, id DESC
			LIMIT 1
		""", (patient_id,))
		study_row = cursor.fetchone()
		study_id = study_row[0] if study_row else None
		return jsonify({
			"status": "success",
			"data": {"patient_id": patient_id, "study_id": study_id}
		})
	except Exception as e:
		log_function_error("search_study_by_ambulatory_card", e)
		return jsonify({"status": "error", "message": f"Ошибка: {str(e)}"})
	finally:
		if cursor:
			cursor.close()
		if conn:
			return_db_connection(conn)

# Инициализация пула соединений

@app.route('/api/migrate_password_hashes', methods=['POST'])
def migrate_password_hashes():
    """One-time migration: for users with plaintext password but empty hash/salt, compute hash, set salt, null out plaintext."""
    conn = None
    cursor = None
    try:
        # Optional simple protection: require a secret token in env
        token = request.headers.get('X-Migration-Token')
        expected = os.getenv('MIGRATION_TOKEN')
        if expected and token != expected:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, password FROM "user" WHERE (password IS NOT NULL AND password <> '') AND (password_hash IS NULL OR password_hash = '')
        """)
        rows = cursor.fetchall()
        updated = 0
        for uid, plaintext in rows:
            salt = generate_password_salt()
            pwd_hash = hash_password_with_salt(plaintext, salt)
            cursor.execute(
                """
                UPDATE "user"
                SET password_hash = %s, password_salt = %s, password = NULL
                WHERE id = %s
                """,
                (pwd_hash, salt, str(uid))
            )
            updated += 1
        conn.commit()
        return jsonify({"status": "success", "updated": updated})
    except Exception as e:
        if conn:
            conn.rollback()
        log_function_error("migrate_password_hashes", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_db_connection(conn)

if __name__ == "__main__":
    bootstrap_app()
    # Debug режим управляется через переменную окружения FLASK_DEBUG
    # По умолчанию False для безопасности в продакшене
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.getenv('FLASK_PORT', '5050'))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
