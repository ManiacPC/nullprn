@echo off
REM ---------------------------------------------------------------------------
REM build.bat - build NullPrn.exe with Nuitka and print its SHA-256.
REM Run from the project root. Uses the local .venv if present.
REM ---------------------------------------------------------------------------
setlocal

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [1/3] Generating icon (NullPrn.ico)...
"%PY%" make_ico.py || goto :error

echo [2/3] Building NullPrn.exe with Nuitka...
"%PY%" -m nuitka nullprn_tray.py ^
    --onefile ^
    --windows-console-mode=disable ^
    --include-module=pystray._win32 ^
    --windows-icon-from-ico=NullPrn.ico ^
    --output-filename=NullPrn.exe ^
    --assume-yes-for-downloads || goto :error

echo [3/3] SHA-256 of NullPrn.exe:
powershell -NoProfile -Command "(Get-FileHash .\NullPrn.exe -Algorithm SHA256).Hash"

echo.
echo Done: NullPrn.exe
endlocal
exit /b 0

:error
echo.
echo BUILD FAILED (error %errorlevel%).
endlocal
exit /b 1
