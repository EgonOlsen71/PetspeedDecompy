@echo off
setlocal
set "ROOT=%~dp0.."
set "OUTPUT=%~dp0output"
if not exist "%ROOT%\pcode\*.prg" (
    echo No compiled PRG files found in "%ROOT%\pcode" 1>&2
    exit /b 1
)
if not exist "%OUTPUT%" mkdir "%OUTPUT%" || exit /b 1
set "FAILED=0"
for %%F in ("%ROOT%\pcode\*.prg") do (
    echo Decompiling %%~nxF
    python "%ROOT%\bin\decompile.py" "%%~fF" -o "%OUTPUT%\%%~nF.decompiled"
    if errorlevel 1 set "FAILED=1"
)
exit /b %FAILED%
