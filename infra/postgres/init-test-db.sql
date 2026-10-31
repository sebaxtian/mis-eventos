SELECT 'CREATE DATABASE mis_eventos_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mis_eventos_test')\gexec

\c mis_eventos
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\c mis_eventos_test
CREATE EXTENSION IF NOT EXISTS pg_trgm;
