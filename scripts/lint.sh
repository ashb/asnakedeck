#!/bin/bash
set -euxo pipefail

poetry run cruft check
poetry run mypy --ignore-missing-imports asnakedeck/
poetry run isort --check --diff asnakedeck/ tests/
poetry run black --check asnakedeck/ tests/
poetry run flake8 asnakedeck/ tests/
poetry run safety check -i 39462 -i 40291
poetry run bandit -r asnakedeck/
