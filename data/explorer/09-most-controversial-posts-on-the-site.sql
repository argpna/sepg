/* Most Controversial Posts On The Site
Posts (not closed, not community wiki) where downvotes exceed half the
upvotes, ordered by upvote count. */

WITH vote_stats AS (
    SELECT
        post_id,
        sum(CASE WHEN vote_type_id = 2 THEN 1 ELSE 0 END) AS up,
        sum(CASE WHEN vote_type_id = 3 THEN 1 ELSE 0 END) AS down
    FROM votes
    WHERE vote_type_id IN (2, 3)
    GROUP BY post_id
)
SELECT
    p.id AS "Post Link",
    vs.up,
    vs.down
FROM vote_stats vs
    INNER JOIN posts p ON vs.post_id = p.id
WHERE vs.down > (vs.up * 0.5)
    AND p.community_owned_date IS NULL
    AND p.closed_date IS NULL
ORDER BY vs.up DESC
LIMIT 100;
