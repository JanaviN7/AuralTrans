"""Print the API's OpenAPI schema (used to generate the web app's TypeScript types)."""

import json

from auraltrans.api.app import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
