/* What is my accepted answer percentage rate
On average, how often are the answers I give accepted? */

\set user_id 15811

SELECT
    count(*)::float
        / (SELECT count(*) FROM posts WHERE owner_user_id = :user_id AND post_type_id = 2)
        * 100 AS accepted_percentage
FROM posts a
    INNER JOIN posts q ON q.id = a.parent_id AND q.accepted_answer_id = a.id
WHERE a.owner_user_id = :user_id
    AND a.post_type_id = 2;
