/* StackOverflow Rank and Percentile */

\set user_id 15811

WITH me AS (
    SELECT id, reputation FROM users WHERE id = :user_id
),
ranked AS (
    SELECT
        me.id,
        (SELECT count(*) FROM users WHERE reputation > me.reputation) + 1 AS ranking
    FROM me
)
SELECT
    id,
    ranking,
    CAST(ranking AS decimal(20, 5)) / (SELECT count(*) FROM users WHERE reputation > 100) AS percentile
FROM ranked;
