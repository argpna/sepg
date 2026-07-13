/* Up vs Down votes by day of week of Question or Answer
For questions and answers, how up/down votes break down by the day of week
the post was created. */

SELECT
    CASE WHEN p.post_type_id = 1 THEN 'Question' ELSE 'Answer' END AS "Post Type",
    to_char(p.creation_date, 'FMDay') AS "Day",
    count(*) AS "Amount",
    count(*) FILTER (WHERE v.vote_type_id = 2) AS "UpVotes",
    count(*) FILTER (WHERE v.vote_type_id = 3) AS "DownVotes",
    round(
        count(*) FILTER (WHERE v.vote_type_id = 2)::numeric
        / NULLIF(count(*) FILTER (WHERE v.vote_type_id = 3), 0),
    4) AS "UpVoteDownVoteRatio"
FROM votes v
    INNER JOIN posts p ON v.post_id = p.id
WHERE p.post_type_id IN (1, 2)
    AND v.vote_type_id IN (2, 3)
GROUP BY p.post_type_id, EXTRACT(DOW FROM p.creation_date), to_char(p.creation_date, 'FMDay')
ORDER BY p.post_type_id, EXTRACT(DOW FROM p.creation_date);
