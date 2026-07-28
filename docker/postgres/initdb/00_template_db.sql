\set ON_ERROR_STOP on

SELECT format('CREATE DATABASE %I OWNER %I', 'se_template', current_user)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'se_template')
\gexec

\connect se_template

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- CREATE EXTENSION IF NOT EXISTS auto_explain;
-- CREATE EXTENSION IF NOT EXISTS pageinspect;
-- CREATE EXTENSION IF NOT EXISTS pg_prewarm;

\connect postgres

UPDATE pg_database
SET datistemplate = TRUE,
    datallowconn = FALSE
WHERE datname = 'se_template';
