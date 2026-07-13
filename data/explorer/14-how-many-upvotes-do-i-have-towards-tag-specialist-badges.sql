/* How many upvotes do I have towards tag specialist badges?
Upvotes on my own answers, grouped by the tag of the question I answered.

Schema note: PostTags is not part of the public XML dump - reconstructed as the
post_tags materialized view in 00-setup.sql */

\set user_id 15811

SELECT
    pt.tag_name AS "TagName",
    count(*) AS "UpVotes"
FROM post_tags pt
    INNER JOIN posts a ON a.parent_id = pt.post_id
    INNER JOIN votes v ON v.post_id = a.id AND v.vote_type_id = 2
WHERE a.owner_user_id = :user_id
    AND a.community_owned_date IS NULL
GROUP BY pt.tag_name
ORDER BY "UpVotes" DESC
LIMIT 20;
