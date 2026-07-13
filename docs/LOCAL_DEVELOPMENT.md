# Local Development

## Prerequisites

- Python 3.10 for the current pinned dependency set.
- Docker and Docker Compose for the local MySQL service.
- A Discord bot token and Clash Royale API token only when running the real bot.

## Setup

Copy the example environment file:

```bash
cp .env.example .env
```

Fill in the required secret values in `.env`. Do not commit `.env`.

For local database-only work, the minimum values are:

```dotenv
MYSQL_DATABASE=clash_royale_manager
MYSQL_USER=clash_royale_manager
MYSQL_PASSWORD=<local password>
MYSQL_ROOT_PASSWORD=<local root password>
```

## Commands

Run dependency-light checks:

```bash
make test
make compile
```

Render the Docker Compose configuration:

```bash
make docker-config
```

Start the local stack:

```bash
make docker-up
```

Stop the local stack:

```bash
make docker-down
```

## Notes

- The MySQL container does not publish port 3306 to the host by default.
- `db_schema.sql` is mounted into the MySQL initialization directory for fresh database volumes.
- The current bot does not yet expose a health endpoint; `/bot_health` remains future work.
- The current pinned dependencies target Python 3.10. Dependency modernization should happen after fixtures and tests protect behavior.
