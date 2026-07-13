/* Rising stars, top 50 users ordered on rep per day
Looking at the duration from when a user created their account till the last
post in the dump, who gained the most rep per day. */

\set min_reputation 5000

WITH end_date AS (
    SELECT max(creation_date) AS end_date FROM posts
)
SELECT
    u.id AS "User Link",
    u.reputation AS "Reputation",
    (ed.end_date::date - u.creation_date::date) AS "Days",
    u.reputation / (ed.end_date::date - u.creation_date::date) AS "RepPerDays"
FROM users u, end_date ed
WHERE u.reputation > :min_reputation
ORDER BY "RepPerDays" DESC
LIMIT 50;
