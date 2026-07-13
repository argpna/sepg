/* My comment score distribution
How many comments do I have at each score value? */

\set user_id 15811

SELECT
    count(*) AS comment_count,
    score
FROM comments
WHERE
    user_id = :user_id
GROUP BY
    score
ORDER BY
    score DESC;
