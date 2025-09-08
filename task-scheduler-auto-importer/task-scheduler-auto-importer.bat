@echo off
:: Set TaskFolder to the script's directory (e.g., C:\abc\schedule task\)
set "TaskFolder=%~dp0"

:: Extract the parent folder name (e.g., abc or qwe) for SchedulerFolder
for %%I in ("%TaskFolder%..") do set "ParentFolder=%%~nI"
set "SchedulerFolder=\%ParentFolder%"

set "User=corp\xxxxxxx"
set "PasswordFile=C:\xxxxxxx.ini"

:: Check if password file exists
if not exist "%PasswordFile%" (
    echo Error: Password file %PasswordFile% not found
    pause
    exit /b
)

:: Read password from file
set /p Password=<"%PasswordFile%"
if "%Password%"=="" (
    echo Error: Password file %PasswordFile% is empty
    pause
    exit /b
)

:: Create the folder in Task Scheduler
schtasks /create /tn "%SchedulerFolder%\DummyTask" /tr "cmd /c exit" /sc ONCE /st 00:00 /ru "%User%" /rp "%Password%" /f
if %ERRORLEVEL%==0 (
    echo Created folder %SchedulerFolder% successfully
) else (
    echo Failed to create folder %SchedulerFolder%. ErrorLevel: %ERRORLEVEL%
)

:: Delete the dummy task used to create the folder
schtasks /delete /tn "%SchedulerFolder%\DummyTask" /f

:: Import tasks from XML files in the current folder
for %%F in ("%TaskFolder%*.xml") do (
    schtasks /create /xml "%%F" /tn "%SchedulerFolder%\%%~nF" /ru "%User%" /rp "%Password%" /f
    if %ERRORLEVEL%==0 (
        echo Imported task %%~nF into %SchedulerFolder% successfully
        :: Verify the task's user
        schtasks /query /tn "%SchedulerFolder%\%%~nF" /fo list | findstr /i "Run As User"
    ) else (
        echo Failed to import task %%~nF. ErrorLevel: %ERRORLEVEL%
    )
)

:: Verify all tasks in the folder
echo.
echo Verifying tasks in %SchedulerFolder%...
schtasks /query /fo list /v /tn "%SchedulerFolder%\*" > task_details.txt
echo Task details saved to task_details.txt for review

pause