/* Find interesting unanswered questions
Looks at unanswered questions in your top 20 tags and sorts them by a combined
weight which takes into account: score, asker's reputation, and how well you
do on that particular tag.

Schema note: PostTags is not part of the public XML dump - reconstructed as
the post_tags materialized view in 00-setup.sql. */

\set user_id 15811

WITH top_tags AS (
    SELECT
        pt.tag_id,
        count(*) AS up_votes
    FROM post_tags pt
        INNER JOIN posts a ON a.parent_id = pt.post_id
        INNER JOIN votes v ON v.post_id = a.id AND v.vote_type_id = 2
    WHERE a.owner_user_id = :user_id
    GROUP BY pt.tag_id
    ORDER BY up_votes DESC
    LIMIT 20
),
unanswered AS (
    SELECT q.id
    FROM posts q
    WHERE q.parent_id IS NULL
        AND q.community_owned_date IS NULL
        AND q.closed_date IS NULL
        AND q.accepted_answer_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM posts a WHERE a.parent_id = q.id AND a.score > 0
        )
)
SELECT
    un.id AS post_id,
    sum(t.up_votes) / 10.0 + us.reputation / 200.0 + p.score * 100 AS weight
FROM unanswered un
    INNER JOIN posts p ON p.id = un.id
    INNER JOIN post_tags pt ON pt.post_id = un.id
    INNER JOIN top_tags t ON t.tag_id = pt.tag_id
    INNER JOIN users us ON us.id = p.owner_user_id
GROUP BY un.id, us.reputation, p.score
ORDER BY weight DESC
LIMIT 2000;
