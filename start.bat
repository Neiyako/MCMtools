@echo off
REM MCMtools one-click start (Windows).
REM
REM NOTE: this file is deliberately ASCII-only, and it switches the console to
REM UTF-8 before anything runs. A .bat file is read by cmd.exe in the *system*
REM codepage -- on Chinese Windows that is GBK, not UTF-8 -- so Chinese text
REM stored inside this file renders as mojibake. The Chinese messages the user
REM actually reads come from the Python side, which controls its own encoding.
chcp 65001 >nul 2>nul

setlocal
cd /d "%~dp0"

REM Prefer the py launcher (Microsoft recommended entry point): it picks the
REM newest Python 3 by itself.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0start" %*
  goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0start" %*
  goto :done
)

echo.
echo   Python was not found.
echo.
echo   MCMtools needs Python 3.9 or newer.
echo   Download it from https://www.python.org/downloads/
echo   and be sure to tick "Add Python to PATH" during setup,
echo   then run this file again.
echo.
pause

:done
REM Keep the window open on failure so the error is readable; a normal exit
REM (including Ctrl-C) closes it.
if errorlevel 1 (
  echo.
  echo   Startup failed with code %errorlevel%.
  echo.
  pause
)
endlocal
