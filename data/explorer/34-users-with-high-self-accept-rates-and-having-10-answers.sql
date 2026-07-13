/* Users with high self-accept rates and having 10+ answers
Among users who accepted their own answer to their own question, what
fraction of all their questions were self-accepted - restricted to users
with more than 10 such self-accepts. */

WITH self_accepted AS (
    SELECT q.owner_user_id AS user_id, count(*) AS self_accept_count
    FROM posts q
        INNER JOIN posts a ON q.accepted_answer_id = a.id
    WHERE q.owner_user_id = a.owner_user_id
    GROUP BY q.owner_user_id
    HAVING count(*) > 10
),
question_counts AS (
    SELECT owner_user_id AS user_id, count(*) AS question_count
    FROM posts
    WHERE post_type_id = 1
    GROUP BY owner_user_id
)
SELECT
    u.id AS "User Link",
    round(100.0 * sa.self_accept_count / qc.question_count, 2) AS "SelfAnswerPercentage"
FROM self_accepted sa
    INNER JOIN question_counts qc ON qc.user_id = sa.user_id
    INNER JOIN users u ON u.id = sa.user_id
ORDER BY "SelfAnswerPercentage" DESC
LIMIT 100;
