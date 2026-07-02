def find_duplicate_emails(users):
    # Inefficient: O(n^2) pairwise comparison over a list that's expected
    # to grow with the user base, where a single pass with a set/dict
    # would be O(n).
    duplicates = []
    for i, a in enumerate(users):
        for b in users[i + 1:]:
            if a["email"] == b["email"]:
                duplicates.append((a["id"], b["id"]))
    return duplicates
