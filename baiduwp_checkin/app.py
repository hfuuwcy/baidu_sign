import hashlib
import argparse
import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import requests

try:
    from .common import load_accounts, normalize_email_config, send_email, setup_logging
except ImportError:
    package_parent = Path(__file__).resolve().parents[1]
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))
    from baiduwp_checkin.common import load_accounts, normalize_email_config, send_email, setup_logging


LOGGER = logging.getLogger("baiduwp_checkin")


class BaiduWPApp:
    name = "百度网盘 App"

    def __init__(self, cookie: str, app_config: dict[str, Any], timeout: int = 30):
        if not cookie:
            raise ValueError("必须提供百度网盘 Cookie")
        if not isinstance(app_config, dict) or not app_config.get("enabled", False):
            raise ValueError("未启用 App 端签到配置")
        self.cookie = cookie
        self.app_config = app_config
        self.timeout = timeout
        self.session = requests.Session()
        self.headers = {
            "User-Agent": str(
                self.app_config.get("user_agent")
                or "netdisk;13.20.7;android;android-android;15;JSbridge4.4.0;jointBridge;1.1.0;"
            ),
            "Accept": "application/json, text/plain, */*",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": self.cookie,
        }

    @staticmethod
    def _param_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @classmethod
    def _normalize_params(cls, params: dict[str, Any]) -> dict[str, str]:
        return {key: cls._param_value(value) for key, value in params.items() if value is not None}

    def _get(self, path: str, params: dict[str, Any]) -> tuple[int, Any, str]:
        response = self.session.get(
            f"https://pan.baidu.com{path}",
            headers=self.headers,
            params=self._normalize_params(params),
            timeout=self.timeout,
        )
        text = response.text
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data, text

    def _common_params(self) -> dict[str, Any]:
        missing = [key for key in ("z", "cuid", "devuid") if not self.app_config.get(key)]
        if missing:
            raise ValueError(f"App 端签到缺少配置: {', '.join(missing)}")

        rand = secrets.token_hex(20)
        offlinepackage = self.app_config.get("offlinepackage")
        params: dict[str, Any] = {
            "z": self.app_config["z"],
            "clienttype": str(self.app_config.get("clienttype", "1")),
            "channel": self.app_config.get("channel", "android_bd-netdisk"),
            "rand": rand,
            "rand2": secrets.token_hex(20),
            "time": str(int(time.time())),
            "cuid": self.app_config["cuid"],
            "devuid": self.app_config["devuid"],
            "version": self.app_config.get("version", "13.20.7"),
            "versioncode": str(self.app_config.get("versioncode", "4062")),
            "themeinfo": str(self.app_config.get("themeinfo", "0")),
            "rchannel": self.app_config.get("rchannel") or hashlib.md5(rand.encode()).hexdigest(),
            "app": self.app_config.get("app", "android"),
        }
        if offlinepackage:
            params["offlinepackage"] = offlinepackage
        return params

    def loginstatus(self) -> dict[str, Any]:
        status_code, data, _ = self._get("/api/loginstatus", self._common_params())
        if status_code != 200 or not isinstance(data, dict) or data.get("errno") != 0:
            raise ValueError(f"App 登录状态查询失败: {status_code} {data}")
        login_info = data.get("login_info")
        return login_info if isinstance(login_info, dict) else {}

    def coin_signin(self, is_growth: int = 1) -> dict[str, Any]:
        params = self._common_params()
        task_id = str(self.app_config.get("coin_sign_task_id", "3434916321758720"))
        params.update(
            {
                "task_id": task_id,
                "task_id_str": task_id,
                "task_from": self.app_config.get("coin_sign_task_from", "task_sys_daily"),
                "is_growth": str(is_growth),
            }
        )
        status_code, data, _ = self._get("/coins/taskcenter/signin", params)
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 端签到请求失败: {status_code}")
        return data

    def coin_signin_list(self, is_growth: int = 1) -> dict[str, Any]:
        params = self._common_params()
        task_id = str(self.app_config.get("coin_sign_task_id", "3434916321758720"))
        params.update(
            {
                "task_id": task_id,
                "task_id_str": task_id,
                "task_from": self.app_config.get("coin_sign_task_from", "task_sys_daily"),
                "is_growth": str(is_growth),
            }
        )
        status_code, data, _ = self._get("/coins/taskcenter/signinlist", params)
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 端签到列表查询失败: {status_code}")
        return data

    def coin_home(self) -> dict[str, Any]:
        status_code, data, _ = self._get("/coins/taskcenter/home", self._common_params())
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 积分中心查询失败: {status_code}")
        return data

    def taskscore_save(
        self,
        task_id: Any | None = None,
        task_from: Any | None = None,
        label: str = "App任务上报",
    ) -> dict[str, Any]:
        params = self._common_params()
        task_id = task_id if task_id is not None else self.app_config.get("question_task_id") or "3434468751761026"
        task_from = (
            task_from
            if task_from is not None
            else self.app_config.get("question_task_from") or "task_sys_task_growth"
        )
        uk = self.app_config.get("uk")
        token = self.app_config.get("token")
        missing = [key for key, value in {"uk": uk, "token": token}.items() if not value]
        if missing:
            raise ValueError(f"App 任务上报缺少配置: {', '.join(missing)}")
        params.update(
            {
                "task_id": task_id,
                "task_from": task_from,
                "uk": uk,
                "token": token,
            }
        )
        status_code, data, text = self._get("/api/taskscore/tasksave", params)
        if status_code != 200 or not isinstance(data, dict):
            detail = data if data is not None else text[:200]
            raise ValueError(f"{label}失败: {status_code} {detail}")
        return data

    @staticmethod
    def taskscore_status(label: str, result: dict[str, Any]) -> str:
        errno = result.get("errno")
        error_code = result.get("error_code")
        message = result.get("errmsg") or result.get("error_msg") or result.get("show_msg")
        result_data = result.get("data")
        score = result.get("score")
        if score in (None, ""):
            score = result.get("points")
        if isinstance(result_data, dict):
            message = message or result_data.get("errmsg") or result_data.get("error_msg") or result_data.get("show_msg")
            if score in (None, ""):
                score = result_data.get("score")
            if score in (None, ""):
                score = result_data.get("points")

        details = []
        if score not in (None, ""):
            details.append(f"得分{score}")
        if message:
            details.append(str(message))
        suffix = f"（{'，'.join(details)}）" if details else ""

        if errno == 0 or error_code == 0 or errno == "0" or error_code == "0":
            return f"{label}: 成功{suffix}"
        if details:
            return f"{label}: 返回提示{suffix}"
        code = errno if errno is not None else error_code
        return f"{label}: 已请求，响应码{code if code is not None else '未知'}"

    def legacy_ad_watch_task(self) -> dict[str, Any] | None:
        ad_config = self.app_config.get("ad_watch")
        if isinstance(ad_config, dict):
            if not ad_config.get("enabled", False):
                return None
        elif self.app_config.get("ad_watch_enabled", False):
            ad_config = {}
        else:
            return None

        return {
            "enabled": True,
            "name": ad_config.get("name") or "App广告观看任务",
            "task_id": ad_config.get("task_id") or self.app_config.get("ad_watch_task_id") or "3434632741761030",
            "task_from": (
                ad_config.get("task_from")
                or self.app_config.get("ad_watch_task_from")
                or ["task_sys_task_growth"]
            ),
            "delay_seconds": ad_config.get("delay_seconds") or self.app_config.get("ad_watch_delay_seconds") or 0,
        }

    def taskscore_task_configs(self) -> list[dict[str, Any]]:
        raw_tasks = self.app_config.get("taskscore_tasks") or self.app_config.get("tasksave_tasks")
        tasks: list[dict[str, Any]] = []
        if isinstance(raw_tasks, list):
            for index, item in enumerate(raw_tasks, start=1):
                if not isinstance(item, dict):
                    continue
                if item.get("enabled", True) is False:
                    continue
                task = dict(item)
                task.setdefault("name", f"App任务上报{index}")
                tasks.append(task)
            return tasks

        legacy_task = self.legacy_ad_watch_task()
        return [legacy_task] if legacy_task else []

    def run_taskscore_task(self, task_config: dict[str, Any]) -> str:
        label = str(task_config.get("name") or "App任务上报")
        task_id = task_config.get("task_id")
        task_from = task_config.get("task_from") or ["task_sys_task_growth"]
        if not task_id:
            return f"{label}: 已跳过，缺少 task_id"

        delay_seconds = int(task_config.get("delay_seconds") or 0)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        result = self.taskscore_save(task_id=task_id, task_from=task_from, label=label)
        return self.taskscore_status(label, result)

    def run_taskscore_tasks(self) -> list[str]:
        results = []
        for task_config in self.taskscore_task_configs():
            label = str(task_config.get("name") or "App任务上报")
            try:
                results.append(self.run_taskscore_task(task_config))
            except Exception as exc:
                results.append(f"{label}: 执行失败: {exc}")
                LOGGER.exception("%s执行失败", label)
        return results

    def membership_user(self) -> dict[str, Any]:
        params = self._common_params()
        params["method"] = "query"
        status_code, data, _ = self._get("/rest/2.0/membership/user", params)
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 会员信息查询失败: {status_code}")
        level_info = data.get("level_info")
        return level_info if isinstance(level_info, dict) else {}

    def get_question(self) -> dict[str, Any]:
        status_code, data, _ = self._get("/act/v2/membergrowv2/getdailyquestion", self._common_params())
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 每日题目获取失败: {status_code}")
        question_info = data.get("data")
        return question_info if isinstance(question_info, dict) else {}

    def answer_question(self, ask_id: Any, answer: Any) -> dict[str, Any]:
        params = self._common_params()
        params.update({"ask_id": ask_id, "answer": answer})
        status_code, data, _ = self._get("/act/v2/membergrowv2/answerquestion", params)
        if status_code != 200 or not isinstance(data, dict):
            raise ValueError(f"App 每日答题提交失败: {status_code}")
        answer_info = data.get("data")
        return answer_info if isinstance(answer_info, dict) else {}

    def daily_question(self) -> str:
        question_info = self.get_question()
        ask_id = question_info.get("ask_id")
        answer = question_info.get("answer")
        question = question_info.get("question") or ""
        answer_status = question_info.get("answer_status")
        score = question_info.get("score")

        if not ask_id or answer is None:
            return "App每日答题: 未获取到题目"
        if answer_status == 1:
            return f"App每日答题: 已答题，得分{score or ''}，题目: {question}"

        answer_info = self.answer_question(ask_id, answer)
        answer_score = answer_info.get("score")
        show_msg = answer_info.get("show_msg") or ""
        return f"App每日答题: 提交完成，得分{answer_score or ''}{show_msg}，题目: {question}"

    @staticmethod
    def signin_status(signin_result: dict[str, Any], signin_info: dict[str, Any]) -> str:
        signed_today = signin_info.get("signed_today")
        if signed_today is True or signed_today == 1:
            return "已签到"

        errno = signin_result.get("errno")
        error_code = signin_result.get("error_code")
        errmsg = signin_result.get("errmsg") or signin_result.get("error_msg") or signin_result.get("show_msg")
        result_data = signin_result.get("data")
        if isinstance(result_data, dict):
            errmsg = errmsg or result_data.get("errmsg") or result_data.get("error_msg") or result_data.get("show_msg")
            if result_data.get("signed_today") is True or result_data.get("signed_today") == 1:
                return "已签到"

        if errno == 0 or error_code == 0:
            if errmsg:
                return f"请求成功，列表未确认（{errmsg}）"
            return "请求成功，列表未确认"
        if errmsg:
            return f"请求已返回提示: {errmsg}"
        return "已请求，待确认"

    def run(self) -> str:
        login_info = self.loginstatus()
        before_level_info = self.membership_user()
        is_growth = int(self.app_config.get("is_growth", 1))
        signin_result = self.coin_signin(is_growth=is_growth)
        signin_list_data = self.coin_signin_list(is_growth=is_growth)
        question_result = self.daily_question()
        taskscore_results = self.run_taskscore_tasks()
        after_level_info = self.membership_user()

        signin_result_info = signin_result.get("data") if isinstance(signin_result, dict) else {}
        signin_info = signin_list_data.get("data") if isinstance(signin_list_data, dict) else {}
        if not isinstance(signin_result_info, dict):
            signin_result_info = {}
        if not isinstance(signin_info, dict):
            signin_info = {}

        signin_days = signin_info.get("signin_days") or signin_result_info.get("signin_days")
        signin_status = self.signin_status(signin_result, signin_info)
        current_level = after_level_info.get("current_level")
        current_value = after_level_info.get("current_value")
        before_value = before_level_info.get("current_value")
        growth_delta = ""
        if isinstance(before_value, int) and isinstance(current_value, int):
            delta = current_value - before_value
            growth_delta = f"（本次变化{delta:+d}）"
        username = login_info.get("username") or ""
        lines = [
            f"App账号{username}",
            f"App连续签到: {signin_status}",
            f"App签到天数: {signin_days or ''}",
            question_result,
        ]
        lines.extend(taskscore_results)
        lines.extend(
            [
                f"当前会员等级: {current_level if current_level is not None else ''}",
                f"当前成长值: {current_value if current_value is not None else ''}{growth_delta}",
            ]
        )
        return "\n".join(lines)


