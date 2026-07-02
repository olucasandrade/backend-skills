# fixture: intentional per-request client construction
class HttpClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def get(self, path):
        raise NotImplementedError


def fetch_user_profile(user_id):
    # Inefficient: constructs a brand new client per call instead of
    # reusing a pooled/module-level one.
    client = HttpClient(base_url="https://profiles.internal")
    return client.get(f"/users/{user_id}")
