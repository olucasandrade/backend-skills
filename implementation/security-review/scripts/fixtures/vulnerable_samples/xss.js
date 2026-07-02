function renderComment(comment) {
  // Vulnerable: user-controlled comment body written directly into the
  // DOM via innerHTML instead of a text-only assignment or a sanitizer,
  // allowing stored XSS via a crafted comment body.
  const el = document.getElementById("comment-" + comment.id);
  el.innerHTML = comment.body;
}

module.exports = { renderComment };
