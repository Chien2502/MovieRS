-- Trigger tự động RLS không cần được thực thi bởi client Data API.
DO $$
BEGIN
    IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
        REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
    END IF;
END
$$;
