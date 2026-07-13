/* Elite Users: Those who hold > X% of all Reputation
Find the highest-rep users whose combined reputation is more than X% of the
total user reputation. Let's make Pareto proud. */

\set percent 10

WITH ranked AS (
    SELECT
        id,
        display_name,
        reputation,
        sum(reputation) OVER (ORDER BY reputation DESC, id) AS running_reputation,
        sum(reputation) OVER () AS total_reputation,
        row_number() OVER (ORDER BY reputation DESC, id) AS user_rank
    FROM users
)
SELECT
    reputation AS "CutoffReputation",
    id AS "CutoffID",
    display_name AS "CutoffDisplayName",
    total_reputation AS "TotalReputation",
    user_rank AS "NumberOfUsers"
FROM ranked
WHERE running_reputation >= total_reputation * (:percent / 100.0)
ORDER BY user_rank
LIMIT 1;
