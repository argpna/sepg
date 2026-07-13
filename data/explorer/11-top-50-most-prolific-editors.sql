/* Top 50 Most Prolific Editors
Shows the top 50 post editors, where the user was the most recent editor */

SELECT
    u.id AS "User Link",
    edits.question_edits AS "QuestionEdits",
    edits.answer_edits AS "AnswerEdits",
    edits.total_edits AS "TotalEdits"
FROM (
    SELECT
        last_editor_user_id,
        count(*) FILTER (WHERE post_type_id = 1) AS question_edits,
        count(*) FILTER (WHERE post_type_id = 2) AS answer_edits,
        count(*) AS total_edits
    FROM posts
    WHERE last_editor_user_id IS NOT NULL
        AND last_editor_user_id <> owner_user_id
    GROUP BY last_editor_user_id
) edits
    INNER JOIN users u ON u.id = edits.last_editor_user_id
ORDER BY edits.total_edits DESC
LIMIT 50;
