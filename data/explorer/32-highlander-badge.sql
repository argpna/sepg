/* Highlander badge
Answers that scored more than 5, where the parent question scored more than
3, had exactly one answer, and accepted this one - "there can be only one"
answer, and it dominated. */

SELECT
    p.owner_user_id AS "User Link",
    p.id AS "Post Link",
    p.score AS "Score"
FROM posts p
    INNER JOIN posts q ON q.id = p.parent_id
WHERE p.post_type_id = 2
    AND p.score > 5
    AND q.score > 3
    AND q.answer_count = 1
    AND q.accepted_answer_id = p.id
ORDER BY p.score DESC
LIMIT 25;
