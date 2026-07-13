/* Users by Popular Question ratio
Among users with at least 10 "Popular Question" badges, the ratio of
Popular-Question badges to total questions asked. */

WITH popular_badges AS (
    SELECT user_id, count(*) AS badge_count
    FROM badges
    WHERE name = 'Popular Question'
    GROUP BY user_id
    HAVING count(*) >= 10
),
question_counts AS (
    SELECT owner_user_id AS user_id, count(*) AS question_count
    FROM posts
    WHERE post_type_id = 1
    GROUP BY owner_user_id
)
SELECT
    u.id AS "User Link",
    pb.badge_count AS "Popular Questions",
    qc.question_count AS "Total Questions",
    round(pb.badge_count::numeric / qc.question_count, 4) AS "Ratio"
FROM popular_badges pb
    INNER JOIN question_counts qc ON qc.user_id = pb.user_id
    INNER JOIN users u ON u.id = pb.user_id
ORDER BY "Ratio" DESC
LIMIT 100;
