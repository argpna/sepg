/* How many upvotes do I have for each tag?
how long before I get tag badges?

Schema note: PostTags is not part of the public XML dump. Indexes/views this
query relies on are created by 00-setup.sql. */

/* Most popular user_id on vi - 51
Most popular user_id on askubuntu - 15811 */

\set user_id 15811

WITH post_tags AS (
    SELECT
        p.id AS post_id,
        t.id AS tag_id,
        t.tag_name
    FROM posts p
        CROSS JOIN LATERAL unnest(string_to_array(btrim(p.tags, '|'), '|')) AS tag_name(tag_name)
        INNER JOIN tags t ON t.tag_name = tag_name.tag_name
    WHERE p.tags IS NOT NULL AND p.tags <> ''
)
SELECT
    t.tag_name,
    COUNT(*) AS up_votes
FROM tags t
    INNER JOIN post_tags pt ON pt.tag_id = t.id
    INNER JOIN posts p ON p.parent_id = pt.post_id
    INNER JOIN votes v ON v.post_id = p.id AND v.vote_type_id = 2
WHERE
    p.owner_user_id = :user_id
GROUP BY t.tag_name
ORDER BY up_votes DESC;

/* Alternatively, use the post_tags materialized view from 00-setup.sql
instead of unnesting posts.tags inline. */

\set user_id 15811

SELECT
    pt.tag_name,
    COUNT(*) AS up_votes
FROM posts p
    INNER JOIN post_tags pt ON pt.post_id = p.parent_id
    INNER JOIN votes v ON v.post_id = p.id AND v.vote_type_id = 2
WHERE p.owner_user_id = :user_id
GROUP BY pt.tag_name
ORDER BY up_votes DESC;