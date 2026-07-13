/* Jon Skeet Comparison
Compares your answer scores against a rival user's, for every question you've
both answered.

Schema note: the original query is based off of OwnerUserId = 22656, Jon Skeet's
actual user id on stackoverflow.com */

\set user_id 15811
\set rival_user_id 449

WITH fights AS (
    SELECT
        my_answer.parent_id AS question,
        my_answer.score AS my_score,
        rival_answer.score AS rival_score
    FROM posts my_answer
        INNER JOIN posts rival_answer
            ON rival_answer.owner_user_id = :rival_user_id
            AND my_answer.parent_id = rival_answer.parent_id
    WHERE my_answer.owner_user_id = :user_id AND my_answer.post_type_id = 2
)
SELECT
    CASE
        WHEN my_score > rival_score THEN 'You win'
        WHEN my_score < rival_score THEN 'Rival wins'
        ELSE 'Tie'
    END AS "Winner",
    question AS "Post Link",
    my_score AS "My score",
    rival_score AS "Rival's score"
FROM fights;
