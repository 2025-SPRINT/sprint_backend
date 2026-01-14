from flask import Flask

print(getattr(Flask.response_class, "status_code"))