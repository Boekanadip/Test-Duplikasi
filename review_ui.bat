@echo off
REM Launch the entity-resolution review UI (4-tab: Input/Review/Hasil/Retrain).
REM Usage:
REM   review_ui.bat              -- default DB
REM   review_ui.bat custom.db    -- custom label DB
set DB=%~1
if "%DB%"=="" set DB=data\processed\review_labels.db
python -m streamlit run app\review_app.py -- --db "%DB%"