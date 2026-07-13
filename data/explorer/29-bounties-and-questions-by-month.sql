/* Bounties and Questions by month
For each month, how many questions were asked and how many bounties were
awarded (count and total amount). */

WITH questions_by_month AS (
    SELECT
        EXTRACT(YEAR FROM creation_date)::int AS year,
        EXTRACT(MONTH FROM creation_date)::int AS month,
        count(*) AS questions
    FROM posts
    WHERE post_type_id = 1 /* 1 = Question */
    GROUP BY 1, 2
),
bounties_by_month AS (
    SELECT
        EXTRACT(YEAR FROM creation_date)::int AS year,
        EXTRACT(MONTH FROM creation_date)::int AS month,
        count(*) AS bounties,
        sum(bounty_amount) AS amount
    FROM votes
    WHERE vote_type_id = 9 /* 9 = BountyClose (bounty awarded) */
    GROUP BY 1, 2
)
SELECT
    coalesce(q.year, b.year) AS "Year",
    coalesce(q.month, b.month) AS "Month",
    b.bounties AS "Bounties",
    b.amount AS "Amount",
    q.questions AS "Questions"
FROM questions_by_month q
    FULL OUTER JOIN bounties_by_month b ON q.year = b.year AND q.month = b.month
ORDER BY "Year", "Month";
