/* Shared setup for data/explorer/ *.sql */

/* PostTags is not part of the public XML dump - reconstructed as the post_tags materialized view
Re-run REFRESH MATERIALIZED VIEW post_tags if the underlying data changes. */
CREATE MATERIALIZED VIEW IF NOT EXISTS post_tags AS
SELECT p.id AS post_id, t.id AS tag_id, t.tag_name
FROM posts p
    CROSS JOIN LATERAL unnest(string_to_array(btrim(p.tags, '|'), '|')) AS tag(tag_name)
    INNER JOIN tags t USING (tag_name)
WHERE p.tags <> '';

CREATE UNIQUE INDEX IF NOT EXISTS post_tags_post_tag_uidx ON post_tags (post_id, tag_id);
CREATE INDEX IF NOT EXISTS post_tags_tag_id_idx ON post_tags (tag_id);

/* posts: owner_user_id alone covers "my posts" lookups. The composite also
covers "my posts of this type" */
CREATE INDEX IF NOT EXISTS posts_owner_user_id_post_type_id_idx ON posts (owner_user_id, post_type_id);

/* posts: answer -> parent question joins, and "questions" scans (parent_id IS NULL).
The composite also serves "answers/questions above a score threshold". */
CREATE INDEX IF NOT EXISTS posts_parent_id_score_idx ON posts (parent_id, score);

/* posts: date-range/recency queries. */
CREATE INDEX IF NOT EXISTS posts_creation_date_idx ON posts (creation_date);

/* posts: substring search over body text can't use a plain btree index.
pg_trgm's GIN index turns that into a bitmap index scan. Scoped to answers only
(post_type_id = 2) */

/* CREATE EXTENSION IF NOT EXISTS pg_trgm; -- is templated, so commenting out */
CREATE INDEX IF NOT EXISTS posts_body_trgm_idx ON posts
    USING gin (body gin_trgm_ops)
    WHERE post_type_id = 2;

/* votes: post_id alone covers per-post vote counts. The composite also
covers "votes of this type on this post" */
CREATE INDEX IF NOT EXISTS votes_post_id_vote_type_id_idx ON votes (post_id, vote_type_id);

/* comments: "my comments" lookups. The composite also covers "my comment
score distribution" (group by score) */
CREATE INDEX IF NOT EXISTS comments_user_id_score_idx ON comments (user_id, score);

/* users: reputation-ordered/filtered queries */
CREATE INDEX IF NOT EXISTS users_reputation_idx ON users (reputation);

/* badges: name alone covers "who earned badge X" lookups. The composite also
serves "count of badge X per user" index-only, since those queries filter name
then group by user_id. Without it a name filter seq-scans all badge rows. */
CREATE INDEX IF NOT EXISTS badges_name_user_id_idx ON badges (name, user_id);
