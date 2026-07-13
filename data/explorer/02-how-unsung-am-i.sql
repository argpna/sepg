/* How Unsung am I?
Zero and non-zero accepted count. Self-accepted answers do not count.

The user's own answers are a much smaller set than all questions, so start
the scan from the (owner_user_id, post_type_id) index and join back to the
parent question, instead of scanning all questions to reach a. */

\set user_id 15811

SELECT
    count(a.id) AS accepted_answers,
    sum(CASE WHEN a.score = 0 THEN 0 ELSE 1 END) AS scored_answers,
    sum(CASE WHEN a.score = 0 THEN 1 ELSE 0 END) AS unscored_answers,
    sum(CASE WHEN a.score = 0 THEN 1 ELSE 0 END) * 1000 / count(a.id) / 10.0 AS percentage_unscored
FROM posts a
    INNER JOIN posts q ON q.id = a.parent_id
WHERE
    a.community_owned_date IS NULL
    AND a.owner_user_id = :user_id
    AND a.post_type_id = 2
    AND q.owner_user_id != :user_id
    AND q.accepted_answer_id = a.id;
