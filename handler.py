"""AWS Lambda entry point — wraps the FastAPI app with Mangum."""

from mangum import Mangum

from app.main import app

lambda_handler = Mangum(app)
