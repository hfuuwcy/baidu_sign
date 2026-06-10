# 百度网盘会员签到

从原 `dailycheckin` 项目中提取的独立百度网盘会员成长值签到项目。

功能：

- 百度网盘会员成长值签到
- 每日答题
- 查询当前会员等级和成长值
- 支持多账号

## 安装

```bash
pip install -r requirements.txt
```

## 配置运行

复制示例配置：

```bash
copy config.example.json config.json
```

编辑 `config.json`：

```json
{
  "BAIDUWP": [
    {
      "cookie": "BDUSS=xxxxxx; STOKEN=xxxxxx; ..."
    }
  ]
}
```

运行：

```bash
python -m baiduwp_checkin
```

这个入口只运行网页端会员成长值签到和每日答题。

也可以直接传入 cookie：

```bash
python -m baiduwp_checkin --cookie "BDUSS=xxxxxx; STOKEN=xxxxxx; ..."
```

App 端使用独立入口：

```bash
python baiduwp_checkin/app.py
```

## 自动化任务

Windows 任务计划程序建议调用项目里的 `run.bat`：

```text
程序或脚本:
D:\haohan\dailycheckin\baiduwp_checkin\run.bat

起始于:
D:\haohan\dailycheckin\baiduwp_checkin
```

如果不想弹出命令行窗口，改用隐藏启动入口：

```text
程序或脚本:
C:\Windows\System32\wscript.exe

添加参数:
"D:\haohan\dailycheckin\baiduwp_checkin\run_hidden.vbs"

起始于:
D:\haohan\dailycheckin\baiduwp_checkin
```

`run.bat` 会先固定工作目录到脚本所在目录，再运行签到。日志会写入：

```text
D:\haohan\dailycheckin\baiduwp_checkin\logs\baiduwp_checkin.log
D:\haohan\dailycheckin\baiduwp_checkin\logs\runner.log
```

推荐任务设置：

- 常规：仅当用户登录时运行
- 常规：使用最高权限运行
- 设置：允许按需运行任务
- 设置：如果任务失败，每隔 10 分钟重新启动一次，尝试 3 次

默认情况下，正式签到会在任务启动后随机等待 0 到 5 分钟再执行，避免每天固定同一秒请求。日志中会记录实际等待秒数。

修改随机阈值：

```bash
python -m baiduwp_checkin --random-delay-minutes 10
```

临时禁用随机延迟：

```bash
python -m baiduwp_checkin --no-random-delay
```

## GitHub Actions

项目已包含 GitHub Actions 工作流，推送到 GitHub 后可以定时运行。

如果当前目录作为独立仓库根目录使用，工作流在 `.github/workflows/checkin.yml`。如果保留在父级 `dailycheckin` 仓库的 `baiduwp_checkin` 子目录中，仓库根目录下的 `.github/workflows/baiduwp-checkin.yml` 会进入本目录运行。

推荐在仓库的 `Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` 中新增：

- `BAIDUWP_CONFIG`：完整 JSON 配置，内容可以直接按 `config.example.json` 填写，支持多账号、邮箱通知和 App 参数。

也可以只新增：

- `BAIDUWP`：单个 Cookie 字符串，例如 `BDUSS=xxxxxx; STOKEN=xxxxxx; ...`
- `BAIDUWP`：或账号 JSON 列表，例如 `[{"cookie":"BDUSS=xxxxxx; STOKEN=xxxxxx; ..."}]`

如果同时配置了 `BAIDUWP_CONFIG` 和 `BAIDUWP`，会优先使用 `BAIDUWP_CONFIG`。

默认定时任务为每天北京时间 07:20 运行网页端入口：

```text
20 23 * * *
```

GitHub Actions 的 cron 使用 UTC，上面等同于北京时间第二天 07:20。也可以在 Actions 页面手动运行，并选择：

- `web`：执行 `python -m baiduwp_checkin --no-random-delay`
- `app`：执行 `python baiduwp_checkin/app.py`

如需让定时任务运行 App 端入口，可在 `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` 中新增变量：

```text
CHECKIN_MODE=app
```

不要把本地 `config.json` 提交到仓库；它已经被 `.gitignore` 忽略。

## 邮箱通知

在 `config.json` 中加入 `EMAIL` 配置，并把 `enabled` 改成 `true`：

