/* Vanity search: links to my website posted by other people during last 2 months
Posts/comments (not authored by me) mentioning my website URL, from the most
recent 2 months of activity.

GETDATE() is the server's wall clock. sepg loads a frozen, long-past dump,
so "now() - 2 months" would fall after every row in the dump and always
return zero rows. Anchored instead to the dump's own last activity
max(creation_date) across posts and comments. */

\set user_id 30633

WITH my_site AS (
    SELECT id, rtrim(regexp_replace(website_url, '^https?://', ''), '/') AS site
    FROM users
    WHERE id = :user_id
),
dump_end AS (
    SELECT greatest(
        (SELECT max(last_activity_date) FROM posts),
        (SELECT max(creation_date) FROM comments)
    ) AS end_date
)
SELECT p.id AS "Post Link", p.last_activity_date AS "Last Activity"
FROM (
    SELECT p.id
    FROM posts p, my_site ms, dump_end d
    WHERE p.body LIKE '%' || ms.site || '%' ESCAPE '!'
        AND p.owner_user_id <> ms.id
        AND p.last_activity_date >= d.end_date - interval '2 months'
        AND ms.site <> ''
    UNION
    SELECT c.post_id
    FROM comments c, my_site ms, dump_end d
    WHERE c.text LIKE '%' || ms.site || '%' ESCAPE '!'
        AND c.user_id <> ms.id
        AND c.creation_date >= d.end_date - interval '2 months'
        AND ms.site <> ''
) q
INNER JOIN posts p ON p.id = q.id
ORDER BY p.last_activity_date DESC;
