/* Posts containing a very short title
Questions (ParentId IS NULL) whose title is under 16 characters. */

SELECT id AS "Post Link", body AS "Body", score AS "Score"
FROM posts
WHERE length(title) < 16 AND parent_id IS NULL;
