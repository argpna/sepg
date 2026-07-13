/* Low Views, High Votes, Yet Unanswered
Questions with a score above 2 that have been viewed but have no accepted answer,
ordered by fewest views first - these are the "why hasn't anyone answered this" posts. */

SELECT
    id AS "Post Link",
    score AS "Score",
    view_count AS "ViewCount"
FROM posts
WHERE score > 2
    AND view_count > 0
    AND parent_id IS NULL
    AND accepted_answer_id IS NULL
ORDER BY view_count ASC
LIMIT 500;
