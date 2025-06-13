# Use the official Python base image
FROM python:3.9

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install dependencies
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /code/

# Run server
CMD ["gunicorn", "evaluation.wsgi:application", "--bind", "0.0.0.0:8000"]
