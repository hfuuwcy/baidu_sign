@echo off
setlocal

cd /d "%~dp0"

if not exist logs mkdir logs

python -m baiduwp_checkin --log-file logs\baiduwp_checkin.log >> logs\runner.log 2>&1
