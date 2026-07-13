/* Total Questions and Answers per Month for the last 12
Total number of questions and answers for the last 12 months (in 30 day chunks),
counting back from the most recently created post in the dump. */

WITH latest AS (
    SELECT creation_date AS newest_post_date
    FROM posts
    ORDER BY id DESC
    LIMIT 1
),
ranges AS (
    SELECT
        bucket,
        newest_post_date - (bucket * interval '30 days') AS start,
        newest_post_date - ((bucket - 1) * interval '30 days') AS finish
    FROM latest, generate_series(1, 12) AS bucket
)
SELECT
    start,
    (SELECT count(*) FROM posts WHERE parent_id IS NULL AND creation_date BETWEEN r.start AND r.finish) AS "Total Questions",
    (SELECT count(*) FROM posts WHERE parent_id IS NOT NULL AND creation_date BETWEEN r.start AND r.finish) AS "Total Answers"
FROM ranges r
ORDER BY start DESC;
