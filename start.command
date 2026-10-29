#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python run_local.py
