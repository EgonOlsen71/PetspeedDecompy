@echo off
python "%~dp0bin\decompile.py" --gui
exit /b %ERRORLEVEL%
