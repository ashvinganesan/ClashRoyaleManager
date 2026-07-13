#!/usr/bin/env sh
set -eu

python3 -m py_compile \
  ClashRoyaleManager/config/settings.py \
  ClashRoyaleManager/utils/clash_utils.py \
  ClashRoyaleManager/utils/db_utils.py \
  ClashRoyaleManager/__main__.py

python3 -m unittest discover -s tests
