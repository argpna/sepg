/* Most Popular StackOverflow Tags In May 2010
For tags with more than 800 posts overall, rank them both by post count within
May 2010 and by total post count, side by side.

Schema note: PostTags is not part of the public XML dump - reconstructed as
the post_tags materialized view in 00-setup.sql.

Note: this query is inherently tied to a specific historical window on
stackoverflow.com. Whichever site you load with sepg pipeline, its May 2010
activity (or lack of it) could return an empty result-set. Run it against
a site/date range with real traffic in that window if you want a better result set. */

WITH may AS (
    SELECT pt.tag_name, count(*) AS may_count
    FROM post_tags pt
        INNER JOIN posts p ON p.id = pt.post_id
    WHERE p.creation_date >= '2010-05-01' AND p.creation_date < '2010-06-01'
    GROUP BY pt.tag_name
),
total AS (
    SELECT tag_name, count(*) AS total_count
    FROM post_tags
    GROUP BY tag_name
    HAVING count(*) > 800
)
SELECT
    total.tag_name AS "Tag",
    row_number() OVER (ORDER BY may.may_count DESC) AS "MayRank",
    row_number() OVER (ORDER BY total.total_count DESC) AS "TotalRank",
    may.may_count AS "QuestionsInMay",
    total.total_count AS "QuestionsTotal"
FROM may
    INNER JOIN total ON total.tag_name = may.tag_name
ORDER BY may.may_count DESC;
