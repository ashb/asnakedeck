#!/bin/bash
set -euxo pipefail

poetry run isort asnakedeck/ tests/
poetry run black asnakedeck/ tests/
