/* High Standards: Top 100 Users That Rarely Upvote
Users with high reputation relative to how few upvotes they've cast - a rough proxy
for "hard to impress" */

\set min_rep 1000
\set min_upvotes 10

SELECT
    id AS "User Link",
    round((100.0 * (reputation / 10)) / (up_votes + 1), 2) AS "Ratio %",
    reputation AS "Rep",
    up_votes AS "+ Votes",
    down_votes AS "- Votes"
FROM users
WHERE reputation > :min_rep
    AND up_votes > :min_upvotes
ORDER BY "Ratio %" DESC
LIMIT 100;
