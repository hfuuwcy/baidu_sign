import argparse
import logging
import re
import time
from typing import Any

import requests

from .app import BaiduWPApp
from .common import (
    load_accounts,
    normalize_email_config,
    send_email,
    setup_logging,
    wait_random_delay,
)


LOGGER = logging.getLogger("baiduwp_checkin")


class BaiduWP:
    name = "百度网盘"

    def __init__(self, cookie: str, timeout: int = 30, app_config: dict[str, Any] | None = None):
        if not cookie:
            raise ValueError("必须提供百度网盘 Cookie")
        self.cookie = cookie
        self.timeout = timeout
        self.app_config = app_config or {}
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36"
            ),
            "Referer": "https://pan.baidu.com/wap/svip/growth/task",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": self.cookie,
        }

    def _get(self, url: str) -> tuple[int, Any, str]:
        response = self.session.get(url, headers=self.headers, timeout=self.timeout)
        text = response.text
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data, text

    @staticmethod
    def _find_json_value(data: Any, key: str) -> Any:
        if isinstance(data, dict):
            if key in data:
                return data[key]
            for value in data.values():
                found = BaiduWP._find_json_value(value, key)
                if found is not None:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = BaiduWP._find_json_value(item, key)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _find_text_value(text: str, key: str) -> str | None:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', text)
        if match:
            return match.group(1)
        match = re.search(rf'"{re.escape(key)}"\s*:\s*(\d+)', text)
        if match:
            return match.group(1)
        return None

    def _value(self, data: Any, text: str, key: str) -> Any:
        value = self._find_json_value(data, key)
        if value is not None:
            return value
        return self._find_text_value(text, key)

    def signin(self) -> tuple[Any, str]:
        url = "https://pan.baidu.com/rest/2.0/membership/level?app_id=250528&web=5&method=signin"
        status_code, data, text = self._get(url)
        if status_code != 200:
            return None, f"签到请求失败: {status_code}"
        sign_point = self._value(data, text, "points")
        signin_error_msg = self._value(data, text, "error_msg") or ""
        return sign_point, str(signin_error_msg)

    def get_question(self) -> dict[str, Any]:
        url = "https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion?app_id=250528&web=5"
        status_code, data, text = self._get(url)
        if status_code != 200:
            return {}
        return {
            "ask_id": self._value(data, text, "ask_id"),
            "answer": self._value(data, text, "answer"),
            "answer_status": self._value(data, text, "answer_status"),
            "score": self._value(data, text, "score"),
            "question": self._value(data, text, "question"),
        }

    def answer_question(self, ask_id: Any, answer: Any) -> dict[str, Any]:
        url = (
            "https://pan.baidu.com/act/v2/membergrowv2/answerquestion"
            f"?app_id=250528&web=5&ask_id={ask_id}&answer={answer}"
        )
        status_code, data, text = self._get(url)
        if status_code != 200:
            return {"score": None, "message": f"答题请求失败: {status_code}"}
        return {
            "score": self._value(data, text, "score"),
            "message": self._value(data, text, "show_msg") or self._value(data, text, "error_msg") or "",
        }

    def get_userinfo(self) -> tuple[Any, Any]:
        url = "https://pan.baidu.com/rest/2.0/membership/user?app_id=250528&web=5&method=query"
        status_code, data, text = self._get(url)
        if status_code != 200:
            return None, None
        current_level = self._value(data, text, "current_level")
        current_value = self._value(data, text, "current_value")
        return current_level, current_value

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def format_delta(before_value: Any, after_value: Any) -> str:
        before_int = BaiduWP._to_int(before_value)
        after_int = BaiduWP._to_int(after_value)
        if before_int is None or after_int is None:
            return ""
        return f"（本次变化{after_int - before_int:+d}）"

    def maybe_save_question_task(self) -> str:
        if not isinstance(self.app_config, dict) or not self.app_config.get("enabled", False):
            return "，未配置App任务上报"
        try:
            result = BaiduWPApp(cookie=self.cookie, app_config=self.app_config, timeout=self.timeout).taskscore_save()
        except Exception as exc:
            LOGGER.warning("App任务上报失败: %s", exc)
            return f"，App任务上报失败: {exc}"

        errno = result.get("errno")
        error_code = result.get("error_code")
        message = result.get("errmsg") or result.get("error_msg") or result.get("show_msg") or result.get("msg") or ""
        if errno == 0 or error_code == 0:
            return f"，App任务上报成功{message}"
        if message:
            return f"，App任务上报返回: {message}"
        return "，App任务上报已请求"

    def answer_daily_question(self, before_value: Any) -> tuple[str, Any]:
        question_info = self.get_question()
        ask_id = question_info.get("ask_id")
        answer = question_info.get("answer")
        answer_status = self._to_int(question_info.get("answer_status"))
        existing_score = question_info.get("score")

        if not ask_id or answer is None:
            _, current_value = self.get_userinfo()
            return "答题未获取到题目", current_value

        if answer_status == 1:
            _, current_value = self.get_userinfo()
            delta = self.format_delta(before_value, current_value)
            if self._to_int(current_value) == self._to_int(before_value):
                task_msg = self.maybe_save_question_task()
                time.sleep(1)
                _, current_value = self.get_userinfo()
                delta = self.format_delta(before_value, current_value)
                return f"答题已完成，得分{existing_score or ''}{task_msg}{delta}", current_value
            return f"答题已完成，得分{existing_score or ''}{delta}", current_value

        answer_result = self.answer_question(ask_id, answer)
        time.sleep(1)
        _, current_value = self.get_userinfo()
        delta = self.format_delta(before_value, current_value)
        if self._to_int(current_value) == self._to_int(before_value):
            task_msg = self.maybe_save_question_task()
            time.sleep(1)
            _, current_value = self.get_userinfo()
            delta = self.format_delta(before_value, current_value)
            return f"答题获得{answer_result.get('score') or ''}{answer_result.get('message') or ''}{task_msg}{delta}", current_value
        return f"答题获得{answer_result.get('score') or ''}{answer_result.get('message') or ''}{delta}", current_value

    def run(self) -> str:
        _, start_value = self.get_userinfo()
        sign_point, signin_error_msg = self.signin()
        time.sleep(3)
        _, after_sign_value = self.get_userinfo()
        sign_delta = self.format_delta(start_value, after_sign_value)
        answer_msg, after_answer_value = self.answer_daily_question(after_sign_value)
        current_level, current_value = self.get_userinfo()
        return (
            f"签到获得{sign_point or ''}{signin_error_msg}{sign_delta}\n"
            f"{answer_msg}\n"
            f"当前会员等级{current_level or ''}，成长值{current_value or ''}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="百度网盘会员成长值签到")
    parser.add_argument("-c", "--config", help="配置文件路径，默认自动查找 config.json")
    parser.add_argument("--cookie", help="直接传入百度网盘 Cookie")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时时间，默认 30 秒")
    parser.add_argument("--log-file", default="logs/baiduwp_checkin.log", help="日志文件路径")
    parser.add_argument("--no-email", action="store_true", help="禁用邮箱通知")
    parser.add_argument("--test-email", action="store_true", help="只测试邮箱通知，不执行签到")
    parser.add_argument("--test-userinfo", action="store_true", help="只测试会员信息查询，不执行签到和答题")
    parser.add_argument("--random-delay-minutes", type=float, default=5, help="正式执行前随机延迟分钟数，默认 5")
    parser.add_argument("--no-random-delay", action="store_true", help="禁用正式执行前随机延迟")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_path = setup_logging(args.log_file)
    LOGGER.info("日志文件: %s", log_path)
    accounts, config_data, loaded_config_path = load_accounts(args.config, args.cookie)
    if loaded_config_path:
        LOGGER.info("使用配置文件: %s", loaded_config_path)

    if args.test_email:
        email_config = normalize_email_config(config_data)
        if not email_config:
            raise SystemExit("邮箱通知未启用或未配置，请在 config.json 中配置 EMAIL.enabled=true")
        send_email(
            email_config,
            "百度网盘签到邮箱测试",
            f"这是一封测试邮件。\n\n配置文件: {loaded_config_path}\n日志文件: {log_path}",
        )
        LOGGER.info("邮箱测试完成")
        return

    if not accounts:
        raise SystemExit("未找到百度网盘账号配置，请提供 config.json、BAIDUWP 环境变量或 --cookie")

    if args.test_userinfo:
        LOGGER.info("开始测试百度网盘会员信息查询，账号数: %s", len(accounts))
        content_list = []
        for index, account in enumerate(accounts, start=1):
            try:
                current_level, current_value = BaiduWP(cookie=account["cookie"], timeout=args.timeout).get_userinfo()
                if current_level is None and current_value is None:
                    message = f"百度网盘账号 {index}: 会员信息查询失败，未获取到等级和成长值"
                    content_list.append(message)
                    LOGGER.warning(message)
                    print(message)
                else:
                    message = f"百度网盘账号 {index}: 当前会员等级{current_level or ''}，成长值{current_value or ''}"
                    content_list.append(message)
                    LOGGER.info(message)
                    print(message)
            except Exception as exc:
                content_list.append(f"百度网盘账号 {index}: 会员信息查询异常: {exc}")
                LOGGER.exception("百度网盘账号 %s 会员信息查询异常", index)
                print(f"百度网盘账号 {index}: 会员信息查询异常: {exc}")

        email_config = normalize_email_config(config_data)
        if email_config and not args.no_email:
            try:
                send_email(email_config, "百度网盘会员信息测试", "\n".join(content_list))
            except Exception:
                LOGGER.exception("邮箱通知发送失败")
        elif args.no_email:
            LOGGER.info("已通过 --no-email 禁用邮箱通知")
        else:
            LOGGER.info("未启用邮箱通知")
        return

    wait_random_delay(args.random_delay_minutes, args.no_random_delay)

    start_time = time.time()
    content_list = []
    LOGGER.info("开始执行百度网盘签到，账号数: %s", len(accounts))
    for index, account in enumerate(accounts, start=1):
        LOGGER.info("开始执行百度网盘账号 %s", index)
        try:
            result = BaiduWP(
                cookie=account["cookie"],
                timeout=args.timeout,
                app_config=account.get("app") if isinstance(account.get("app"), dict) else None,
            ).run()
            content_list.append(f"百度网盘账号 {index}\n{result}")
            LOGGER.info("百度网盘账号 %s 执行完成\n%s", index, result)
        except Exception as exc:
            content_list.append(f"百度网盘账号 {index}\n执行失败: {exc}")
            LOGGER.exception("百度网盘账号 %s 执行失败", index)

    elapsed = int(time.time() - start_time)
    content_list.append(f"任务用时: {elapsed} 秒\n日志文件: {log_path}")
    content = "\n\n".join(content_list)

    email_config = normalize_email_config(config_data)
    if email_config and not args.no_email:
        try:
            send_email(email_config, "百度网盘签到通知", content)
        except Exception:
            LOGGER.exception("邮箱通知发送失败")
    elif args.no_email:
        LOGGER.info("已通过 --no-email 禁用邮箱通知")
    else:
        LOGGER.info("未启用邮箱通知")

    LOGGER.info("本次任务结束，用时 %s 秒", elapsed)


if __name__ == "__main__":
    main()
