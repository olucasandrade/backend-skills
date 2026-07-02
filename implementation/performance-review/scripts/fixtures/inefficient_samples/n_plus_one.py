def list_posts_with_authors(db, post_ids):
    posts = db.query("SELECT * FROM posts WHERE id IN (?)", post_ids)
    # Inefficient: one query per post to fetch its author instead of a
    # single batched query (JOIN or WHERE author_id IN (...)).
    for post in posts:
        post["author"] = db.query_one(
            "SELECT * FROM users WHERE id = ?", post["author_id"]
        )
    return posts
