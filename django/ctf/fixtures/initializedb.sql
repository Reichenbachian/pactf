-- SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = 'TARGET_DB' AND pid <> pg_backend_pid(); -- Terminate existing connections to allow the drop to go through
DROP DATABASE pactf;
CREATE DATABASE pactf;
CREATE USER pactf_user WITH PASSWORD 'pactf_user_password';
ALTER ROLE pactf_user SET client_encoding TO 'utf8';
ALTER ROLE pactf_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE pactf_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE pactf TO pactf_user;
-- ALTER USER pactf_user CREATEDB; -- so we can use `manage.py reset_db`
