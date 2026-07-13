/* Posts With Many Thank-You Answers
Questions that got more than one short (<= 200 char) "thank you"-style
answer

Schema note:
A leading-and-trailing wildcard pattern like '%hank%' can't use a plain
btree index, so this always seq-scans `posts` unless we use something like
a GIN trigram index (pg_trgm).

pg_trgm extenstion is templated from se_template and the index definition
lives in 00-setup.sql */

SELECT
    parent_id AS "Post Link",
    count(*) AS "Thank You Answers"
FROM posts
WHERE post_type_id = 2 AND length(body) <= 200 AND body ILIKE '%hank%'
GROUP BY parent_id
HAVING count(*) > 1
ORDER BY count(*) DESC;
