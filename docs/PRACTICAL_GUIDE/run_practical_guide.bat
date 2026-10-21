@echo off
REM ============================================================
REM PlanX Urban Resilience - Practical Guide Runner
REM ============================================================
REM Runs the headless screenshot generator in the OSGeo4W / QGIS Python
REM environment, verifies the captured results, rebuilds the interactive and
REM print editions, and cleans the scratch directory.
REM
REM Prerequisites:
REM - QGIS 3.44 LTR or 4.2 installed via OSGeo4W
REM - The PlanX Urban Resilience plugin source in this repository
REM
REM Usage:
REM   run_practical_guide.bat --all
REM   run_practical_guide.bat --algo urban_heat_comfort_risk
REM   run_practical_guide.bat --list
REM   run_practical_guide.bat --verify
REM ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"
set "RUNNER_SCRIPT=%SCRIPT_DIR%practical_guide_runner.py"
set "QGIS_PYTHON="

if exist "C:\OSGeo4W\bin\python-qgis-ltr.bat" (
    set "QGIS_PYTHON=C:\OSGeo4W\bin\python-qgis-ltr.bat"
) else if exist "C:\OSGeo4W64\bin\python-qgis-ltr.bat" (
    set "QGIS_PYTHON=C:\OSGeo4W64\bin\python-qgis-ltr.bat"
) else if exist "C:\Program Files\QGIS 3.44\bin\python-qgis-ltr.bat" (
    set "QGIS_PYTHON=C:\Program Files\QGIS 3.44\bin\python-qgis-ltr.bat"
) else if exist "C:\Program Files\QGIS 4.2\bin\python-qgis.bat" (
    set "QGIS_PYTHON=C:\Program Files\QGIS 4.2\bin\python-qgis.bat"
) else (
    echo [ERROR] QGIS Python not found!
    echo Install QGIS via OSGeo4W, or make sure python-qgis-ltr.bat is reachable.
    pause
    exit /b 1
)

echo [INFO] Using QGIS Python: %QGIS_PYTHON%

if not exist "%RUNNER_SCRIPT%" (
    echo [ERROR] Runner script not found: %RUNNER_SCRIPT%
    pause
    exit /b 1
)

if "%~1"=="" goto :usage
if /i "%~1"=="--verify" goto :verify
if /i "%~1"=="--list" goto :run
if /i "%~1"=="--all" goto :run
if /i "%~1"=="--algo" goto :run
goto :usage

:usage
echo Usage: run_practical_guide.bat [--all | --algo ALGO_ID | --list | --verify]
echo.
echo Examples:
echo   run_practical_guide.bat --all
echo   run_practical_guide.bat --algo urban_heat_comfort_risk
echo   run_practical_guide.bat --list
echo   run_practical_guide.bat --verify
pause
exit /b 0

:verify
echo [INFO] Verifying the captured results...
call "%QGIS_PYTHON%" "%SCRIPT_DIR%manifest\verify_signals.py"
if errorlevel 1 goto :verify_failed
echo.
echo [SUCCESS] All key result fields carry real signal.
pause
exit /b 0

:verify_failed
echo.
echo [ERROR] Result verification failed.
pause
exit /b 1

:audit_failed
echo.
echo [ERROR] The reference manual drifted from the live provider.
echo Fix the manual, or regenerate the parameter tables from the provider.
pause
exit /b 1

:run
echo [INFO] Running the practical guide generator...
echo.
call "%QGIS_PYTHON%" "%RUNNER_SCRIPT%" %*
if errorlevel 1 goto :run_failed

echo.
echo [INFO] Verifying the captured results...
call "%QGIS_PYTHON%" "%SCRIPT_DIR%manifest\verify_signals.py"
if errorlevel 1 goto :verify_failed

echo.
echo [INFO] Auditing the reference manual against the live provider...
call "%QGIS_PYTHON%" "%SCRIPT_DIR%manifest\audit_manual_drift.py"
if errorlevel 1 goto :audit_failed

echo.
echo [INFO] Rebuilding the guide...
REM the builders are plain Python, but they must run with the SAME interpreter
REM as the runner: the OSGeo4W wrapper exports a PYTHONPATH that would break a
REM different Python with an "SRE module mismatch".
call "%QGIS_PYTHON%" "%SCRIPT_DIR%build_final.py"
if errorlevel 1 goto :build_failed
call "%QGIS_PYTHON%" "%SCRIPT_DIR%build_static.py"
if errorlevel 1 goto :build_failed
goto :clean

:clean
echo.
echo [INFO] Cleaning the scratch directory...
call "%QGIS_PYTHON%" "%RUNNER_SCRIPT%" --clean
echo.
echo [SUCCESS] Practical guide generation complete!
echo Open: %SCRIPT_DIR%practical_guide.html
pause
exit /b 0

:build_failed
echo.
echo [ERROR] Could not rebuild the guide.
pause
exit /b 1

:run_failed
echo.
echo [ERROR] The runner failed.
pause
exit /b 1
