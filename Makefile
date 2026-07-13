.PHONY: compile docker-config docker-down docker-up init-db test

compile:
	python3 -m py_compile ClashRoyaleManager/config/settings.py ClashRoyaleManager/utils/clash_utils.py ClashRoyaleManager/utils/db_utils.py ClashRoyaleManager/utils/verification_utils.py ClashRoyaleManager/utils/war_math.py ClashRoyaleManager/commands/update_commands.py ClashRoyaleManager/__main__.py

test:
	python3 -m unittest discover -s tests

docker-config:
	docker compose config

docker-up:
	docker compose up --build

docker-down:
	docker compose down

init-db:
	./scripts/init_db.sh
