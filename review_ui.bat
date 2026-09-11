"@echo off
REM Launch the entity-resolution review UI.
REM Usage:
REM   review_ui.bat                                    -- default complex_hard queue
REM   review_ui.bat path\to\review_queue.csv path\to\customers.csv
set QUEUE=%~1
set CUST=%~2
if "%QUEUE%"=="" set QUEUE=data\processed\complex_hard_merge\review_queue.csv
if "%CUST%"=="" set CUST=data\processed\_complex_hard_500.csv
python -m streamlit run app\review_app.py -- --input "%QUEUE%" --customers "%CUST%"