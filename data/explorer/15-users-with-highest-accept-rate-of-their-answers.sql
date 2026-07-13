/* Users with highest accept rate of their answers
Does not count self-answers.
Shows users with at least :min_answers answers. */

\set min_answers 50

SELECT
    u.id AS "User Link",
    count(*) AS "NumAnswers",
    count(*) FILTER (WHERE q.accepted_answer_id = a.id) AS "NumAccepted",
    (count(*) FILTER (WHERE q.accepted_answer_id = a.id) * 100.0 / count(*)) AS "AcceptedPercent"
FROM posts a
    INNER JOIN users u ON u.id = a.owner_user_id
    INNER JOIN posts q ON a.parent_id = q.id
WHERE q.owner_user_id <> u.id OR q.owner_user_id IS NULL /* no self answers */
GROUP BY u.id
HAVING count(*) >= :min_answers
ORDER BY "AcceptedPercent" DESC, "NumAnswers" DESC
LIMIT 100;
