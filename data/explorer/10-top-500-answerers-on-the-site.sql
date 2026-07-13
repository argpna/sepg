/* Top 500 Answerers On The Site
Users with more than 10 answers (not community wiki, not closed), ranked by
average answer score. */

SELECT
    u.id AS "User Link",
    count(p.id) AS "Answers",
    CAST(avg(CAST(score AS float)) AS numeric(6, 2)) AS "Average Answer Score"
FROM posts p
    INNER JOIN users ON u.id = owner_user_id
WHERE post_type_id = 2 AND community_owned_date IS NULL AND closed_date IS NULL
GROUP BY u.id
HAVING count(p.id) > 10
ORDER BY "Average Answer Score" DESC
LIMIT 500;
