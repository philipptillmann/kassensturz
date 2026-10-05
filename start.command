#!/bin/zsh
cd "${0:A:h}"
docker compose up -d --build
