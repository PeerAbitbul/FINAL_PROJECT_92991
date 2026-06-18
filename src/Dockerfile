# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY ingest/ ./ingest/

# Install dependencies
RUN pip install psycopg2-binary neo4j requests



# Run app.py when the container launches
WORKDIR /app/ingest

CMD ["python", "main.py"]
