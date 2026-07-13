/* My Money for Jam
My Non Community Wiki Posts that earn the most Passive Reputation.
Reputation gained in the first 15 days of a post is ignored, all reputation
after that is considered passive reputation. Post must be at least 60 days old. */

\set ignore_days 15
\set min_age_days 60
\set user_id 15811

SELECT max(creation_date) AS latest_date FROM posts \gset

WITH vote_stats AS (
    SELECT
        p.id AS post_id,
        sum(CASE WHEN v.vote_type_id = 2 THEN
            CASE WHEN p.parent_id IS NULL THEN 5 ELSE 10 END
            ELSE 0 END) AS up,
        sum(CASE WHEN v.vote_type_id = 3 THEN 2 ELSE 0 END) AS down,
        p.creation_date
    FROM votes v
        INNER JOIN posts p ON v.post_id = p.id
    WHERE v.vote_type_id IN (2, 3)
        AND p.owner_user_id = :user_id
        AND p.community_owned_date IS NULL
        AND (v.creation_date::date - p.creation_date::date) > :ignore_days
        AND (:'latest_date'::date - p.creation_date::date) > :min_age_days
    GROUP BY p.id, p.creation_date
)
SELECT
    post_id AS "Post Link",
    CAST(up - down AS decimal(10, 2)) / ((:'latest_date'::date - creation_date::date) - :ignore_days) AS "Passive Rep Per Day",
    (up - down) AS "Passive Rep",
    up AS "Passive Up Reputation",
    down AS "Passive Down Reputation",
    (:'latest_date'::date - creation_date::date) - :ignore_days AS "Days Counted"
FROM vote_stats
ORDER BY "Passive Rep Per Day" DESC
LIMIT 100;
