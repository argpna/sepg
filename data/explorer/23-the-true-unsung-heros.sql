/* The True Unsung Heros
Users whose accepted answers are disproportionately zero-scored: they answer
someone else's question, get accepted, but rarely get upvoted for it. Ranked
by the fraction of their accepted answers that scored zero. */

\set min_zero_score_answers 10

WITH accepted_answers AS (
    SELECT
        a.owner_user_id,
        count(*) FILTER (WHERE a.score <> 0) AS non_zero_score_answers,
        count(*) FILTER (WHERE a.score = 0) AS zero_score_answers
    FROM posts q
        INNER JOIN posts a ON a.id = q.accepted_answer_id
    WHERE a.community_owned_date IS NULL
        AND a.owner_user_id IS NOT NULL
        AND a.owner_user_id <> coalesce(q.owner_user_id, -1)
    GROUP BY a.owner_user_id
    HAVING count(*) FILTER (WHERE a.score = 0) > :min_zero_score_answers
)
SELECT
    aa.owner_user_id AS "User Link",
    aa.non_zero_score_answers AS "Non Zero Score Answers",
    aa.zero_score_answers AS "Zero Score Answers",
    u.reputation AS "Reputation"
FROM accepted_answers aa
    INNER JOIN users u ON u.id = aa.owner_user_id
ORDER BY (aa.zero_score_answers + 0.0) / (aa.zero_score_answers + aa.non_zero_score_answers + 0.0) DESC;
