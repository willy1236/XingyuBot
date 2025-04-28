poetry run python update.py
poetry lock
poetry install --no-root
cd ../
poetry run python main.py