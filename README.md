# 百度网盘网页端会员签到

这是百度网盘网页端会员成长值签到项目，只负责网页端任务：

- 会员成长值签到
- 每日答题
- 查询当前会员等级和成长值
- 支持多账号
- 支持独立邮箱通知配置

## 安装

```bash
pip install -r requirements.txt
```

## 本地配置

复制账号配置示例：

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

邮箱配置单独放在 `email.json`：

```bash
copy email.example.json email.json
```

编辑 `email.json`，并把 `enabled` 改成 `true`：

```json
{
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
```

QQ 邮箱、163 邮箱等通常要填写 SMTP 授权码，不是邮箱登录密码。

## 运行

```bash
python -m baiduwp_checkin
```

直接传入 Cookie：

```bash
python -m baiduwp_checkin --cookie "BDUSS=xxxxxx; STOKEN=xxxxxx; ..."
```

指定配置文件：

```bash
python -m baiduwp_checkin --config config.json --email-config email.json
```

只测试邮箱通知：

```bash
python -m baiduwp_checkin --test-email
```

只测试会员信息查询：

```bash
python -m baiduwp_checkin --test-userinfo
```

成功时会输出：

```text
百度网盘账号 1: 当前会员等级{等级}，成长值{成长值}
```

## GitHub Actions

工作流在 `.github/workflows/checkin.yml`，默认每天北京时间 07:20 运行网页端入口：

```text
20 23 * * *
```

GitHub Actions 的 cron 使用 UTC，上面等同于北京时间第二天 07:20。

在仓库的 `Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` 中新增：

- `BAIDUWP_CONFIG`：完整账号 JSON，内容可以按 `config.example.json` 填写。
- `BAIDUWP_EMAIL_CONFIG`：完整邮箱 JSON，内容可以按 `email.example.json` 填写。

也可以只新增：

- `BAIDUWP`：单个 Cookie 字符串，例如 `BDUSS=xxxxxx; STOKEN=xxxxxx; ...`
- `BAIDUWP`：或账号 JSON 列表，例如 `[{"cookie":"BDUSS=xxxxxx; STOKEN=xxxxxx; ..."}]`

如果同时配置了 `BAIDUWP_CONFIG` 和 `BAIDUWP`，会优先使用 `BAIDUWP_CONFIG`。

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

日志会写入：

```text
D:\haohan\dailycheckin\baiduwp_checkin\logs\baiduwp_checkin.log
D:\haohan\dailycheckin\baiduwp_checkin\logs\runner.log
```

默认情况下，正式签到会在任务启动后随机等待 0 到 5 分钟再执行，避免每天固定同一秒请求。

修改随机阈值：

```bash
python -m baiduwp_checkin --random-delay-minutes 10
```

临时禁用随机延迟：

```bash
python -m baiduwp_checkin --no-random-delay
```

## Cookie 获取

1. 登录百度网盘。
2. 访问 `https://pan.baidu.com/wap/svip/growth/task`。
3. 从浏览器开发者工具复制完整 Cookie，填入 `config.json` 或 GitHub Secret。


## 配置读取顺序

账号配置会按顺序读取：

- `--config` 指定的配置文件
- 环境变量 `BAIDUWP_CONFIG` 或 `BAIDUWP_CONFIG_JSON`
- 当前目录下的 `config.json`
- 当前目录下的 `config/config.json`
- 环境变量 `BAIDUWP`

邮箱配置会按顺序读取：

- `--email-config` 指定的配置文件
- 环境变量 `BAIDUWP_EMAIL_CONFIG` 或 `BAIDUWP_EMAIL_CONFIG_JSON`
- 当前目录下的 `email.json`
- 当前目录下的 `config/email.json`

不要把本地 `config.json` 或 `email.json` 提交到仓库；它们已经被 `.gitignore` 忽略。