```json
{
  "BAIDUWP": [
    {
      "cookie": "BDUSS=xxxxxx; STOKEN=xxxxxx; ..."
    }
  ],
  "EMAIL": {
    "enabled": true,
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "smtp_user": "your-email@qq.com",
    "smtp_password": "your-smtp-authorization-code",
    "from_addr": "your-email@qq.com",
    "to_addrs": [
      "receiver@example.com"
    ],
    "use_ssl": true,
    "use_tls": false,
    "subject": "百度网盘签到通知"
  }
}
```

QQ 邮箱、163 邮箱等通常要填写 SMTP 授权码，不是邮箱登录密码。

只测试邮箱通知，不执行签到：

```bash
python -m baiduwp_checkin --test-email
```

App 端使用同一个 `EMAIL` 配置：

```bash
python baiduwp_checkin/app.py --test-email
```

只测试百度网盘会员信息查询，不执行签到和答题：

```bash
python -m baiduwp_checkin --test-userinfo
```

成功时会输出：

```text
百度网盘账号 1: 当前会员等级{等级}，成长值{成长值}
```

## App 端签到

App 端签到来自 Reqable 抓包中的百度网盘 Android App 请求，目前实现：

```text
GET https://pan.baidu.com/coins/taskcenter/signin
GET https://pan.baidu.com/coins/taskcenter/signinlist
GET https://pan.baidu.com/rest/2.0/membership/user?method=query
GET https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion
GET https://pan.baidu.com/act/v2/membergrowv2/answerquestion
```

其中 `signin` 是 App 连续签到执行接口，`signinlist` 是签到日历/结果查询接口。
会员等级和成长值来自 `membership/user` 响应里的 `level_info.current_level` 和 `level_info.current_value`，不是积分中心的 `points_balance`。
其中 `getdailyquestion` 用于获取题目，响应里包含 `ask_id` 和 `answer`；`answerquestion` 用于提交答案。当前 HAR 中账号已经答过题，只抓到了获取题目的请求，但页面 JS 中确认提交接口就是 `answerquestion`。

配置示例：

```json
{
  "BAIDUWP": [
    {
      "cookie": "BDUSS=xxxxxx; STOKEN=xxxxxx; ...",
      "app": {
        "enabled": true,
        "z": "从 HAR 的 z 参数复制",
        "cuid": "从 HAR 的 cuid 参数复制",
        "devuid": "从 HAR 的 devuid 参数复制",
        "channel": "android_15_xxx_bd-netdisk_xxx",
        "version": "13.20.7",
        "versioncode": "4062",
        "coin_sign_task_id": "3434916321758720",
        "coin_sign_task_from": "task_sys_daily",
        "is_growth": 1,
        "question_task_id": "3434468751761026",
        "question_task_from": "task_sys_task_growth",
        "uk": "从 /api/taskscore/tasksave 的 uk 参数复制",
        "token": "从 /api/taskscore/tasksave 的 token 参数复制"
      }
    }
  ]
}
```

网页端每日答题提交后，如果成长值没有变化，脚本会在配置了 App 参数时尝试调用 `/api/taskscore/tasksave` 上报/完成每日一题成长值任务。

App 端代码在 `baiduwp_checkin/app.py`，和网页端入口分离。两个入口读取同一个 `config.json`，但 Web 入口只执行 Web 签到/答题，App 入口只执行 App 签到/答题。

## Cookie 获取

1. 登录百度网盘。
2. 访问 `https://pan.baidu.com/wap/svip/growth/task`。
3. 从浏览器开发者工具复制完整 Cookie，填入 `config.json`。

## 兼容配置

脚本会按顺序读取：

- `--config` 指定的配置文件
- 环境变量 `BAIDUWP_CONFIG` 或 `BAIDUWP_CONFIG_JSON` 中的完整 JSON 配置
- 当前目录下的 `config.json`
- 当前目录下的 `config/config.json`
- 环境变量 `BAIDUWP`

环境变量 `BAIDUWP` 支持两种格式：

```text
BDUSS=xxxxxx; STOKEN=xxxxxx; ...
```

或：

```json
[{"cookie": "BDUSS=xxxxxx; STOKEN=xxxxxx; ..."}]
```
