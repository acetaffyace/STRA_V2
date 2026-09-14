@echo off
if /I "%~1"=="Username for 'https://github.com':" (echo %GIT_ASKPASS_USERNAME%) else (echo %GIT_ASKPASS_PASSWORD%)
