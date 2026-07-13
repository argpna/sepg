/* Top Users by Number of Bounties Won
For each user, how many bounties they've won - i.e. how many of their posts
received a bounty-awarded vote. */

SELECT
    p.owner_user_id AS "User Link",
    count(*) AS "BountiesWon"
FROM votes v
    INNER JOIN posts p ON v.post_id = p.id
WHERE v.vote_type_id = 9
GROUP BY p.owner_user_id
ORDER BY "BountiesWon" DESC
LIMIT 100;
