DO $$ 
DECLARE 
    r RECORD; 
BEGIN 
    FOR r IN (
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
          AND (tablename ILIKE 'LiteLLM_%' OR tablename = '_prisma_migrations')
    ) LOOP 
        EXECUTE 'DROP TABLE IF EXISTS "' || r.tablename || '" CASCADE'; 
    END LOOP; 
END $$;
