# K7: Runbook развёртывания на Dental

Дата: 22.09.2026. Сервер `ssh Dental`, публичный IPv4 `5.42.98.110`. Список работавших контейнеров до развёртывания сохранён в `docs/dental-containers-before.txt` (22 контейнера).

## Состояние до развёртывания

- 22 работающих контейнера (список в `docs/dental-containers-before.txt`).
- Порт 8000 свободен.
- Память: 11 GiB всего, ~6.6 GiB доступно.
- Существующие контейнеры **не останавливались** — развёртывание под отдельным Compose project name `alfagen`.

## Развёртывание

Образ собран для `linux/amd64` (Dental — amd64; локальный Mac — arm64, поэтому нужен `--platform linux/amd64`).

**Важно:** задать общий `ALFAGEN_ENCRYPTION_KEY` для всех workers. Без него каждый worker генерирует свой эфемерный ключ, и кросс-worker демаскирование падает с 503. Также очистить Redis перед сменой ключа (старые записи зашифрованы старым ключом).

```bash
# 1. Собрать образ для amd64
docker build --platform linux/amd64 -t alfagen-pii-guard:0.1.0-amd64 .

# 2. Сохранить и передать на Dental
docker save alfagen-pii-guard:0.1.0-amd64 | gzip > /tmp/alfagen-pii-guard-amd64.tar.gz
scp /tmp/alfagen-pii-guard-amd64.tar.gz Dental:/tmp/

# 3. Загрузить образ и поднять сервис под отдельным project name
ssh Dental 'docker load -i /tmp/alfagen-pii-guard-amd64.tar.gz'
scp docker-compose.dental.yml Dental:/tmp/
ssh Dental 'cd /tmp && ALFAGEN_ENCRYPTION_KEY=<общий ключ> docker compose -p alfagen -f docker-compose.dental.yml up -d'
```

## Проверка

```bash
# Локально на Dental
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/process -H 'Content-Type: application/json' \
  -d '{"payload":"почта a@b.com","payload_id":"d-1"}'
# Внешний доступ
curl http://5.42.98.110:8000/health
```

## Откат (восстановление)

```bash
# Остановить только alfagen-проект (не трогает чужие контейнеры/volumes)
ssh Dental 'cd /tmp && docker compose -p alfagen -f docker-compose.dental.yml down'
# Удалить переданные файлы
ssh Dental 'rm -f /tmp/alfagen-pii-guard-amd64.tar.gz /tmp/docker-compose.dental.yml'
```

Существующие 22 контейнера не изменялись; их восстановление не требуется. `prune` и удаление чужих volumes не выполнялись.

## Ограничения

- Транспорт HTTP (без TLS) — честно обозначено; плановый вход — HTTPS по IP с self-signed сертификатом (D07).
- Профиль `evaluation-open` — временное исключение аутентификации для проверки, не банковский контур.
- Redis внутри Docker-сети, наружу не публикуется.
- Ключ шифрования эфемерный (не задан `ALFAGEN_ENCRYPTION_KEY`) — соответствия теряются при рестарте.