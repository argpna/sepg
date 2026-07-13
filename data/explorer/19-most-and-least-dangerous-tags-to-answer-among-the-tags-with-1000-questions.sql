/* Most and Least Dangerous Tags to Answer (among tags with >= 1000 questions)

For tags with at least 1000 questions, the ratio of downvotes to upvotes their
answers receive - a proxy for how "dangerous" it is to answer in that tag.

Schema note: PostTags is not part of the public XML dump - reconstructed as
the post_tags materialized view in 00-setup.sql. */

\set min_questions 1000

WITH tag_question_counts AS (
    SELECT tag_id, count(*) AS num_questions
    FROM post_tags
    GROUP BY tag_id
    HAVING count(*) >= :min_questions
),
answer_votes AS (
    SELECT
        pt.tag_id,
        count(*) FILTER (WHERE v.vote_type_id = 2) AS upvotes,
        count(*) FILTER (WHERE v.vote_type_id = 3) AS downvotes
    FROM post_tags pt
        INNER JOIN tag_question_counts tqc ON tqc.tag_id = pt.tag_id
        INNER JOIN posts pa ON pa.parent_id = pt.post_id
        INNER JOIN votes v ON v.post_id = pa.id AND v.vote_type_id IN (2, 3)
    GROUP BY pt.tag_id
)
SELECT
    t.tag_name AS "Tags",
    av.upvotes AS "Upvotes",
    av.downvotes AS "Downvotes",
    round(100.0 * av.downvotes / NULLIF(av.upvotes, 0), 2) AS "D/U ratio"
FROM answer_votes av
    INNER JOIN tags t ON t.id = av.tag_id
ORDER BY 4 DESC;