def _direct_main() -> None:
    """Allow running this file directly without depending on the web CLI."""

    parser = argparse.ArgumentParser(description="百度网盘 App 端签到")
    parser.add_argument("-c", "--config", help="配置文件路径，默认自动查找 config.json")
    parser.add_argument("--timeout", type=int, default=30, help="请求超时时间，默认 30 秒")
    parser.add_argument("--log-file", default="logs/baiduwp_app.log", help="日志文件路径")
    parser.add_argument("--no-email", action="store_true", help="禁用邮箱通知")
    parser.add_argument("--test-email", action="store_true", help="只测试邮箱通知，不执行 App 签到")
    args = parser.parse_args()

    log_path = setup_logging(args.log_file)
    accounts, config_data, loaded_config_path = load_accounts(args.config)
    if not loaded_config_path:
        raise SystemExit("未找到配置文件，请使用 -c 指定 config.json")

    LOGGER.info("日志文件: %s", log_path)
    LOGGER.info("使用配置文件: %s", loaded_config_path)

    if args.test_email:
        email_config = normalize_email_config(config_data)
        if not email_config:
            raise SystemExit("邮箱通知未启用或未配置，请在 config.json 中配置 EMAIL.enabled=true")
        send_email(
            email_config,
            "百度网盘 App 签到邮箱测试",
            f"这是一封 App 端测试邮件。\n\n配置文件: {loaded_config_path}\n日志文件: {log_path}",
        )
        LOGGER.info("App 端邮箱测试完成")
        return

    if not accounts:
        raise SystemExit("config.json 中未找到 BAIDUWP 账号列表")

    content_list = []
    start_time = time.time()
    for index, account in enumerate(accounts, start=1):
        app_config = account.get("app")
        if not isinstance(app_config, dict) or not app_config.get("enabled", False):
            message = f"百度网盘账号 {index}\n未启用 App 端签到，已跳过"
            content_list.append(message)
            LOGGER.info(message)
            continue
        try:
            result = BaiduWPApp(
                cookie=str(account["cookie"]),
                app_config=app_config,
                timeout=args.timeout,
            ).run()
            content_list.append(f"百度网盘账号 {index}\n{result}")
            LOGGER.info("百度网盘账号 %s App 端执行完成\n%s", index, result)
            print(result)
        except Exception as exc:
            content_list.append(f"百度网盘账号 {index}\nApp 端执行失败: {exc}")
            LOGGER.exception("百度网盘账号 %s App 端执行失败", index)

    elapsed = int(time.time() - start_time)
    content_list.append(f"任务用时: {elapsed} 秒\n日志文件: {log_path}")
    content = "\n\n".join(content_list)

    email_config = normalize_email_config(config_data)
    if email_config and not args.no_email:
        try:
            send_email(email_config, "百度网盘 App 签到通知", content)
        except Exception:
            LOGGER.exception("邮箱通知发送失败")
    elif args.no_email:
        LOGGER.info("已通过 --no-email 禁用邮箱通知")
    else:
        LOGGER.info("未启用邮箱通知")

    LOGGER.info("App 端任务结束，用时 %s 秒", elapsed)


if __name__ == "__main__":
    _direct_main()
