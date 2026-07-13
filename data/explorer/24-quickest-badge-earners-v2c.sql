/* Quickest badge earners V2c
For a given badge, how many days after joining did each earner win it -
accounting for the fact that some badges aren't introduced until a certain
date, so early members couldn't have earned it any sooner than that date
(they aren't applied retroactively). */

\set badge_name 'Guru'

WITH first_time AS (
    SELECT min(date)::date AS first_time FROM badges WHERE name = :'badge_name'
),
badge_earners AS (
    SELECT
        u.id AS user_id,
        u.creation_date AS member_since,
        b.date AS date_won,
        1 + (b.date::date - u.creation_date::date) AS days_membership
    FROM badges b
        INNER JOIN users u ON b.user_id = u.id
    WHERE b.name = :'badge_name'
)
SELECT
    be.user_id AS "User Link",
    be.member_since AS "Member Since",
    be.date_won AS "Date Won",
    be.days_membership AS "DaysMembership",
    (be.date_won::date - ft.first_time) AS "DaysSince1st"
FROM badge_earners be, first_time ft
ORDER BY be.days_membership ASC;
