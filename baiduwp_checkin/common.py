import json
import logging
import os
import secrets
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("baiduwp_checkin")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def setup_logging(log_file: str) -> Path:
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


def load_json_file(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def parse_env_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def parse_env_int(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_env_jsonish(value: str) -> Any:
    if not value:
        return None
    if value[0] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def add_env_value(config: dict[str, Any], env_name: str, key: str, value_type: str = "str") -> None:
    value = env_value(env_name)
    if not value:
        return

    if value_type == "int":
        int_value = parse_env_int(value)
        if int_value is not None:
            config[key] = int_value
        return
    if value_type == "bool":
        config[key] = parse_env_bool(value)
        return
    if value_type == "jsonish":
        config[key] = parse_env_jsonish(value)
        return
    config[key] = value


def build_split_env_config() -> tuple[Any, str | None]:
    cookie = env_value("BAIDUWP_COOKIE")
    if not cookie:
        return None, None

    app: dict[str, Any] = {}
    app_fields = {
        "BAIDUWP_APP_Z": ("z", "str"),
        "BAIDUWP_APP_CUID": ("cuid", "str"),
        "BAIDUWP_APP_DEVUID": ("devuid", "str"),
        "BAIDUWP_APP_CHANNEL": ("channel", "jsonish"),
        "BAIDUWP_APP_VERSION": ("version", "str"),
        "BAIDUWP_APP_VERSIONCODE": ("versioncode", "str"),
        "BAIDUWP_APP_CLIENTTYPE": ("clienttype", "str"),
        "BAIDUWP_APP_THEMEINFO": ("themeinfo", "str"),
        "BAIDUWP_APP_RCHANNEL": ("rchannel", "str"),
        "BAIDUWP_APP_APP": ("app", "str"),
        "BAIDUWP_APP_USER_AGENT": ("user_agent", "str"),
        "BAIDUWP_APP_OFFLINEPACKAGE": ("offlinepackage", "jsonish"),
        "BAIDUWP_APP_TASKS": ("taskscore_tasks", "jsonish"),
        "BAIDUWP_APP_TASKSCORE_TASKS": ("taskscore_tasks", "jsonish"),
        "BAIDUWP_APP_COIN_SIGN_TASK_ID": ("coin_sign_task_id", "str"),
        "BAIDUWP_APP_COIN_SIGN_TASK_FROM": ("coin_sign_task_from", "jsonish"),
        "BAIDUWP_APP_IS_GROWTH": ("is_growth", "int"),
        "BAIDUWP_APP_QUESTION_TASK_ID": ("question_task_id", "str"),
        "BAIDUWP_APP_QUESTION_TASK_FROM": ("question_task_from", "jsonish"),
        "BAIDUWP_APP_UK": ("uk", "str"),
        "BAIDUWP_APP_TOKEN": ("token", "str"),
    }
    for env_name, (key, value_type) in app_fields.items():
        add_env_value(app, env_name, key, value_type)

    ad_watch: dict[str, Any] = {}
    add_env_value(ad_watch, "BAIDUWP_APP_AD_WATCH_ENABLED", "enabled", "bool")
    add_env_value(ad_watch, "BAIDUWP_APP_AD_WATCH_TASK_ID", "task_id")
    add_env_value(ad_watch, "BAIDUWP_APP_AD_WATCH_TASK_FROM", "task_from", "jsonish")
    add_env_value(ad_watch, "BAIDUWP_APP_AD_WATCH_DELAY_SECONDS", "delay_seconds", "int")
    if ad_watch:
        app["ad_watch"] = ad_watch

    explicit_app_enabled = env_value("BAIDUWP_APP_ENABLED")
    if app or explicit_app_enabled:
        app["enabled"] = parse_env_bool(explicit_app_enabled, default=True)

    account: dict[str, Any] = {"cookie": cookie}
    if app:
        account["app"] = app

    config: dict[str, Any] = {"BAIDUWP": [account]}

    email: dict[str, Any] = {}
    email_fields = {
        "BAIDUWP_EMAIL_SMTP_HOST": ("smtp_host", "str"),
        "BAIDUWP_EMAIL_SMTP_PORT": ("smtp_port", "int"),
        "BAIDUWP_EMAIL_SMTP_USER": ("smtp_user", "str"),
        "BAIDUWP_EMAIL_SMTP_PASSWORD": ("smtp_password", "str"),
        "BAIDUWP_EMAIL_SMTP_PASSWORD_ENV": ("smtp_password_env", "str"),
        "BAIDUWP_EMAIL_FROM_ADDR": ("from_addr", "str"),
        "BAIDUWP_EMAIL_TO_ADDRS": ("to_addrs", "jsonish"),
        "BAIDUWP_EMAIL_USE_SSL": ("use_ssl", "bool"),
        "BAIDUWP_EMAIL_USE_TLS": ("use_tls", "bool"),
        "BAIDUWP_EMAIL_SUBJECT": ("subject", "str"),
    }
    for env_name, (key, value_type) in email_fields.items():
        add_env_value(email, env_name, key, value_type)

    explicit_email_enabled = env_value("BAIDUWP_EMAIL_ENABLED")
    if email or explicit_email_enabled:
        email["enabled"] = parse_env_bool(explicit_email_enabled, default=True)
        config["EMAIL"] = email

    return config, "split environment variables"


def normalize_accounts(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("BAIDUWP"), list):
        accounts = data["BAIDUWP"]
    elif isinstance(data, list):
        accounts = data
    elif isinstance(data, dict) and data.get("cookie"):
        accounts = [data]
    else:
        accounts = []

    result = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        cookie = str(item.get("cookie", "")).strip()
        if not cookie:
            continue
        account: dict[str, Any] = {"cookie": cookie}
        if isinstance(item.get("app"), dict):
            account["app"] = item["app"]
        result.append(account)
    return result


def find_config_path(config_path: str | None) -> Path | None:
    if config_path:
        path = Path(config_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path if path.exists() else None

    candidate_paths = [
        Path.cwd() / "config.json",
        Path.cwd() / "config" / "config.json",
        PROJECT_ROOT / "config.json",
        PROJECT_ROOT / "config" / "config.json",
    ]
    for path in candidate_paths:
        if path.exists():
            return path
    return None


def load_env_config() -> tuple[Any, str | None]:
    for env_name in ("BAIDUWP_CONFIG", "BAIDUWP_CONFIG_JSON"):
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return json.loads(env_value), env_name
    split_config, split_source = build_split_env_config()
    if split_config is not None:
        return split_config, split_source
    return None, None


def load_config(config_path: str | None) -> tuple[Any, Path | str | None]:
    if config_path:
        path = find_config_path(config_path)
        if not path:
            return None, None
        return load_json_file(path), path

    env_config, env_name = load_env_config()
    if env_config is not None:
        return env_config, env_name

    path = find_config_path(None)
    if not path:
        return None, None
    return load_json_file(path), path


def load_accounts(config_path: str | None, cookie: str | None = None) -> tuple[list[dict[str, Any]], Any, Path | str | None]:
    if cookie:
        config_data, loaded_config_path = load_config(config_path)
        return [{"cookie": cookie.strip()}], config_data, loaded_config_path

    config_data, loaded_config_path = load_config(config_path)
    if config_data is not None:
        return normalize_accounts(config_data), config_data, loaded_config_path

    env_value = os.getenv("BAIDUWP", "").strip()
    if env_value:
        try:
            return normalize_accounts(json.loads(env_value)), None, None
        except json.JSONDecodeError:
            return [{"cookie": env_value}], None, None

    return [], config_data, loaded_config_path


def normalize_email_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    config = data.get("EMAIL") or data.get("SMTP") or {}
    if not isinstance(config, dict):
        return {}
    if not config.get("enabled", False):
        return {}
    return config


def email_recipients(config: dict[str, Any]) -> list[str]:
    recipients = config.get("to_addrs") or config.get("to_addr") or []
    if isinstance(recipients, str):
        recipients = [item.strip() for item in recipients.split(",")]
    return [str(item).strip() for item in recipients if str(item).strip()]


def send_email(config: dict[str, Any], subject: str, content: str) -> None:
    host = str(config.get("smtp_host", "")).strip()
    port = int(config.get("smtp_port", 465))
    username = str(config.get("smtp_user", "")).strip()
    password_env = str(config.get("smtp_password_env", "")).strip()
    password = str(config.get("smtp_password", "") or (os.getenv(password_env, "") if password_env else "")).strip()
    from_addr = str(config.get("from_addr", "") or username).strip()
    recipients = email_recipients(config)

    if not host or not from_addr or not recipients:
        LOGGER.warning("邮箱通知配置不完整，已跳过发送")
        return

    message = EmailMessage()
    message["Subject"] = str(config.get("subject") or subject)
    message["From"] = from_addr
    message["To"] = ", ".join(recipients)
    message.set_content(content)

    use_ssl = bool(config.get("use_ssl", port == 465))
    use_tls = bool(config.get("use_tls", not use_ssl))

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)

    LOGGER.info("邮箱通知已发送给 %s", ", ".join(recipients))


def wait_random_delay(max_minutes: float, disabled: bool) -> int:
    if disabled or max_minutes <= 0:
        LOGGER.info("随机延迟已禁用")
        return 0

    max_seconds = int(max_minutes * 60)
    delay_seconds = secrets.randbelow(max_seconds + 1) if max_seconds > 0 else 0
    if delay_seconds <= 0:
        LOGGER.info("随机延迟命中 0 秒，立即执行")
        return 0

    LOGGER.info("正式执行前随机等待 %s 秒，阈值 %.2f 分钟", delay_seconds, max_minutes)
    time.sleep(delay_seconds)
    LOGGER.info("随机等待结束，开始执行正式任务")
    return delay_seconds
